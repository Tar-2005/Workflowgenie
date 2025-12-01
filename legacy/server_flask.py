# --- DEBUG-SAFE additions for legacy/server_flask.py ---
import traceback

# helper to append full traceback to /tmp/init_error.log and also print it
def _log_init_exception(exc: Exception, context: str = ""):
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    msg = f"INIT EXCEPTION ({context}):\n{tb}\n"
    # print so Railway logs capture it
    print(msg, flush=True)
    # append to a file under /tmp so we can fetch it via an endpoint
    try:
        with open("/tmp/init_error.log", "a", encoding="utf-8") as f:
            f.write(msg)
    except Exception as e:
        # If we cannot write to /tmp, also print that error
        print("Failed to write /tmp/init_error.log:", e, flush=True)

# Replace heavy_init with the debug-safe version
def heavy_init():
    logger.info("Heavy init thread started (DEBUG MODE)...")
    try:
        with app.app_context():
            # Tools
            try:
                from tools.calendar_tool import CalendarTool
                from tools.reminder_tool import ReminderTool
                calendar = CalendarTool()
                reminder = ReminderTool()
                app.config["tools"] = {"calendar": calendar, "reminder": reminder}
                logger.info("Tools initialized (DEBUG)")
            except Exception as e:
                _log_init_exception(e, "tools init")
                raise

            # Memory (TinyDB) -- ensure DB path uses /tmp in memory_store.py
            try:
                from state.memory_store import TaskMemory
                memory = TaskMemory(tools=app.config["tools"])
                memory.cleanup_on_startup()
                app.config["memory"] = memory
                logger.info("Memory startup cleanup complete (DEBUG)")
            except Exception as e:
                _log_init_exception(e, "memory init")
                raise

            # LLM
            try:
                from llm import LLM
                llm = LLM()
                app.config["llm"] = llm
                logger.info("LLM initialized (DEBUG)")
            except Exception as e:
                _log_init_exception(e, "llm init")
                raise

            # Workflow
            try:
                from workflows.workflow import build_workflow
                flow = build_workflow()
                app.config["workflow"] = flow
                logger.info("Workflow built (DEBUG)")
            except Exception as e:
                _log_init_exception(e, "workflow build")
                raise

        # If we get here it's OK
        app.config["READY"] = True
        logger.info("Heavy init completed. READY=True (DEBUG)")
    except Exception as e:
        # log and keep the app alive
        logger.exception("Background startup failed (DEBUG); check /tmp/init_error.log")
        _log_init_exception(e, "heavy_init outer")
        app.config["INIT_ERROR"] = str(e)
        app.config["READY"] = False
    finally:
        app.config["INIT_IN_PROGRESS"] = False

# Ensure the start_init and ensure_init behavior still runs; keep existing start_init/ensure_init
# (no change needed if already present)
# --- add debug endpoint to read /tmp/init_error.log ---
@app.route("/debug-init", methods=["GET"])
def debug_init_log():
    # Return last N lines of /tmp/init_error.log
    try:
        p = "/tmp/init_error.log"
        if not os.path.exists(p):
            return jsonify({"ok": False, "message": "no init log found"}), 404
        with open(p, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
            tail = lines[-200:] if len(lines) > 200 else lines
            return jsonify({"ok": True, "tail": tail})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
