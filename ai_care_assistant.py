"""AI Care Assistant - the agentic half of PawPal+'s AI extension.

Pipeline: retrieve breed/age/activity-matched care guidelines (care_guidelines.py)
-> ask Gemini to draft care tasks grounded in those guidelines (structured JSON
output, guardrail layer 1) -> validate the structural shape of each task
(guardrail layer 2) -> check the draft against the REAL scheduler's existing
Scheduler.detectConflicts() -> if conflicts are found, feed them back to Gemini
and retry (bounded) -> if still conflicting after the retry budget, apply one
local nudge pass -> return whatever plan is usable, with any remaining
conflicts flagged rather than hidden.

Every step is logged to ai_care_assistant.log (and the console) so the
assistant's behavior can be audited after the fact.
"""
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from dotenv import load_dotenv

from pawpal_system import Pet, Scheduler, Task
from care_guidelines import retrieve_guidelines

logger = logging.getLogger("pawpal.ai_care_assistant")


def _configure_logging(log_path: str = "ai_care_assistant.log") -> None:
    """Idempotent: safe to call multiple times (e.g. on every Streamlit rerun)."""
    if logger.handlers:
        return
    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)


_configure_logging()


class AIAssistantConfigError(Exception):
    """Raised when the assistant cannot be configured (e.g. missing API key)."""


class AIAssistantError(Exception):
    """Raised when a Gemini call fails or returns something unusable."""


DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

ALLOWED_FREQUENCIES = {"one-time", "daily", "weekly", "monthly", "yearly"}
ALLOWED_PRIORITIES = {"low", "medium", "high"}
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

CARE_PLAN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "tasks": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "description": {"type": "STRING"},
                    "time": {"type": "STRING", "description": "24-hour HH:MM, today"},
                    "duration": {"type": "INTEGER"},
                    "frequency": {
                        "type": "STRING",
                        "enum": ["one-time", "daily", "weekly", "monthly", "yearly"],
                    },
                    "priority": {"type": "STRING", "enum": ["low", "medium", "high"]},
                    "rationale": {
                        "type": "STRING",
                        "description": "Which retrieved guideline justified this task's timing/duration/frequency",
                    },
                },
                "required": ["description", "time", "duration", "frequency", "priority", "rationale"],
            },
        }
    },
    "required": ["tasks"],
}


def _get_client():
    """Lazily construct the Gemini client. Raises AIAssistantConfigError if
    no API key is configured - never called at import time, so the rest of
    the app works fine with no key set."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise AIAssistantConfigError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add your "
            "Gemini API key from https://aistudio.google.com/apikey."
        )
    from google import genai
    from google.genai import types

    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=30_000))


def _build_system_prompt() -> str:
    return (
        "You are a care planning assistant for the PawPal+ pet care app. "
        "You will be given a pet's profile and a list of retrieved care guidelines. "
        "Ground every task's duration and frequency choice ONLY in the guidelines "
        "provided - do not invent breed facts that are not present in them. "
        "A pet with a 'high' activity level guideline should get longer and/or "
        "more frequent exercise tasks than one with a 'medium' or 'low' activity "
        "guideline. Propose times as plain 24-hour HH:MM for today. Never schedule "
        "two of your own proposed tasks at the exact same time for this pet. "
        "For every task, fill in 'rationale' by naming the specific guideline "
        "(its category and/or id) that justified your choice of duration/frequency. "
        "Respond only through the propose_care_tasks structure - no prose."
    )


def _build_user_prompt(pet: Pet, guidelines: list, existing_tasks_summary: str,
                        conflict_feedback: str = None) -> str:
    guideline_lines = "\n".join(
        f"- [{g['id']}] ({g['category']}) {g['guidance']} "
        f"(suggested duration: {g['suggested_duration_minutes']} min, "
        f"suggested frequency: {g['suggested_frequency']})"
        for g in guidelines
    ) or "(no specific guidelines matched - use conservative, generic care defaults)"

    prompt = (
        f"Pet profile:\n"
        f"- Name: {pet.name}\n"
        f"- Type: {pet.type}\n"
        f"- Breed: {pet.breed}\n"
        f"- Age: {pet.age}\n"
        f"- Activity level: {pet.activityLevel}\n"
        f"- Health info: {pet.healthInfo}\n\n"
        f"Retrieved care guidelines:\n{guideline_lines}\n\n"
        f"This pet's existing scheduled tasks (avoid obvious overlaps with these):\n"
        f"{existing_tasks_summary or '(no existing tasks)'}\n"
    )

    if conflict_feedback:
        prompt += (
            f"\nYour previous proposal conflicted with existing/other proposed "
            f"tasks as follows:\n{conflict_feedback}\n"
            f"Adjust the times of your proposed tasks to resolve these conflicts. "
            f"Keep guideline-informed durations/frequencies unchanged where possible."
        )

    return prompt


def validate_task_dict(d: dict):
    """Pure structural guardrail (no I/O). Returns (True, None) if d has all
    required fields in valid shapes, else (False, "<reason>")."""
    required = ["description", "time", "duration", "frequency", "priority", "rationale"]
    for key in required:
        if key not in d:
            return False, f"Missing required field '{key}'"

    if not isinstance(d["description"], str) or not d["description"].strip():
        return False, "description must be a non-empty string"

    if not isinstance(d["time"], str) or not TIME_RE.match(d["time"]):
        return False, f"time '{d['time']}' is not a valid HH:MM 24-hour time"

    if not isinstance(d["duration"], int) or isinstance(d["duration"], bool) or not (1 <= d["duration"] <= 480):
        return False, "duration must be an integer between 1 and 480 minutes"

    if d["frequency"] not in ALLOWED_FREQUENCIES:
        return False, f"frequency '{d['frequency']}' is not one of {ALLOWED_FREQUENCIES}"

    if d["priority"] not in ALLOWED_PRIORITIES:
        return False, f"priority '{d['priority']}' is not one of {ALLOWED_PRIORITIES}"

    if not isinstance(d["rationale"], str) or not d["rationale"].strip():
        return False, "rationale must be a non-empty string"

    return True, None


def _call_gemini_for_care_plan(client, pet: Pet, guidelines: list,
                                existing_tasks_summary: str,
                                conflict_feedback: str = None) -> dict:
    """One Gemini call. Returns the parsed {'tasks': [...]} dict, or raises
    AIAssistantError with a user-facing message on any failure."""
    from google.genai import types
    from google.genai import errors as genai_errors

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(pet, guidelines, existing_tasks_summary, conflict_feedback)

    logger.debug("System prompt: %s", system_prompt[:2000])
    logger.debug("User prompt: %s", user_prompt[:2000])

    try:
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=CARE_PLAN_SCHEMA,
            ),
        )
    except genai_errors.ClientError as e:
        logger.error("Gemini client error: %s", e, exc_info=True)
        raise AIAssistantError(f"Gemini rejected the request (invalid key or request): {e}") from e
    except genai_errors.ServerError as e:
        logger.error("Gemini server error: %s", e, exc_info=True)
        raise AIAssistantError(f"Gemini API is temporarily unavailable: {e}") from e
    except Exception as e:
        logger.error("Unexpected error calling Gemini: %s", e, exc_info=True)
        raise AIAssistantError(f"Unexpected AI assistant error: {e}") from e

    logger.info("Gemini response received for pet %s", pet.name)

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, dict) and "tasks" in parsed:
        return parsed

    text = getattr(response, "text", None)
    if text:
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "tasks" in data:
                return data
        except json.JSONDecodeError:
            pass

    raise AIAssistantError("Gemini did not return a structured care plan.")


def _construct_tasks_from_plan(pet: Pet, plan: dict, id_prefix: str) -> list:
    """Validate each task dict (guardrail layer 2) before constructing a real
    Task - invalid entries are skipped and logged, never raised."""
    tasks = []
    for i, task_dict in enumerate(plan.get("tasks", []), start=1):
        ok, reason = validate_task_dict(task_dict)
        if not ok:
            logger.warning("Skipping invalid AI-proposed task %r: %s", task_dict, reason)
            continue

        hour, minute = (int(part) for part in task_dict["time"].split(":"))
        task_time = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)

        tasks.append(
            Task(
                taskId=f"{id_prefix}_{i}",
                petId=pet.petId,
                description=task_dict["description"],
                time=task_time,
                frequency=task_dict["frequency"],
                priority=task_dict["priority"],
                duration=task_dict["duration"],
                completionStatus="pending",
            )
        )
    return tasks


def _check_conflicts_for_candidates(scheduler: Scheduler, candidate_tasks: list) -> list:
    """Reuses Scheduler.detectConflicts() against a throwaway copy of the task
    list - never mutates the real scheduler."""
    temp_scheduler = Scheduler(owner=scheduler.owner)
    temp_scheduler.tasks = scheduler.tasks + candidate_tasks
    return temp_scheduler.detectConflicts()


@dataclass
class CarePlanResult:
    success: bool
    tasks: list = field(default_factory=list)
    remaining_conflicts: list = field(default_factory=list)
    iterations_used: int = 0
    guideline_ids_used: list = field(default_factory=list)
    error: str = None


def generate_care_plan(pet: Pet, scheduler: Scheduler, max_iterations: int = 3) -> CarePlanResult:
    """Retrieve guidelines, draft a care plan with Gemini, self-check it
    against the real scheduler's conflict detection, and retry (feeding
    conflicts back to the model) up to max_iterations before returning the
    best plan found - flagging any conflicts it couldn't resolve."""
    guidelines = retrieve_guidelines(pet)
    guideline_ids = [g["id"] for g in guidelines]
    logger.info("Retrieved %d guideline(s) for %s: %s", len(guidelines), pet.name, guideline_ids)

    try:
        client = _get_client()
    except AIAssistantConfigError as e:
        logger.error("Configuration error: %s", e)
        return CarePlanResult(success=False, guideline_ids_used=guideline_ids, error=str(e))

    existing_tasks_summary = "\n".join(
        f"- {t.description} at {t.time.strftime('%H:%M')} ({t.priority} priority)"
        for t in pet.getTasks()
    )

    conflict_feedback = None
    best_tasks, best_conflicts = [], []

    for i in range(1, max_iterations + 1):
        try:
            plan = _call_gemini_for_care_plan(
                client, pet, guidelines, existing_tasks_summary, conflict_feedback
            )
        except AIAssistantError as e:
            logger.error("Attempt %d failed: %s", i, e)
            return CarePlanResult(
                success=False, iterations_used=i, guideline_ids_used=guideline_ids, error=str(e)
            )

        tasks = _construct_tasks_from_plan(pet, plan, id_prefix=f"ai_{pet.petId}_{i}")
        if not tasks:
            logger.warning("Attempt %d produced no valid tasks after validation", i)
            conflict_feedback = (
                "Your last response contained no valid tasks after validation; "
                "ensure every field matches the required schema exactly."
            )
            continue

        conflicts = _check_conflicts_for_candidates(scheduler, tasks)
        best_tasks, best_conflicts = tasks, conflicts

        if not conflicts:
            logger.info("Attempt %d produced a conflict-free plan for %s", i, pet.name)
            return CarePlanResult(
                success=True, tasks=tasks, iterations_used=i, guideline_ids_used=guideline_ids
            )

        logger.info("Attempt %d has %d conflict(s), retrying: %s", i, len(conflicts), conflicts)
        conflict_feedback = "\n".join(conflicts)

    # Retry budget exhausted while still conflicting - one bounded local nudge
    # pass: push each candidate forward past its own duration until its time
    # no longer collides with an existing task OR an already-placed candidate.
    # No further LLM calls are made here.
    occupied_times = {t.time for t in scheduler.tasks if t.completionStatus == "pending"}
    nudged_tasks = []
    for t in best_tasks:
        while t.time in occupied_times:
            t.time = t.time + timedelta(minutes=t.duration + 5)
        occupied_times.add(t.time)
        nudged_tasks.append(t)

    final_conflicts = _check_conflicts_for_candidates(scheduler, nudged_tasks)
    logger.info(
        "Exhausted %d iterations for %s; local nudge pass left %d conflict(s)",
        max_iterations, pet.name, len(final_conflicts),
    )
    return CarePlanResult(
        success=True,
        tasks=nudged_tasks,
        remaining_conflicts=final_conflicts,
        iterations_used=max_iterations,
        guideline_ids_used=guideline_ids,
    )
