from datetime import date, timedelta

from pawpal_ai import PawPalAICoach
from pawpal_system import (
    ActivityService,
    CareScoreService,
    UserService,
    PetService,
    CareTargetService,
    TaskService,
    sort_by_urgency,
    sort_by_care_score,
    sort_by_completion_gap,
)

# --- Setup services ---
user_service   = UserService()
pet_service    = PetService()
target_service = CareTargetService()
activity_service = ActivityService()
score_service = CareScoreService(activity_service, target_service)
task_service   = TaskService()

TODAY = date.today()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def print_tasks(label: str, tasks: list) -> None:
    print(f"\n  {'-' * 41}")
    print(f"  {label}")
    print(f"  {'-' * 41}")
    if not tasks:
        print("  (none)")
        return
    for t in tasks:
        days_diff = (t.scheduled_date - TODAY).days
        if days_diff < 0:
            badge = f"OVERDUE {abs(days_diff)}d"
        elif days_diff == 0:
            badge = "TODAY"
        else:
            badge = f"in {days_diff}d"

        recur = {
            "daily":  "[daily]",
            "weekly": "[weekly]",
            "custom": f"[every {t.recurrence_interval_days}d]",
        }.get(t.recurrence, "")

        time_part = f" @{t.scheduled_time}" if t.scheduled_time else ""
        print(
            f"  [{t.status:7}] {t.task_type:12} | {t.scheduled_date}{time_part}"
            f"  ({badge})"
            + (f"  {recur}" if recur else "")
        )


def print_targets(pet_name: str, pet_id: str) -> None:
    t = target_service.get_targets(pet_id)
    print(f"  Pet       : {pet_name}")
    print(f"  Feeding   : {t.daily_meals} meal(s) per day")
    print(f"  Exercise  : {t.daily_walk_min} min of walking per day")
    print(f"  Grooming  : every {t.grooming_interval_days} day(s)")
    print(f"  Vet Visit : every {t.vet_interval_days} day(s)")
    print()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    # --- Create owner ---
    owner = user_service.register(
        name="Alex Rivera",
        email="alex@pawpal.com",
        password="securepassword123",
    )
    print("=" * 45)
    print(f"  Owner registered: {owner.name} ({owner.email})")
    print("=" * 45)

    # --- Create pets ---
    max_    = pet_service.create(owner.id, "Max",    "dog",    "Golden Retriever", 32.0, 3)
    luna    = pet_service.create(owner.id, "Luna",   "cat",    "Siamese",           4.2, 5)
    biscuit = pet_service.create(owner.id, "Biscuit","rabbit", "Holland Lop",       1.8, 7)
    pepper  = pet_service.create(owner.id, "Pepper", "dog",    "Border Collie",    10.5, 1)

    pets = [max_, luna, biscuit, pepper]
    print(f"\n  {len(pets)} pets created for {owner.name}:")
    for p in pets:
        print(f"    - {p.name} ({p.breed}, {p.age_years}yr, {p.weight_kg}kg)")

    # --- Set care targets (Max: daily reset, Pepper: weekly reset) ---
    target_service.set_targets(max_.id,    daily_meals=3, daily_walk_min=90,  grooming_interval_days=7,  vet_interval_days=180, reset_period="daily")
    target_service.set_targets(luna.id,    daily_meals=2, daily_walk_min=0,   grooming_interval_days=14, vet_interval_days=365)
    target_service.set_targets(biscuit.id, daily_meals=2, daily_walk_min=20,  grooming_interval_days=10, vet_interval_days=90)
    target_service.set_targets(pepper.id,  daily_meals=4, daily_walk_min=120, grooming_interval_days=5,  vet_interval_days=90,  reset_period="weekly")

    print()
    print("=" * 45)
    print("  Care Targets")
    print("=" * 45)
    print()
    for pet in pets:
        print_targets(pet.name, pet.id)

    # --- Upsert test (Max vet interval updated) ---
    print("  [Testing upsert] Updating Max's vet interval to 120 days...")
    target_service.set_targets(max_.id, daily_meals=3, daily_walk_min=90, grooming_interval_days=7, vet_interval_days=120, reset_period="daily")
    print()
    print("  Max's targets after update:")
    print_targets(max_.name, max_.id)

    # =========================================================================
    # Task scheduling — added deliberately out of chronological order
    # =========================================================================
    print("=" * 45)
    print("  Scheduling tasks (out of order)")
    print("=" * 45)

    # Future tasks
    task_service.create(max_.id,    "walk",      TODAY + timedelta(days=5),  scheduled_time="08:00", recurrence="daily")
    task_service.create(luna.id,    "grooming",  TODAY + timedelta(days=12))
    task_service.create(biscuit.id, "vet_visit", TODAY + timedelta(days=3),  scheduled_time="10:30")
    task_service.create(pepper.id,  "feeding",   TODAY + timedelta(days=1),  scheduled_time="07:00", recurrence="daily")
    task_service.create(max_.id,    "vet_visit", TODAY + timedelta(days=60))
    task_service.create(luna.id,    "feeding",   TODAY + timedelta(days=2))

    # Today
    task_service.create(pepper.id,  "grooming",  TODAY, scheduled_time="09:00")
    task_service.create(biscuit.id, "feeding",   TODAY)

    # Overdue (past dates — added last to ensure sort is not insertion-order)
    task_service.create(max_.id,    "grooming",  TODAY - timedelta(days=4))
    task_service.create(pepper.id,  "walk",      TODAY - timedelta(days=1),  scheduled_time="08:30", recurrence="weekly")
    task_service.create(luna.id,    "vet_visit", TODAY - timedelta(days=10))
    task_service.create(biscuit.id, "walk",      TODAY - timedelta(days=2),  scheduled_time="11:00")

    all_pet_ids = [max_.id, luna.id, biscuit.id, pepper.id]

    # ── 1. Sort by urgency (all pets, all statuses) ───────────────────────
    all_tasks = task_service.get_all_for_pets(all_pet_ids)
    print_tasks("Sort: URGENCY  |  Filter: all pets, all statuses",
                sort_by_urgency(all_tasks, TODAY))

    # ── 2. Sort by care score (simulate scores: pepper lowest) ────────────
    score_map = {
        max_.id:    85,
        luna.id:    72,
        biscuit.id: 60,
        pepper.id:  45,   # lowest → should surface first
    }
    print_tasks("Sort: CARE SCORE (lowest score first)  |  Filter: all pets",
                sort_by_care_score(all_tasks, score_map))

    # ── 3. Sort by completion gap (biscuit most behind on targets) ────────
    gap_map = {
        max_.id:    0.10,
        luna.id:    0.30,
        biscuit.id: 0.85,  # biggest gap → surfaces first
        pepper.id:  0.50,
    }
    print_tasks("Sort: COMPLETION GAP (biggest gap first)  |  Filter: all pets",
                sort_by_completion_gap(all_tasks, gap_map))

    # ── 4. Filter: pending tasks only, sorted by urgency ──────────────────
    pending_tasks = task_service.get_all_for_pets(all_pet_ids, status="pending")
    print_tasks("Sort: URGENCY  |  Filter: status=pending",
                sort_by_urgency(pending_tasks, TODAY))

    # ── 5. Filter: single pet (Luna), all statuses ────────────────────────
    luna_tasks = task_service.get_all_for_pets([luna.id])
    print_tasks("Sort: URGENCY  |  Filter: pet=Luna",
                sort_by_urgency(luna_tasks, TODAY))

    # ── 6. Filter: dogs only (Max + Pepper), pending, urgency ─────────────
    dog_ids   = [max_.id, pepper.id]
    dog_tasks = task_service.get_all_for_pets(dog_ids, status="pending")
    print_tasks("Sort: URGENCY  |  Filter: dogs only (Max + Pepper), status=pending",
                sort_by_urgency(dog_tasks, TODAY))

    # ── 7. Complete a recurring task — verify next occurrence spawned ──────
    print("\n  " + "-" * 41)
    print("  Recurring task test")
    print("  " + "-" * 41)
    pepper_walk = next(
        t for t in task_service.get_all_for_pets([pepper.id])
        if t.task_type == "walk" and t.status == "pending"
    )
    print(f"  Completing Pepper's walk ({pepper_walk.scheduled_date}, {pepper_walk.recurrence}) ...")
    next_task = task_service.complete(pepper_walk.id)
    print(f"  Status now : {pepper_walk.status}")
    if next_task:
        print(f"  Next task  : {next_task.task_type} on {next_task.scheduled_date}  (parent_id match: {next_task.parent_task_id == pepper_walk.id})")

    # ── 8. Target auto-reset demo ──────────────────────────────────────────
    print("\n  " + "-" * 41)
    print("  Target auto-reset test")
    print("  " + "-" * 41)

    # Mark Max (daily) and Pepper (weekly) as achieved
    target_service.mark_achieved(max_.id)
    target_service.mark_achieved(pepper.id)
    print(f"  Max status    : {target_service.get_targets(max_.id).status}  (reset_period=daily)")
    print(f"  Pepper status : {target_service.get_targets(pepper.id).status}  (reset_period=weekly)")

    # Simulate next day — Max's daily target should reset
    next_day = TODAY + timedelta(days=1)
    reset_daily = target_service.check_and_reset(max_.id, today=next_day)
    print(f"\n  After 1 day  (simulated {next_day}):")
    print(f"    Max reset  -> {target_service.get_targets(max_.id).status}"
          + ("  [auto-reset]" if reset_daily else "  [no change]"))
    no_reset = target_service.check_and_reset(pepper.id, today=next_day)
    print(f"    Pepper     -> {target_service.get_targets(pepper.id).status}"
          + ("  [auto-reset]" if no_reset else "  [no change, needs 7 days]"))

    # Simulate 7 days later — Pepper's weekly target should now reset
    week_later = TODAY + timedelta(days=7)
    reset_weekly = target_service.check_and_reset(pepper.id, today=week_later)
    print(f"\n  After 7 days (simulated {week_later}):")
    print(f"    Pepper reset -> {target_service.get_targets(pepper.id).status}"
          + ("  [auto-reset]" if reset_weekly else "  [no change]"))

    # Bulk reset — check all targets at once
    print(f"\n  Bulk check_and_reset_all at {week_later}:")
    bulk = target_service.check_and_reset_all(today=week_later)
    print(f"    {len(bulk)} target(s) reset this cycle.")

    # ── 9. Conflict detection ──────────────────────────────────────────────
    print("\n  " + "-" * 41)
    print("  Conflict detection (7-day window)")
    print("  " + "-" * 41)
    # Same-pet duplicate: two grooming sessions for Max on the same day
    task_service.create(max_.id, "grooming", TODAY + timedelta(days=2), scheduled_time="09:00")
    task_service.create(max_.id, "grooming", TODAY + timedelta(days=2), scheduled_time="09:20")

    # Cross-pet same-time clash: Max and Luna both at 10:00 on same day
    task_service.create(max_.id,  "feeding", TODAY + timedelta(days=3), scheduled_time="10:00")
    task_service.create(luna.id,  "walk",    TODAY + timedelta(days=3), scheduled_time="10:00")

    conflicts = task_service.detect_conflicts(all_pet_ids, window_days=7)
    if conflicts:
        for c in conflicts:
            print(f"  [{c.conflict_type}] {c.message}")
    else:
        print("  No conflicts detected.")

    # â”€â”€ 10. AI care coach â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print("\n  " + "-" * 41)
    print("  AI Care Coach demo")
    print("  " + "-" * 41)
    coach = PawPalAICoach(
        pet_service=pet_service,
        care_target_service=target_service,
        activity_service=activity_service,
        care_score_service=score_service,
        task_service=task_service,
    )
    ai_plan = coach.generate_plan(
        pet_id=max_.id,
        question="Explain what needs attention this week and suggest the next best routine-care tasks.",
        owner_pet_ids=all_pet_ids,
        horizon_days=7,
    )
    print(f"  Summary    : {ai_plan.summary}")
    print(f"  Confidence : {int(ai_plan.confidence * 100)}%")
    if ai_plan.alerts:
        for alert in ai_plan.alerts:
            print(f"  Alert      : {alert}")
    for action in ai_plan.actions:
        due = action.due_date.isoformat() if action.due_date else "review only"
        mode = action.task_type or "guidance"
        print(f"  - {action.title} [{action.priority}] ({mode}, due {due})")

    print()
    print("=" * 45)
    print("  Done.")
    print("=" * 45)


if __name__ == "__main__":
    main()
