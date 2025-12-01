import os
import sys
import logging
import threading
import traceback
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Add repo root
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("legacy.server_flask")


def create_app():
    STATIC_DIR = os.path.join(REPO_ROOT, "legacy", "static")
    app = Flask("workflowgenie", static_folder=STATIC_DIR, static_url_path="/static")

    # state flags
    app.config["READY"] = False
    app.config["INIT_IN_PROGRESS"] = False
    app.config["INIT_ERROR"] = None

    # placeholders
    app.config["tools"] = None
    app.config["memory"] = None
    app.config["workflow"] = None
    app.config["llm"] = None

    # helper: log exceptions to file + stdout
    def _log_init_exception(exc: Exception, ctx: str):
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        log_entry = f"\n=== INIT ERROR ({ctx}) ===\n{tb}\n"
        print(log_entry, flush=True)
        try:
            with open("/tmp/init_error.log", "a") as f:
                f.write(log_entry)
        except:
            pass

    # heavy initializer
    def heavy_init():
        logger.info("Heavy init thread started...")
        try:
            with app.app_context():

                # Tools
                try:
                    from tools.calendar_tool import CalendarTool
                    from tools.reminder_tool import ReminderTool
                    app.config["tools"] = {
                        "calendar": CalendarTool(),
                        "reminder": ReminderTool()
                    }
                except Exception as e:
                    _log_init_exception(e, "tools init")
                    raise

                # Memory
                try:
                    from state.memory_store import TaskMemory
                    mem = TaskMemory(tools=app.config["tools"])
                    mem.cleanup_on_startup()
                    app.config["memory"] = mem
                except Exception as e:
                    _log_init_exception(e, "memory init")
                    raise

                # LLM
                try:
                    from llm import LLM
                    app.config["llm"] = LLM()
                except Exception as e:
                    _log_init_exception(e, "llm init")
                    raise

                # Workflow
                try:
                    from workflows.workflow import build_workflow
                    app.config["workflow"] = build_workflow()
                except Exception as e:
                    _log_init_exception(e, "workflow build")
                    raise

            app.config["READY"] = True
            logger.info("Heavy init completed. READY=True")
        except Exception as e:
            _log_init_exception(e, "outer heavy_init")
            app.config["INIT_ERROR"] = str(e)
            app.config["READY"] = False
        finally:
            app.config["INIT_IN_PROGRESS"] = False

    def start_init():
        if not app.config["INIT_IN_PROGRESS"] and not app.config["READY"]:
            app.config["INIT_IN_PROGRESS"] = True
            threading.Thread(target=heavy_init, daemon=True).start()

    @app.before_request
    def ensure_started():
        start_init()

    # ROUTES
    @app.route("/")
    def root():
        index = os.path.join(app.static_folder, "index.html")
        if os.path.exists(index):
            return app.send_static_file("index.html")
        return jsonify({"message": "WorkflowGenie API"})

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

    # NEW debug endpoint — now correctly inside create_app()
    @app.route("/debug-init")
    def debug_init():
        p = "/tmp/init_error.log"
        if not os.path.exists(p):
            return jsonify({"ok": False, "message": "no init log"}), 404
        with open(p) as f:
            lines = f.read().splitlines()
        return jsonify({"ok": True, "tail": lines[-200:]})

    @app.route("/run", methods=["POST"])
    def run_api():
        if not app.config["READY"]:
            return jsonify({"error": "initializing"}), 503

        data = request.get_json() or {}
        text = data.get("text")
        if not text:
            return jsonify({"error": "missing text"}), 400

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

        from workflows.workflow import run as workflow_run
        result = workflow_run(app.config["workflow"], memory=memory, inputs={"text": text})
        return jsonify({"result": result})

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
