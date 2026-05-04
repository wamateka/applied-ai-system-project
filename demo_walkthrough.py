from __future__ import annotations

from datetime import date, timedelta

from pawpal_ai import CarePlanResult, PawPalAICoach
from pawpal_system import (
    ActivityService,
    CareScoreService,
    CareTargetService,
    PetService,
    TaskService,
    UserService,
    sort_by_urgency,
)


TODAY = date.today()


def print_section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def print_plan(plan: CarePlanResult) -> None:
    print(f"AI status    : {plan.status}")
    print(f"Confidence   : {int(plan.confidence * 100)}%")
    print(f"Summary      : {plan.summary}")

    if plan.findings:
        print("Findings     :")
        for finding in plan.findings:
            print(f"  - {finding}")

    if plan.alerts:
        print("Alerts       :")
        for alert in plan.alerts:
            print(f"  - {alert}")

    if plan.retrieved_knowledge:
        print("Knowledge    :")
        for item in plan.retrieved_knowledge[:3]:
            print(f"  - {item.doc_id}: {item.title} (score {item.score:.1f})")

    if plan.actions:
        print("AI response  :")
        for action in plan.actions:
            due = action.due_date.isoformat() if action.due_date else "review only"
            mode = action.task_type or "guidance only"
            print(
                f"  - {action.title} | priority={action.priority} | mode={mode} | due={due}"
            )
            print(f"    rationale: {action.rationale}")


def print_pending_tasks(task_service: TaskService, pet_id: str, pet_name: str) -> None:
    pending = sort_by_urgency(task_service.get_all_for_pets([pet_id], status="pending"), TODAY)
    print(f"Pending tasks for {pet_name}:")
    if not pending:
        print("  (none)")
        return
    for task in pending:
        time_part = f" @{task.scheduled_time}" if task.scheduled_time else ""
        recur = (
            f", recur={task.recurrence}"
            + (
                f" every {task.recurrence_interval_days}d"
                if task.recurrence == "custom"
                else ""
            )
            if task.recurrence != "none"
            else ""
        )
        print(
            f"  - {task.task_type} on {task.scheduled_date}{time_part} "
            f"[{task.status}{recur}]"
        )


def seed_demo_state() -> dict[str, object]:
    user_service = UserService()
    pet_service = PetService()
    target_service = CareTargetService()
    activity_service = ActivityService()
    score_service = CareScoreService(activity_service, target_service)
    task_service = TaskService()

    owner = user_service.register(
        name="Jordan Lee",
        email="jordan@example.com",
        password="demo-password",
    )

    max_pet = pet_service.create(
        owner.id,
        name="Max",
        species="dog",
        breed="Golden Retriever",
        weight_kg=31.5,
        age_years=4,
    )
    luna_pet = pet_service.create(
        owner.id,
        name="Luna",
        species="cat",
        breed="Siamese",
        weight_kg=4.3,
        age_years=5,
    )
    pepper_pet = pet_service.create(
        owner.id,
        name="Pepper",
        species="dog",
        breed="Border Collie",
        weight_kg=10.2,
        age_years=2,
    )

    target_service.set_targets(
        max_pet.id,
        daily_meals=3,
        daily_walk_min=90,
        grooming_interval_days=7,
        vet_interval_days=120,
    )
    target_service.set_targets(
        luna_pet.id,
        daily_meals=2,
        daily_walk_min=0,
        grooming_interval_days=14,
        vet_interval_days=365,
    )
    target_service.set_targets(
        pepper_pet.id,
        daily_meals=4,
        daily_walk_min=120,
        grooming_interval_days=5,
        vet_interval_days=90,
    )

    # Max: underfed today, not enough walking, overdue grooming, upcoming conflict
    activity_service.log_activity(max_pet.id, "feeding", {}, TODAY)
    activity_service.log_activity(max_pet.id, "walk", {"duration_min": 20}, TODAY)
    activity_service.log_activity(max_pet.id, "grooming", {}, TODAY - timedelta(days=10))
    activity_service.log_activity(max_pet.id, "vet_visit", {}, TODAY - timedelta(days=45))
    task_service.create(max_pet.id, "walk", TODAY + timedelta(days=1), scheduled_time="08:00", recurrence="daily")
    task_service.create(max_pet.id, "grooming", TODAY - timedelta(days=2))
    task_service.create(max_pet.id, "feeding", TODAY + timedelta(days=2), scheduled_time="10:00")

    # Luna: feeding gap, overdue vet, overloaded near-term schedule with a clash
    activity_service.log_activity(luna_pet.id, "feeding", {}, TODAY)
    activity_service.log_activity(luna_pet.id, "grooming", {}, TODAY - timedelta(days=5))
    activity_service.log_activity(luna_pet.id, "vet_visit", {}, TODAY - timedelta(days=400))
    task_service.create(luna_pet.id, "feeding", TODAY, scheduled_time="09:00")
    task_service.create(luna_pet.id, "grooming", TODAY + timedelta(days=2), scheduled_time="10:00")
    task_service.create(luna_pet.id, "walk", TODAY + timedelta(days=2), scheduled_time="10:00")
    task_service.create(luna_pet.id, "feeding", TODAY + timedelta(days=2), scheduled_time="10:20")
    task_service.create(luna_pet.id, "feeding", TODAY + timedelta(days=2), scheduled_time="11:00")
    task_service.create(luna_pet.id, "feeding", TODAY + timedelta(days=2), scheduled_time="12:00")
    task_service.create(luna_pet.id, "feeding", TODAY + timedelta(days=2), scheduled_time="13:00")
    task_service.create(luna_pet.id, "feeding", TODAY + timedelta(days=2), scheduled_time="14:00")

    # Pepper: enough context for the emergency guardrail example
    activity_service.log_activity(pepper_pet.id, "feeding", {}, TODAY)
    activity_service.log_activity(pepper_pet.id, "feeding", {}, TODAY)
    activity_service.log_activity(pepper_pet.id, "walk", {"duration_min": 35}, TODAY)
    activity_service.log_activity(pepper_pet.id, "grooming", {}, TODAY - timedelta(days=2))
    activity_service.log_activity(pepper_pet.id, "vet_visit", {}, TODAY - timedelta(days=30))

    coach = PawPalAICoach(
        pet_service=pet_service,
        care_target_service=target_service,
        activity_service=activity_service,
        care_score_service=score_service,
        task_service=task_service,
    )

    return {
        "owner": owner,
        "pets": {
            "max": max_pet,
            "luna": luna_pet,
            "pepper": pepper_pet,
        },
        "coach": coach,
        "task_service": task_service,
        "all_pet_ids": [max_pet.id, luna_pet.id, pepper_pet.id],
    }


def main() -> None:
    state = seed_demo_state()
    pets = state["pets"]
    coach: PawPalAICoach = state["coach"]  # type: ignore[assignment]
    task_service: TaskService = state["task_service"]  # type: ignore[assignment]
    all_pet_ids: list[str] = state["all_pet_ids"]  # type: ignore[assignment]

    print_section("PawPal+ AI Care Coach Demo Walkthrough")
    print("This scripted run shows three end-to-end examples:")
    print("1. Weekly planning and AI task application")
    print("2. Schedule-aware reasoning for backlog and conflicts")
    print("3. Emergency guardrail behavior")

    # Example 1
    print_section("Example 1: Weekly planning for Max")
    print("User input   : Explain what needs attention this week and suggest the next best routine-care tasks.")
    max_plan = coach.generate_plan(
        pet_id=pets["max"].id,
        question="Explain what needs attention this week and suggest the next best routine-care tasks.",
        owner_pet_ids=all_pet_ids,
        horizon_days=7,
    )
    print_plan(max_plan)
    max_apply = coach.apply_task_suggestions(max_plan)
    print("System action:")
    print(f"  - Created {len(max_apply.created_tasks)} task(s) from approved AI suggestions.")
    for message in max_apply.skipped_messages:
        print(f"  - {message}")
    print_pending_tasks(task_service, pets["max"].id, pets["max"].name)

    # Example 2
    print_section("Example 2: Schedule cleanup for Luna")
    print("User input   : Summarize Luna's biggest routine gaps and tell me whether I should reschedule anything.")
    luna_plan = coach.generate_plan(
        pet_id=pets["luna"].id,
        question="Summarize Luna's biggest routine gaps and tell me whether I should reschedule anything.",
        owner_pet_ids=all_pet_ids,
        horizon_days=7,
    )
    print_plan(luna_plan)
    print("System action:")
    print("  - No automatic rescheduling occurs. The AI surfaces conflicts and recommended next actions for the human to review.")
    print_pending_tasks(task_service, pets["luna"].id, pets["luna"].name)

    # Example 3
    print_section("Example 3: Emergency boundary for Pepper")
    print("User input   : Pepper ate something toxic and is vomiting. What should I do?")
    pepper_plan = coach.generate_plan(
        pet_id=pets["pepper"].id,
        question="Pepper ate something toxic and is vomiting. What should I do?",
        owner_pet_ids=all_pet_ids,
        horizon_days=7,
    )
    print_plan(pepper_plan)
    print("System action:")
    print("  - The emergency guardrail stops routine planning and returns a veterinary handoff instead of normal task suggestions.")

    print_section("End of Demo")
    print("Run this script with: python demo_walkthrough.py")


if __name__ == "__main__":
    main()
