import sys
import os
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pawpal_system import Owner, Pet, Task, Scheduler
from ai_care_assistant import (
    validate_task_dict,
    _construct_tasks_from_plan,
    _check_conflicts_for_candidates,
    generate_care_plan,
    AIAssistantConfigError,
)


def _make_owner_scheduler_pet():
    owner = Owner(ownerId="1", name="Sarah", contactInfo="sarah@example.com")
    scheduler = Scheduler(owner=owner)
    owner.scheduler = scheduler
    pet = Pet(petId="1", name="Max", type="dog", breed="Labrador Retriever",
              age=4, healthInfo="Healthy", activityLevel="high", scheduler=scheduler)
    owner.addPet(pet)
    return owner, scheduler, pet


def _valid_task_dict(time="09:00", description="Morning walk"):
    return {
        "description": description,
        "time": time,
        "duration": 30,
        "frequency": "daily",
        "priority": "high",
        "rationale": "ex-high-working-01: high-activity breed needs a long daily walk",
    }


def _mock_response(tasks_payload):
    return SimpleNamespace(parsed={"tasks": tasks_payload}, text=None)


# --- Guardrail: validate_task_dict --------------------------------------------------

def test_validate_task_dict_accepts_well_formed_task():
    ok, reason = validate_task_dict(_valid_task_dict())
    assert ok is True
    assert reason is None
    print("[PASS] test_validate_task_dict_accepts_well_formed_task passed")


def test_validate_task_dict_rejects_bad_time_format():
    d = _valid_task_dict()
    d["time"] = "9:00am"
    ok, reason = validate_task_dict(d)
    assert ok is False
    print("[PASS] test_validate_task_dict_rejects_bad_time_format passed")


def test_validate_task_dict_rejects_bad_enum_priority():
    d = _valid_task_dict()
    d["priority"] = "urgent"
    ok, reason = validate_task_dict(d)
    assert ok is False
    print("[PASS] test_validate_task_dict_rejects_bad_enum_priority passed")


def test_validate_task_dict_rejects_nonpositive_duration():
    d = _valid_task_dict()
    d["duration"] = 0
    ok, reason = validate_task_dict(d)
    assert ok is False
    print("[PASS] test_validate_task_dict_rejects_nonpositive_duration passed")


def test_validate_task_dict_rejects_missing_key():
    d = _valid_task_dict()
    del d["rationale"]
    ok, reason = validate_task_dict(d)
    assert ok is False
    print("[PASS] test_validate_task_dict_rejects_missing_key passed")


# --- _construct_tasks_from_plan -------------------------------------------------------

def test_construct_tasks_from_plan_skips_invalid_and_builds_valid():
    _, _, pet = _make_owner_scheduler_pet()
    plan = {"tasks": [_valid_task_dict(), {"description": "bad"}]}
    tasks = _construct_tasks_from_plan(pet, plan, id_prefix="ai_1_1")

    assert len(tasks) == 1
    assert tasks[0].petId == pet.petId
    assert tasks[0].time.strftime("%H:%M") == "09:00"
    print("[PASS] test_construct_tasks_from_plan_skips_invalid_and_builds_valid passed")


# --- _check_conflicts_for_candidates --------------------------------------------------

def test_check_conflicts_for_candidates_reuses_detect_conflicts_without_mutating_real_scheduler():
    owner, scheduler, pet = _make_owner_scheduler_pet()
    existing = Task(taskId="1", petId=pet.petId, description="Breakfast",
                     time=__import__("datetime").datetime.now().replace(hour=7, minute=0, second=0, microsecond=0),
                     frequency="daily", priority="high", duration=10, completionStatus="pending")
    owner.addTask(existing)

    plan = {"tasks": [_valid_task_dict(time="07:00", description="Playtime")]}
    candidates = _construct_tasks_from_plan(pet, plan, id_prefix="ai_1_1")

    conflicts = _check_conflicts_for_candidates(scheduler, candidates)
    assert len(conflicts) > 0
    assert len(scheduler.tasks) == 1  # real scheduler untouched
    print("[PASS] test_check_conflicts_for_candidates_reuses_detect_conflicts_without_mutating_real_scheduler passed")


# --- generate_care_plan (mocked Gemini client) ----------------------------------------

@patch("ai_care_assistant._get_client")
def test_generate_care_plan_success_on_first_try(mock_get_client):
    owner, scheduler, pet = _make_owner_scheduler_pet()

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_response(
        [_valid_task_dict(time="09:00")]
    )
    mock_get_client.return_value = mock_client

    result = generate_care_plan(pet, scheduler)

    assert result.success is True
    assert len(result.tasks) == 1
    assert result.iterations_used == 1
    assert mock_client.models.generate_content.call_count == 1
    print("[PASS] test_generate_care_plan_success_on_first_try passed")


@patch("ai_care_assistant._get_client")
def test_generate_care_plan_retries_after_conflict_then_succeeds(mock_get_client):
    owner, scheduler, pet = _make_owner_scheduler_pet()
    existing = Task(taskId="1", petId=pet.petId, description="Breakfast",
                     time=__import__("datetime").datetime.now().replace(hour=9, minute=0, second=0, microsecond=0),
                     frequency="daily", priority="high", duration=10, completionStatus="pending")
    owner.addTask(existing)

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _mock_response([_valid_task_dict(time="09:00", description="Conflicting walk")]),
        _mock_response([_valid_task_dict(time="10:00", description="Clean walk")]),
    ]
    mock_get_client.return_value = mock_client

    result = generate_care_plan(pet, scheduler)

    assert result.success is True
    assert result.iterations_used == 2
    assert mock_client.models.generate_content.call_count == 2

    second_call_kwargs = mock_client.models.generate_content.call_args_list[1].kwargs
    assert "conflict" in second_call_kwargs["contents"].lower()
    print("[PASS] test_generate_care_plan_retries_after_conflict_then_succeeds passed")


@patch("ai_care_assistant._get_client")
def test_generate_care_plan_flags_remaining_conflicts_after_max_iterations(mock_get_client):
    owner, scheduler, pet = _make_owner_scheduler_pet()
    existing = Task(taskId="1", petId=pet.petId, description="Breakfast",
                     time=__import__("datetime").datetime.now().replace(hour=9, minute=0, second=0, microsecond=0),
                     frequency="daily", priority="high", duration=10, completionStatus="pending")
    owner.addTask(existing)

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_response(
        [_valid_task_dict(time="09:00", description="Always conflicting")]
    )
    mock_get_client.return_value = mock_client

    result = generate_care_plan(pet, scheduler, max_iterations=3)

    assert result.success is True
    assert result.iterations_used == 3
    assert len(result.tasks) == 1
    assert mock_client.models.generate_content.call_count == 3
    print("[PASS] test_generate_care_plan_flags_remaining_conflicts_after_max_iterations passed")


@patch("ai_care_assistant._get_client")
def test_generate_care_plan_handles_malformed_tool_output(mock_get_client):
    owner, scheduler, pet = _make_owner_scheduler_pet()

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_response(
        [{"description": "x"}]  # missing required fields
    )
    mock_get_client.return_value = mock_client

    result = generate_care_plan(pet, scheduler, max_iterations=2)

    # Never raises, never constructs a bad Task - just reports no usable plan.
    assert result.tasks == []
    assert mock_client.models.generate_content.call_count == 2
    print("[PASS] test_generate_care_plan_handles_malformed_tool_output passed")


@patch("google.genai.Client")
def test_generate_care_plan_handles_missing_api_key(mock_client_cls, monkeypatch):
    owner, scheduler, pet = _make_owner_scheduler_pet()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("ai_care_assistant.load_dotenv", lambda *a, **k: None)

    result = generate_care_plan(pet, scheduler)

    assert result.success is False
    assert "GEMINI_API_KEY" in result.error
    mock_client_cls.assert_not_called()
    print("[PASS] test_generate_care_plan_handles_missing_api_key passed")
