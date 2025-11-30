import os
import sys
import logging

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from flask import Flask, request, jsonify  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

# Now safe to import local top-level packages
from workflows.workflow import build_workflow, run  # noqa: E402
from state.memory_store import TaskMemory  # noqa: E402
from llm import LLM  # noqa: E402
from tools.calendar_tool import CalendarTool  # noqa: E402
from tools.reminder_tool import ReminderTool  # noqa: E402

# Load .env after module-level imports so import ordering rules are preserved.
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app():
    # Configure Flask to serve the legacy static folder at the URL path `/static`.
    STATIC_DIR = os.path.join(REPO_ROOT, "legacy", "static")
    app = Flask("workflowgenie", static_folder=STATIC_DIR, static_url_path="/static")

    logger.info("Flask server startup: initializing LLM, tools and memory")
    llm = LLM()
    calendar = CalendarTool()
    reminder = ReminderTool()
    tools = {"calendar": calendar, "reminder": reminder}
    memory = TaskMemory(tools=tools, llm=llm)
    memory.cleanup_on_startup()
    workflow = build_workflow()

    app.config["llm"] = llm
    app.config["tools"] = tools
    app.config["memory"] = memory
    app.config["workflow"] = workflow

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

    @app.route("/run", methods=["POST"])
    def run_endpoint():
        data = request.get_json(force=True)
        text = data.get("text") if data else None
        if not text:
            return jsonify({"error": "missing 'text' in body"}), 400
        
        calendar = CalendarTool()
        reminder = ReminderTool()
        tools = {"calendar": calendar, "reminder": reminder}
        memory = TaskMemory(tools=tools, llm=app.config.get("llm"))
        memory.cleanup_on_startup()
        workflow = app.config.get("workflow")
        
        try:
            result = run(workflow, memory=memory, inputs={"text": text})
            # Result captured; DB already cleared by workflow.run()
            calendar.clear_events()
            reminder.clear_reminders()
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
        include_done = request.args.get("include_done", "false").lower() in ("1", "true", "yes")
        memory: TaskMemory = app.config.get("memory")
        return jsonify({"tasks": memory.list_tasks(include_done=include_done)})

    @app.route("/tasks/<int:task_id>/done", methods=["POST"])
    def mark_done(task_id):
        memory: TaskMemory = app.config.get("memory")
        memory.mark_done(task_id)
        return jsonify({"ok": True})

    @app.route("/events", methods=["GET"])
    def events():
        tools = app.config.get("tools")
        return jsonify({"events": tools["calendar"].list_events()})

    @app.route("/reminders", methods=["GET"])
    def reminders():
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
        memory: TaskMemory = app.config.get("memory")
        try:
            memory.delete_task(task_id)
            return jsonify({"ok": True, "deleted": task_id})
        except Exception as e:
            logger.exception("Failed to delete task %s", task_id)
            return jsonify({"error": str(e)}), 500

 

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print("Flask starting on port", port)
    app.run(host="0.0.0.0", port=port)
