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
    STATIC_DIR = os.path.join(REPO_ROOT, "legacy", "static")
    app = Flask("workflowgenie", static_folder=STATIC_DIR, static_url_path="/static")

    app.config["READY"] = False
    app.config["INIT_IN_PROGRESS"] = False
    app.config["INIT_ERROR"] = None

    app.config["llm"] = None
    app.config["tools"] = None
    app.config["memory"] = None
    app.config["workflow"] = None

    from workflows.workflow import build_workflow, run as workflow_run

    def heavy_init():
        logger.info("Heavy init thread started...")
        try:
            with app.app_context():

                # Tools
                from tools.calendar_tool import CalendarTool
                from tools.reminder_tool import ReminderTool
                calendar = CalendarTool()
                reminder = ReminderTool()
                app.config["tools"] = {"calendar": calendar, "reminder": reminder}

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
                flow = build_workflow()
                app.config["workflow"] = flow

            app.config["READY"] = True
            logger.info("Heavy init completed. READY=True")
        except Exception as e:
            logger.exception("INIT ERROR")
            app.config["INIT_ERROR"] = str(e)
            app.config["READY"] = False
        finally:
            app.config["INIT_IN_PROGRESS"] = False

    def start_init():
        if not app.config["INIT_IN_PROGRESS"] and not app.config["READY"]:
            app.config["INIT_IN_PROGRESS"] = True
            threading.Thread(target=heavy_init, daemon=True).start()

    @app.before_request
    def ensure_init():
        start_init()

    @app.route("/")
    def root():
        index = os.path.join(app.static_folder, "index.html")
        if os.path.exists(index):
            return app.send_static_file("index.html")
        return jsonify({"ok": True, "message": "WorkflowGenie API"})

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

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

        data = request.get_json(silent=True) or {}
        text = data.get("text")
        if not text:
            return jsonify({"error": "no text"}), 400

        # isolated per-request tools/memory
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
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
