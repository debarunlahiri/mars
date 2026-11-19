"""Orchestrator/Planner: turns the question into independent research sub-tasks."""

from __future__ import annotations

from ..prompts import ATTACHED_NOTE, PLANNER_SYSTEM, stamped
from ..schemas import PlanOut, ResearchTask
from ..workflow.deps import Deps


async def plan(deps: Deps, question: str, document_ids: list[str] | None = None) -> list[ResearchTask]:
    max_tasks = deps.settings.max_tasks
    system = PLANNER_SYSTEM.format(max_tasks=max_tasks)
    user = f"Research question: {question}"
    if document_ids and deps.docs is not None:
        system += ATTACHED_NOTE
        user += f"\n\nAttached documents (name and opening text):\n{await deps.docs.outline(document_ids)}"
    out = await deps.fast.structured(PlanOut, stamped(system), user)
    tasks: list[ResearchTask] = []
    seen: set[str] = set()
    for t in out.tasks:
        query = " ".join(t.query.split())
        key = query.casefold()
        if query and key not in seen:  # drop empty and duplicate queries
            seen.add(key)
            tasks.append(ResearchTask(id=f"t{len(tasks) + 1}", query=query, rationale=t.rationale))
    # Never return an empty plan: fall back to researching the question itself.
    return tasks[:max_tasks] or [ResearchTask(id="t1", query=question, rationale="fallback")]
