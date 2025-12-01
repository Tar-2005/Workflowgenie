import os
from tinydb import TinyDB, Query
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Use Railway-safe writable directory
DB_PATH = os.path.join("/tmp", "workflowgenie_adk_db.json")


class TaskMemory:

    def __init__(self, db_path: str = None, tools: dict = None, llm=None):
        self.db_path = db_path or DB_PATH
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
        """Delete a task by its numeric id field."""
        Task = Query()
        # remove all matching entries
        self.table.remove(Task.id == task_id)

    def clear_db(self):
        self.db.drop_tables()
        self.db = TinyDB(self.db_path)
        self.table = self.db.table("tasks")
        logger.info("TaskMemory: DB cleared.")

    def clear(self):
        """Alias for clear_db(): delete all persistent data."""
        self.clear_db()

    def cleanup_on_startup(self):
        """
        Remove blank-title tasks and deduplicate tasks (keep earliest created).
        Run this at program start to avoid leftover/blank records from earlier runs.
        """
        logger.info("TaskMemory: Running startup cleanup on DB: %s", self.db_path)
        all_tasks = self.table.all()
        # Remove tasks with blank/empty titles (whitespace-only)
        removed = 0
        for t in all_tasks:
            title = (t.get("title") or "").strip()
            if title == "":
                self.table.remove(doc_ids=[t.doc_id])
                removed += 1
        if removed:
            logger.info("TaskMemory: removed %d blank-title tasks.", removed)

        # Deduplicate by (title, due) — keep earliest created_at
        tasks = self.table.all()
        seen = {}
        duplicates = []
        for t in tasks:
            key = ( (t.get("title") or "").strip().lower(), t.get("due") or "none" )
            created = t.get("created_at") or ""
            # if key seen, compare created times and choose earliest to keep
            if key in seen:
                # existing doc
                existing = seen[key]
                # choose which to keep: earliest created_at string lexicographically earlier likely older
                keep = existing
                drop = t
                # if new one has earlier timestamp, swap
                if created and existing.get("created_at"):
                    if created < existing.get("created_at"):
                        keep = t
                        drop = existing
                        seen[key] = keep
                duplicates.append(drop)
            else:
                seen[key] = t

        # Remove duplicates
        if duplicates:
            for d in duplicates:
                self.table.remove(doc_ids=[d.doc_id])
            logger.info("TaskMemory: removed %d duplicate tasks.", len(duplicates))

        logger.info("TaskMemory: startup cleanup complete.")

