import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pawpal_ai import KnowledgeBase, PawPalAICoach
from pawpal_system import (
    ActivityService,
    CareScoreService,
    CareTargetService,
    PetService,
    TaskService,
)


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_PATH = ROOT / "knowledge_base" / "pet_care_knowledge.json"


@pytest.fixture(autouse=True)
def reset_all():
    PetService._pets = {}
    CareTargetService._targets = {}
    ActivityService._activities = {}
    CareScoreService._scores = {}
    TaskService._tasks = {}
    yield


@pytest.fixture
def services():
    pet_service = PetService()
    target_service = CareTargetService()
    activity_service = ActivityService()
    score_service = CareScoreService(activity_service, target_service)
    task_service = TaskService()
    return {
        "pet_service": pet_service,
        "target_service": target_service,
        "activity_service": activity_service,
        "score_service": score_service,
        "task_service": task_service,
    }


def build_coach(services, tmp_path):
    return PawPalAICoach(
        services["pet_service"],
        services["target_service"],
        services["activity_service"],
        services["score_service"],
        services["task_service"],
        knowledge_base_path=KNOWLEDGE_PATH,
        audit_log_path=tmp_path / "pawpal_ai_runs.jsonl",
    )


@pytest.fixture
def local_tmp_path(request):
    base = ROOT / "logs" / "pytest_tmp" / request.node.name
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)
    yield base
    shutil.rmtree(base, ignore_errors=True)


def make_pet(services, name="Buddy", species="dog"):
    return services["pet_service"].create(user_id="user-1", name=name, species=species)


def set_targets(services, pet_id):
    return services["target_service"].set_targets(
        pet_id=pet_id,
        daily_meals=2,
        daily_walk_min=30,
        grooming_interval_days=14,
        vet_interval_days=180,
    )


def test_retrieval_prefers_species_relevant_exercise_doc():
    kb = KnowledgeBase(KNOWLEDGE_PATH)
    results = kb.search(
        query="How should I improve my dog's daily walk routine?",
        species="dog",
        context_tags=["exercise", "walk", "planning"],
    )

    assert results, "knowledge search should return at least one document"
    assert results[0].doc_id == "dog_exercise_basics"


def test_guardrail_blocks_emergency_health_prompt(services, local_tmp_path):
    coach = build_coach(services, local_tmp_path)
    pet = make_pet(services)
    set_targets(services, pet.id)

    plan = coach.generate_plan(
        pet_id=pet.id,
        question="My dog ate something toxic and is vomiting. What should I do?",
        owner_pet_ids=[pet.id],
    )

    assert plan.status == "emergency"
    assert any("veterinarian" in alert.lower() for alert in plan.alerts)
    assert plan.actions[0].priority == "critical"
    assert plan.actions[0].task_type is None


def test_plan_uses_pet_data_and_generates_supported_actions(services, local_tmp_path):
    coach = build_coach(services, local_tmp_path)
    pet = make_pet(services, species="dog")
    set_targets(services, pet.id)

    services["activity_service"].log_activity(pet.id, "feeding", {}, date.today())

    plan = coach.generate_plan(
        pet_id=pet.id,
        question="Summarize the biggest routine gaps and suggest the next best tasks.",
        owner_pet_ids=[pet.id],
    )

    action_types = {action.task_type for action in plan.actions if action.task_type}

    assert plan.status == "normal"
    assert plan.confidence >= 0.5
    assert any("care score" in finding.lower() for finding in plan.findings)
    assert "walk" in action_types
    assert all(action.citations for action in plan.actions), "each action should cite retrieved knowledge"
    assert all(action.evidence for action in plan.actions), "each action should carry system evidence"


def test_apply_task_suggestions_creates_tasks_once(services, local_tmp_path):
    coach = build_coach(services, local_tmp_path)
    pet = make_pet(services, species="dog")
    set_targets(services, pet.id)

    plan = coach.generate_plan(
        pet_id=pet.id,
        question="Plan the next best routine-care tasks for this dog.",
        owner_pet_ids=[pet.id],
    )

    first_apply = coach.apply_task_suggestions(plan)
    second_apply = coach.apply_task_suggestions(plan)

    assert first_apply.created_tasks, "the first application should create at least one task"
    assert not second_apply.created_tasks, "the second application should avoid duplicate tasks"
    assert second_apply.skipped_messages, "duplicate prevention should explain why tasks were skipped"


def test_generate_plan_writes_audit_log(services, local_tmp_path):
    coach = build_coach(services, local_tmp_path)
    pet = make_pet(services, species="cat")
    set_targets(services, pet.id)

    plan = coach.generate_plan(
        pet_id=pet.id,
        question="Explain what needs attention this week.",
        owner_pet_ids=[pet.id],
    )

    log_path = local_tmp_path / "pawpal_ai_runs.jsonl"
    assert log_path.exists()

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[-1])

    assert payload["request_id"] == plan.request_id
    assert payload["pet_id"] == pet.id
    assert "confidence" in payload
