import os
import sys
import logging
import threading
import time
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Ensure repo root on sys.path so local imports work
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("workflowgenie")


def create_app():
    STATIC_DIR = os.path.join(REPO_ROOT, "legacy", "static")
    app = Flask("workflowgenie", static_folder=STATIC_DIR, static_url_path="/static")

    # Readiness flags
    app.config["READY"] = False
    app.config["INIT_IN_PROGRESS"] = False
    app.config["INIT_ERROR"] = None

    # Placeholders for components; will be filled by background init
    app.config["llm"] = None
    app.config["tools"] = None
    app.config["memory"] = None
    app.config["workflow"] = None

    # Import function definitions (safe) but do NOT instantiate heavy objects here
    from workflows.workflow import build_workflow, run  # noqa: E402


    def _do_startup():
        # Run heavy initialization in background thread
        if app.config.get("INIT_IN_PROGRESS"):
            logger.info("Startup already in progress; skipping extra call.")
            return

        app.config["INIT_IN_PROGRESS"] = True
        app.config["INIT_ERROR"] = None
        try:
            logger.info("Background startup: initializing components...")
            # Use app context for initializers that may rely on it
            with app.app_context():
                # Initialize tools
                try:
                    from tools.calendar_tool import CalendarTool
                    from tools.reminder_tool import ReminderTool
                    calendar = CalendarTool()
                    reminder = ReminderTool()
                    tools = {"calendar": calendar, "reminder": reminder}
                    app.config["tools"] = tools
                    logger.info("Tools initialized")
                except Exception as e:
                    logger.exception("Failed initializing tools: %s", e)
                    raise

                # Memory startup cleanup
                try:
                    from state.memory_store import TaskMemory
                    # Create memory with tools but without LLM yet
                    memory = TaskMemory(tools=app.config.get("tools"))
                    memory.cleanup_on_startup()
                    app.config["memory"] = memory
                    logger.info("Memory startup cleanup complete")
                except Exception as e:
                    logger.exception("Memory startup cleanup failed: %s", e)
                    raise

                # Initialize LLM last (may be heavy)
                try:
                    from llm import LLM
                    llm = LLM()
                    app.config["llm"] = llm
                    logger.info("LLM initialized")
                except Exception as e:
                    logger.exception("LLM initialization failed: %s", e)
                    raise

                # Build workflow after components are ready
                try:
                    workflow = build_workflow()
                    app.config["workflow"] = workflow
                    logger.info("Workflow built")
                except Exception as e:
                    logger.exception("Failed to build workflow: %s", e)
                    raise

            # If we reach here, startup succeeded
            app.config["READY"] = True
            logger.info("Background startup: initialization complete. READY=True")
        except Exception as e:
            logger.exception("Background startup failed: %s", e)
            app.config["READY"] = False
            app.config["INIT_ERROR"] = str(e)
        finally:
            app.config["INIT_IN_PROGRESS"] = False


    def start_background_init_if_needed():
        # Optionally allow forcing init at process start by env var (for local dev)
        force_at_start = os.environ.get("FORCE_BACKGROUND_INIT", "false").lower() in ("1", "true", "yes")
        if force_at_start and not app.config["INIT_IN_PROGRESS"] and not app.config["READY"]:
            t = threading.Thread(target=_do_startup, daemon=True)
            t.start()
            logger.info("Forced background init started at process start.")


    def kick_off_background_init():
        # Start background init but do not block the request
        if app.config.get("READY"):
            logger.info("kick_off_background_init: already READY.")
            return

        if not app.config.get("INIT_IN_PROGRESS"):
            logger.info("kick_off_background_init: starting background init thread.")
            t = threading.Thread(target=_do_startup, daemon=True)
            t.start()
        else:
            logger.info("kick_off_background_init: init already in progress.")

    # Register kick-off to run on first request. Some Flask distributions
    # may not expose `before_first_request` as an attribute in older or
    # minimal builds; try to register via the decorator API and fall back
    # to a lightweight `before_request` check that only triggers once.
    try:
        app.before_first_request(kick_off_background_init)
    except Exception:
        # Fallback: use a before_request hook that runs once.
        app.config.setdefault("_background_init_kicked", False)

        @app.before_request
        def _kick_once_before_request():
            if not app.config.get("_background_init_kicked"):
                app.config["_background_init_kicked"] = True
                # start background init in a thread
                if not app.config.get("INIT_IN_PROGRESS") and not app.config.get("READY"):
                    t = threading.Thread(target=_do_startup, daemon=True)
                    t.start()


    @app.route("/", methods=["GET"])
    def root():
        try:
            index_path = os.path.join(app.static_folder, "index.html")
            if os.path.exists(index_path):
                return app.send_static_file("index.html")
        except Exception:
            pass

        return jsonify({
            "message": "WorkFlowGenie API",
            "endpoints": {
                "GET /health": "Health check",
                "GET /ready": "Readiness (initializing -> ready)",
                "POST /run": "Run workflow (body: {\"text\": \"...\"})",
                "GET /tasks": "List tasks (query: ?include_done=true)",
                "POST /tasks/<id>/done": "Mark task done",
                "GET /events": "List calendar events",
                "GET /reminders": "List reminders"
            }
        })


    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})


    @app.route("/ready", methods=["GET"])
    def ready():
        ready_flag = app.config.get("READY", False)
        status = "ready" if ready_flag else "initializing"
        code = 200 if ready_flag else 503
        payload = {"status": status, "initializing": not ready_flag}
        if app.config.get("INIT_ERROR"):
            payload["error"] = app.config.get("INIT_ERROR")
        return jsonify(payload), code


    @app.route("/run", methods=["POST"])
    def run_endpoint():
        # If not ready, return 503 per requirement
        if not app.config.get("READY"):
            logger.info("Received /run while not READY; returning 503.")
            return jsonify({
                "error": "service_initializing",
                "message": "Server is starting up. Try again in a few seconds.",
                "ready": False
            }), 503

        data = request.get_json(force=True)
        text = data.get("text") if data else None
        if not text:
            return jsonify({"error": "missing 'text' in body"}), 400

        # Create ephemeral tools/memory for the request so requests remain isolated
        try:
            from tools.calendar_tool import CalendarTool
            from tools.reminder_tool import ReminderTool
            calendar = CalendarTool()
            reminder = ReminderTool()
            tools = {"calendar": calendar, "reminder": reminder}
            from state.memory_store import TaskMemory
            memory = TaskMemory(tools=tools, llm=app.config.get("llm"))
            # ensure memory cleanup on startup for this ephemeral memory
            memory.cleanup_on_startup()
            workflow = app.config.get("workflow")

            # Import run function
            from workflows.workflow import run as workflow_run
            result = workflow_run(workflow, memory=memory, inputs={"text": text})

            # clear ephemeral tools state
            try:
                calendar.clear_events()
                reminder.clear_reminders()
            except Exception:
                pass

            return jsonify({"ok": True, "result": result})
        except Exception as e:
            logger.exception("Workflow run failed")
            try:
                calendar.clear_events()
                reminder.clear_reminders()
            except Exception:
                pass
            return jsonify({"error": str(e)}), 500


    @app.route("/tasks", methods=["GET"])
    def tasks():
        if not app.config.get("READY"):
            return jsonify({"error": "service_initializing", "ready": False}), 503
        include_done = request.args.get("include_done", "false").lower() in ("1", "true", "yes")
        memory = app.config.get("memory")
        return jsonify({"tasks": memory.list_tasks(include_done=include_done)})


    @app.route("/tasks/<int:task_id>/done", methods=["POST"])
    def mark_done(task_id):
        if not app.config.get("READY"):
            return jsonify({"error": "service_initializing", "ready": False}), 503
        memory = app.config.get("memory")
        memory.mark_done(task_id)
        return jsonify({"ok": True})


    @app.route("/events", methods=["GET"])
    def events():
        if not app.config.get("READY"):
            return jsonify({"error": "service_initializing", "ready": False}), 503
        tools = app.config.get("tools")
        return jsonify({"events": tools["calendar"].list_events()})


    @app.route("/reminders", methods=["GET"])
    def reminders():
        if not app.config.get("READY"):
            return jsonify({"error": "service_initializing", "ready": False}), 503
        tools = app.config.get("tools")
        return jsonify({"reminders": tools["reminder"].list_reminders()})


    @app.route("/clear_db", methods=["POST"])
    def clear_db():
        # Require explicit confirmation in request body to avoid accidental clears.
        # Client should POST JSON: {"confirm": true}
        data = request.get_json(silent=True) or {}
        if not data.get("confirm"):
            return jsonify({"error": "missing 'confirm': true in request body"}), 400

        from state.memory_store import TaskMemory
        mem = TaskMemory()
        mem.clear_db()
        return jsonify({"status": "ok", "message": "Database cleared"})


    @app.route("/tasks/<int:task_id>/delete", methods=["POST", "DELETE"])
    def delete_task(task_id: int):
        if not app.config.get("READY"):
            return jsonify({"error": "service_initializing", "ready": False}), 503
        memory = app.config.get("memory")
        try:
            memory.delete_task(task_id)
            return jsonify({"ok": True, "deleted": task_id})
        except Exception as e:
            logger.exception("Failed to delete task %s", task_id)
            return jsonify({"error": str(e)}), 500

    # Optionally start background init at process start (if configured)
    start_background_init_if_needed()

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    logger.info("Flask starting on port %s", port)
    # Development server; use gunicorn in production
    app.run(host="0.0.0.0", port=port)
