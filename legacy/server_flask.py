import os
import sys
import logging
import threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Add repo root to sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("legacy.server_flask")


def create_app():
    # Static folder (must exist)
    STATIC_DIR = os.path.join(REPO_ROOT, "static")
    FALLBACK_STATIC_DIR = os.path.join(REPO_ROOT, "legacy", "static")

    # Prefer /static, fallback to /legacy/static
    if os.path.exists(STATIC_DIR):
        static_folder = STATIC_DIR
    else:
        static_folder = FALLBACK_STATIC_DIR

    app = Flask(
        "workflowgenie",
        static_folder=static_folder,
        static_url_path="/static"
    )

    # State Flags
    app.config["READY"] = False
    app.config["INIT_IN_PROGRESS"] = False
    app.config["INIT_ERROR"] = None

    # Instances to fill later
    app.config["llm"] = None
    app.config["tools"] = None
    app.config["memory"] = None
    app.config["workflow"] = None

    # Lazy imports
    from workflows.workflow import build_workflow, run as workflow_run

    # -----------------------
    # HEAVY INITIALIZATION
    # -----------------------
    def heavy_init():
        try:
            logger.info("Heavy init thread: STARTED")

            with app.app_context():
                # Tools
                from tools.calendar_tool import CalendarTool
                from tools.reminder_tool import ReminderTool

                calendar = CalendarTool()
                reminder = ReminderTool()
                app.config["tools"] = {
                    "calendar": calendar,
                    "reminder": reminder
                }

                # Memory
                from state.memory_store import TaskMemory
                memory = TaskMemory(tools=app.config["tools"])
                memory.cleanup_on_startup()
                app.config["memory"] = memory

                # LLM
                from llm import LLM
                llm = LLM()
                app.config["llm"] = llm

                # Workflow
                wf = build_workflow()
                app.config["workflow"] = wf

            app.config["READY"] = True
            logger.info("Heavy init COMPLETED — READY=True")

        except Exception as e:
            logger.exception("INIT ERROR")
            app.config["INIT_ERROR"] = str(e)
            app.config["READY"] = False

        finally:
            app.config["INIT_IN_PROGRESS"] = False

    # -----------------------
    # START INITIALIZATION
    # -----------------------
    def start_init():
        if not app.config["INIT_IN_PROGRESS"] and not app.config["READY"]:
            app.config["INIT_IN_PROGRESS"] = True
            threading.Thread(target=heavy_init, daemon=True).start()

    # -----------------------
    # BEFORE REQUEST HOOK
    # DO NOT BLOCK ROOT/HEALTH !!!!
    # -----------------------
    @app.before_request
    def ensure_init():
        path = request.path

        # Never block Railway health checks
        if path in ["/", "/health", "/ready"]:
            return

        # Kick initialization for other routes
        start_init()

    # -----------------------
    # ROUTES
    # -----------------------
    @app.route("/")
    def root():
        # Fast 200 OK (Railway reads this!)
        try:
            index_file = os.path.join(app.static_folder, "index.html")
            if os.path.exists(index_file):
                return app.send_static_file("index.html")
        except:
            pass

        return jsonify({
            "ok": True,
            "message": "WorkflowGenie API running",
            "ready": app.config["READY"]
        }), 200

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.route("/ready")
    def ready():
        if app.config["READY"]:
            return jsonify({"status": "ready"}), 200

        return jsonify({
            "status": "initializing",
            "error": app.config["INIT_ERROR"]
        }), 503

    @app.route("/run", methods=["POST"])
    def run_api():
        if not app.config["READY"]:
            return jsonify({"error": "initializing"}), 503

        data = request.get_json(force=True)
        text = data.get("text")
        if not text:
            return jsonify({"error": "Missing text"}), 400

        # ephemeral tools per run
        from tools.calendar_tool import CalendarTool
        from tools.reminder_tool import ReminderTool
        from state.memory_store import TaskMemory

        calendar = CalendarTool()
        reminder = ReminderTool()

        memory = TaskMemory(
            tools={"calendar": calendar, "reminder": reminder},
            llm=app.config["llm"]
        )
        memory.cleanup_on_startup()

        result = workflow_run(app.config["workflow"], memory=memory, inputs={"text": text})

        return jsonify({"result": result})

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
