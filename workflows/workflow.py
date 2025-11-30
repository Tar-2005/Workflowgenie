from typing import Dict, Any
import asyncio
import inspect

from agents import task_extractor_agent, planner_agent, reminder_agent, reporter_agent


class Workflow:
    """Simple workflow definition."""
    def __init__(self, name: str):
        self.name = name
        self.steps = []  # list of (step_func, step_name) tuples
    
    def set_entrypoint(self, func):
        self.steps = [(func, func.__name__)]
    
    def add_step(self, func):
        self.steps.append((func, func.__name__))


def run(workflow: Workflow, memory: Any, inputs: Dict[str, Any]):
    """Execute workflow: run each step sequentially, collecting outputs.
    
    IMPORTANT: After all steps complete, the database is automatically cleared
    to ensure stateless operation (no leftover state between requests).
    """
    result = {}
    tools = memory.tools if hasattr(memory, 'tools') else {}
    llm = memory.llm if hasattr(memory, 'llm') else None
    
    try:
        for step_func, step_name in workflow.steps:
            try:
                # If the step function is a coroutine function, run it in an
                # event loop so legacy synchronous callers (like Flask) can
                # execute async agents. Also handle the case where a sync
                # function returns an awaitable.
                if inspect.iscoroutinefunction(step_func):
                    output = asyncio.run(step_func(inputs, memory, tools, llm))
                else:
                    output = step_func(inputs, memory, tools, llm)

                # If the returned value itself is awaitable, await it as well.
                if inspect.isawaitable(output):
                    output = asyncio.run(output)

                result[step_name] = output
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception(f"Workflow step {step_name} failed: {e}")
                result[step_name] = {"error": str(e)}
    finally:
        # NOTE: Previously the workflow auto-cleared the DB here to enforce
        # a stateless operation. That behavior was removed so that stored
        # tasks/events remain persistently available until an explicit
        # user action (Clear DB) is taken from the UI or API.
        pass
    
    return result


def build_workflow() -> Workflow:
    """Build the WorkFlowGenie workflow."""
    w = Workflow("workflowgenie")
    w.set_entrypoint(task_extractor_agent)
    w.add_step(planner_agent)
    w.add_step(reminder_agent)
    w.add_step(reporter_agent)
    return w
