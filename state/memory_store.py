import os
import tempfile
from tinydb import TinyDB, Query
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class TaskMemory:

    def __init__(self, db_path: str = None, tools: dict = None, llm=None):
        # Cross-platform safe writable directory
        safe_tmp = tempfile.gettempdir()    
        
        self.db_path = db_path or os.path.join(safe_tmp, "workflowgenie_adk_db.json")

        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self.db = TinyDB(self.db_path)
        self.table = self.db.table("tasks")
        self.tools = tools or {}
        self.llm = llm

    def store_task(self, task: dict):
        Task = Query()
        if self.table.contains(Task.id == task["id"]):
            self.table.update(task, Task.id == task["id"])
        else:
            self.table.insert(task)

    def list_pending(self):
        return [t for t in self.table.all() if not t.get("done", False)]

    def list_tasks(self, include_done: bool = False):
        if include_done:
            return self.table.all()
        return [t for t in self.table.all() if not t.get("done", False)]

    @property
    def tasks(self):
        return self.table.all()

    def mark_done(self, task_id):
        Task = Query()
        self.table.update({"done": True}, Task.id == task_id)

    def delete_task(self, task_id):
        Task = Query()
        self.table.remove(Task.id == task_id)

    def clear_db(self):
        self.db.drop_tables()
        self.db = TinyDB(self.db_path)
        self.table = self.db.table("tasks")
        logger.info("TaskMemory: DB cleared.")

    def clear(self):
        self.clear_db()

    def cleanup_on_startup(self):
        logger.info("TaskMemory: Running startup cleanup on DB: %s", self.db_path)
        all_tasks = self.table.all()

        # Remove blank titles
        removed = 0
        for t in all_tasks:
            title = (t.get("title") or "").strip()
            if title == "":
                self.table.remove(doc_ids=[t.doc_id])
                removed += 1
        if removed:
            logger.info("TaskMemory: removed %d blank-title tasks.", removed)

        # Deduplicate
        tasks = self.table.all()
        seen = {}
        duplicates = []

        for t in tasks:
            key = ((t.get("title") or "").strip().lower(), t.get("due") or "none")
            created = t.get("created_at") or ""

            if key in seen:
                existing = seen[key]

                keep = existing
                drop = t

                if created and existing.get("created_at"):
                    if created < existing.get("created_at"):
                        keep = t
                        drop = existing
                        seen[key] = keep

                duplicates.append(drop)
            else:
                seen[key] = t

        # Remove duplicates
        for d in duplicates:
            self.table.remove(doc_ids=[d.doc_id])

        if duplicates:
            logger.info("TaskMemory: removed %d duplicate tasks.", len(duplicates))

        logger.info("TaskMemory: startup cleanup complete.")
