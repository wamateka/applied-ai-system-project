from __future__ import annotations

import hashlib
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Optional


# --- Data Models ---


@dataclass
class User:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    email: str = ""
    password_hash: str = ""
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Pet:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    name: str = ""
    species: str = ""
    breed: Optional[str] = None
    weight_kg: Optional[float] = None
    age_years: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class CareTarget:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pet_id: str = ""                  # unique per pet — enforced by set_targets upsert
    daily_meals: int = 0
    daily_walk_min: int = 0
    grooming_interval_days: int = 0
    vet_interval_days: int = 0
    status: str = "pending"           # "pending" | "achieved"
    reset_period: str = "none"        # "none" | "daily" | "weekly" — auto-resets status
    last_reset_date: Optional[date] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class Activity:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pet_id: str = ""
    type: str = ""                    # "feeding" | "walk" | "grooming" | "vet_visit"
    date: date = field(default_factory=date.today)
    details: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


# Valid field names that PetService.update() is allowed to modify.
_PET_UPDATABLE_FIELDS: frozenset[str] = frozenset(
    {"name", "species", "breed", "weight_kg", "age_years"}
)


@dataclass
class CareScore:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pet_id: str = ""
    date: date = field(default_factory=date.today)  # unique per (pet_id, date) — enforced by calculate upsert
    feeding_pct: int = 0
    exercise_pct: int = 0
    grooming_pct: int = 0
    vet_pct: int = 0
    overall_score: int = 0
    grade: str = ""
    created_at: datetime = field(default_factory=datetime.now)


# --- Services ---


class UserService:
    _users: dict[str, User] = {}

    def register(self, name: str, email: str, password: str) -> User:
        """Hash password and persist a new User, returning the created instance."""
        # Check if email already exists
        for user in self._users.values():
            if user.email == email:
                raise ValueError(f"Email '{email}' already registered")

        # Hash password
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        # Create and store user
        user = User(
            name=name,
            email=email,
            password_hash=password_hash,
            created_at=datetime.now()
        )
        self._users[user.id] = user
        return user

    def login(self, email: str, password: str) -> User:
        """Verify credentials and return the matching User, raising on failure."""
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        for user in self._users.values():
            if user.email == email and user.password_hash == password_hash:
                return user

        raise ValueError("Invalid email or password")

    def get_pets(self, user_id: str) -> list[Pet]:
        """Return all Pet records owned by the given user_id."""
        return [p for p in PetService._pets.values() if p.user_id == user_id]


class PetService:
    _pets: dict[str, Pet] = {}

    def create(
        self,
        user_id: str,
        name: str,
        species: str,
        breed: Optional[str] = None,
        weight_kg: Optional[float] = None,
        age_years: Optional[int] = None,
    ) -> Pet:
        """Persist and return a new Pet for the given user."""
        pet = Pet(
            user_id=user_id,
            name=name,
            species=species,
            breed=breed,
            weight_kg=weight_kg,
            age_years=age_years,
            created_at=datetime.now()
        )
        self._pets[pet.id] = pet
        return pet

    def update(self, pet_id: str, **kwargs) -> Pet:
        """Apply allowed field updates (name, species, breed, weight_kg, age_years) to the Pet and return it."""
        if pet_id not in self._pets:
            raise ValueError(f"Pet '{pet_id}' not found")

        pet = self._pets[pet_id]

        for key, value in kwargs.items():
            if key not in _PET_UPDATABLE_FIELDS:
                raise ValueError(f"Cannot update field: {key}")
            setattr(pet, key, value)

        return pet

    def get_profile(self, pet_id: str) -> Pet:
        """Fetch and return the Pet record for the given pet_id."""
        if pet_id not in self._pets:
            raise ValueError(f"Pet '{pet_id}' not found")
        return self._pets[pet_id]

    def delete(self, pet_id: str) -> None:
        """Remove the Pet and cascade-delete its CareScores, Activities, and CareTarget in safe order."""
        if pet_id not in self._pets:
            raise ValueError(f"Pet '{pet_id}' not found")

        # Delete in order: CareScore → Activity → CareTarget → Pet
        CareScoreService._scores = {
            k: v for k, v in CareScoreService._scores.items() if v.pet_id != pet_id
        }

        ActivityService._activities = {
            k: v for k, v in ActivityService._activities.items() if v.pet_id != pet_id
        }

        CareTargetService._targets = {
            k: v for k, v in CareTargetService._targets.items() if v.pet_id != pet_id
        }

        TaskService._tasks = {
            k: v for k, v in TaskService._tasks.items() if v.pet_id != pet_id
        }

        del self._pets[pet_id]


class CareTargetService:
    _targets: dict[str, CareTarget] = {}

    def set_targets(
        self,
        pet_id: str,
        daily_meals: int,
        daily_walk_min: int,
        grooming_interval_days: int,
        vet_interval_days: int,
        reset_period: str = "none",
    ) -> CareTarget:
        """Upsert the single CareTarget for the given pet, updating in place if one already exists."""
        # Find existing target for this pet
        existing = None
        for target in self._targets.values():
            if target.pet_id == pet_id:
                existing = target
                break

        if existing:
            # Update existing
            existing.daily_meals = daily_meals
            existing.daily_walk_min = daily_walk_min
            existing.grooming_interval_days = grooming_interval_days
            existing.vet_interval_days = vet_interval_days
            existing.reset_period = reset_period
            existing.updated_at = datetime.now()
            return existing
        else:
            # Create new
            target = CareTarget(
                pet_id=pet_id,
                daily_meals=daily_meals,
                daily_walk_min=daily_walk_min,
                grooming_interval_days=grooming_interval_days,
                vet_interval_days=vet_interval_days,
                reset_period=reset_period,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            self._targets[target.id] = target
            return target

    def get_targets(self, pet_id: str) -> CareTarget:
        """Return the CareTarget associated with the given pet_id."""
        for target in self._targets.values():
            if target.pet_id == pet_id:
                return target
        raise ValueError(f"No CareTarget found for pet '{pet_id}'")

    def mark_achieved(self, pet_id: str) -> CareTarget:
        """Set the CareTarget status to 'achieved' for the given pet and return it."""
        target = self.get_targets(pet_id)
        target.status = "achieved"
        target.last_reset_date = date.today()
        target.updated_at = datetime.now()
        return target

    def check_and_reset(
        self, pet_id: str, today: Optional[date] = None
    ) -> Optional[CareTarget]:
        """
        If reset_period is set and enough time has passed since last_reset_date,
        flip status back to 'pending'. Returns the target if reset happened, else None.
        """
        today = today or date.today()
        target = self.get_targets(pet_id)
        if target.reset_period == "none" or target.status != "achieved":
            return None
        last = target.last_reset_date or target.updated_at.date()
        elapsed = (today - last).days
        if target.reset_period == "daily" and elapsed >= 1:
            target.status = "pending"
            target.last_reset_date = today
            target.updated_at = datetime.now()
            return target
        if target.reset_period == "weekly" and elapsed >= 7:
            target.status = "pending"
            target.last_reset_date = today
            target.updated_at = datetime.now()
            return target
        return None

    def check_and_reset_all(self, today: Optional[date] = None) -> list[CareTarget]:
        """Run check_and_reset for every target that has a reset_period set."""
        today = today or date.today()
        return [
            result
            for target in self._targets.values()
            if target.reset_period != "none"
            for result in [self.check_and_reset(target.pet_id, today)]
            if result is not None
        ]

    def count_for_pet(self, pet_id: str) -> int:
        """Return the number of CareTarget records that exist for the given pet (0 or 1)."""
        return sum(1 for t in self._targets.values() if t.pet_id == pet_id)


class ActivityService:
    _activities: dict[str, Activity] = {}

    def log_activity(
        self,
        pet_id: str,
        activity_type: str,
        details: dict,
        activity_date: Optional[date] = None,
    ) -> Activity:
        """Persist and return a new Activity for activity_date, defaulting to today to support backdating."""
        if activity_date is None:
            activity_date = date.today()

        activity = Activity(
            pet_id=pet_id,
            type=activity_type,
            date=activity_date,
            details=details,
            created_at=datetime.now()
        )
        self._activities[activity.id] = activity
        return activity

    def get_by_date(self, pet_id: str, activity_date: date) -> list[Activity]:
        """Return all Activity records for the given pet on the specified date."""
        return [
            a for a in self._activities.values()
            if a.pet_id == pet_id and a.date == activity_date
        ]

    def get_recent(
        self,
        pet_id: str,
        days: int,
        today: Optional[date] = None,
    ) -> list[Activity]:
        """Return recent Activity records for the pet within the last `days` days."""
        today = today or date.today()
        cutoff = today - timedelta(days=max(0, days - 1))
        matching = [
            a
            for a in self._activities.values()
            if a.pet_id == pet_id and cutoff <= a.date <= today
        ]
        return sorted(matching, key=lambda a: (a.date, a.created_at), reverse=True)

    def get_latest_by_type(
        self, pet_id: str, activity_type: str
    ) -> Optional[Activity]:
        """Return the most recent Activity of the given type, or None if none exist."""
        matching = [
            a for a in self._activities.values()
            if a.pet_id == pet_id and a.type == activity_type
        ]
        if not matching:
            return None
        return max(matching, key=lambda a: a.created_at)


class CareScoreService:
    _scores: dict[str, CareScore] = {}

    def __init__(
        self,
        activity_service: ActivityService,
        care_target_service: CareTargetService,
    ) -> None:
        """Store injected service dependencies used by calculate()."""
        self._activity_service = activity_service
        self._care_target_service = care_target_service

    def calculate(self, pet_id: str, score_date: date) -> CareScore:
        """Compute feeding, exercise, grooming, and vet scores against targets, then upsert and return the CareScore."""
        # Get targets
        targets = self._care_target_service.get_targets(pet_id)

        # Get activities for the day
        activities = self._activity_service.get_by_date(pet_id, score_date)

        # Calculate FEEDING
        feeding_count = sum(1 for a in activities if a.type == "feeding")
        if targets.daily_meals > 0:
            feeding_pct = min(100, int((feeding_count / targets.daily_meals) * 100))
        else:
            feeding_pct = 0

        # Calculate EXERCISE
        walk_duration = sum(
            a.details.get("duration_min", 0) for a in activities if a.type == "walk"
        )
        if targets.daily_walk_min > 0:
            exercise_pct = min(100, int((walk_duration / targets.daily_walk_min) * 100))
        else:
            exercise_pct = 0

        # Calculate GROOMING
        last_grooming = self._activity_service.get_latest_by_type(pet_id, "grooming")
        if last_grooming:
            days_since = (score_date - last_grooming.date).days
            grooming_pct = 100 if days_since <= targets.grooming_interval_days else 0
        else:
            grooming_pct = 0

        # Calculate VET
        last_vet = self._activity_service.get_latest_by_type(pet_id, "vet_visit")
        if last_vet:
            days_since = (score_date - last_vet.date).days
            vet_pct = 100 if days_since <= targets.vet_interval_days else 0
        else:
            vet_pct = 0

        # Calculate OVERALL
        overall_score = round((feeding_pct + exercise_pct + grooming_pct + vet_pct) / 4)

        # Calculate GRADE
        if overall_score >= 90:
            grade = "A"
        elif overall_score >= 80:
            grade = "B"
        elif overall_score >= 70:
            grade = "C"
        else:
            grade = "D"

        # Upsert score
        existing = None
        for score in self._scores.values():
            if score.pet_id == pet_id and score.date == score_date:
                existing = score
                break

        if existing:
            existing.feeding_pct = feeding_pct
            existing.exercise_pct = exercise_pct
            existing.grooming_pct = grooming_pct
            existing.vet_pct = vet_pct
            existing.overall_score = overall_score
            existing.grade = grade
            return existing
        else:
            score = CareScore(
                pet_id=pet_id,
                date=score_date,
                feeding_pct=feeding_pct,
                exercise_pct=exercise_pct,
                grooming_pct=grooming_pct,
                vet_pct=vet_pct,
                overall_score=overall_score,
                grade=grade,
                created_at=datetime.now()
            )
            self._scores[score.id] = score
            return score

    def get_by_date(self, pet_id: str, score_date: date) -> Optional[CareScore]:
        """Return the CareScore for the given pet on score_date, or None if absent."""
        for score in self._scores.values():
            if score.pet_id == pet_id and score.date == score_date:
                return score
        return None

    def get_history(self, pet_id: str, days: int) -> list[CareScore]:
        """Return CareScore records for the given pet over the last `days` days."""
        cutoff_date = date.today() - timedelta(days=days)
        scores = [
            s for s in self._scores.values()
            if s.pet_id == pet_id and s.date >= cutoff_date
        ]
        return sorted(scores, key=lambda s: s.date)


# ---------------------------------------------------------------------------
# Scheduled Tasks
# ---------------------------------------------------------------------------

@dataclass
class ScheduledTask:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pet_id: str = ""
    task_type: str = ""               # "feeding" | "walk" | "grooming" | "vet_visit"
    scheduled_date: date = field(default_factory=date.today)
    scheduled_time: Optional[str] = None   # "HH:MM" or None
    recurrence: str = "none"              # "none" | "daily" | "weekly" | "custom"
    recurrence_interval_days: int = 0     # used when recurrence == "custom"
    status: str = "pending"               # "pending" | "done" | "skipped"
    parent_task_id: Optional[str] = None  # links spawned task back to its origin
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ConflictReport:
    task_id: str
    conflict_type: str      # "duplicate_non_feeding" | "time_proximity" | "daily_overload"
    conflicting_task_id: Optional[str]   # None for daily_overload
    message: str


# ---------------------------------------------------------------------------
# Sorting helpers (pure functions — no storage dependency)
# ---------------------------------------------------------------------------

def sort_by_urgency(tasks: list[ScheduledTask], today: date) -> list[ScheduledTask]:
    """Overdue tasks first, then ascending by scheduled_date."""
    return sorted(tasks, key=lambda t: (t.scheduled_date - today).days)


def sort_by_care_score(
    tasks: list[ScheduledTask], score_map: dict[str, int]
) -> list[ScheduledTask]:
    """Pets with the lowest overall care score surface first; ties broken by urgency."""
    today = date.today()
    return sorted(
        tasks,
        key=lambda t: (score_map.get(t.pet_id, 50), (t.scheduled_date - today).days),
    )


def sort_by_completion_gap(
    tasks: list[ScheduledTask], gap_map: dict[str, float]
) -> list[ScheduledTask]:
    """Pets furthest from meeting today's targets surface first (gap 0.0–1.0)."""
    today = date.today()
    return sorted(
        tasks,
        key=lambda t: (-(gap_map.get(t.pet_id, 0.5)), (t.scheduled_date - today).days),
    )


# ---------------------------------------------------------------------------
# TaskService
# ---------------------------------------------------------------------------

class TaskService:
    _tasks: dict[str, ScheduledTask] = {}

    # ── CRUD ──────────────────────────────────────────────────────────────

    def create(
        self,
        pet_id: str,
        task_type: str,
        scheduled_date: date,
        scheduled_time: Optional[str] = None,
        recurrence: str = "none",
        recurrence_interval_days: int = 0,
        notes: str = "",
        parent_task_id: Optional[str] = None,
    ) -> ScheduledTask:
        """Persist and return a new ScheduledTask."""
        task = ScheduledTask(
            pet_id=pet_id,
            task_type=task_type,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            recurrence=recurrence,
            recurrence_interval_days=recurrence_interval_days,
            notes=notes,
            parent_task_id=parent_task_id,
        )
        self._tasks[task.id] = task
        return task

    def complete(self, task_id: str) -> Optional[ScheduledTask]:
        """Mark task done. Returns spawned next occurrence for recurring tasks, else None."""
        task = self._get_or_raise(task_id)
        task.status = "done"
        if task.recurrence != "none":
            return self._spawn_next(task)
        return None

    def skip(self, task_id: str) -> Optional[ScheduledTask]:
        """Mark task skipped. Returns spawned next occurrence for recurring tasks, else None."""
        task = self._get_or_raise(task_id)
        task.status = "skipped"
        if task.recurrence != "none":
            return self._spawn_next(task)
        return None

    def get_all_for_pets(
        self,
        pet_ids: list[str],
        status: Optional[str] = None,
    ) -> list[ScheduledTask]:
        """Return all tasks for the given pets, optionally filtered by status."""
        tasks = [t for t in self._tasks.values() if t.pet_id in pet_ids]
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def delete_for_pet(self, pet_id: str) -> None:
        """Remove all tasks belonging to the given pet (called from PetService.delete cascade)."""
        self._tasks = {k: v for k, v in self._tasks.items() if v.pet_id != pet_id}

    # ── Conflict detection ────────────────────────────────────────────────

    def detect_conflicts(
        self, pet_ids: list[str], window_days: int = 7
    ) -> list[ConflictReport]:
        """
        Return ConflictReports for pending tasks within the next window_days.

        Three rules:
          A. Same non-feeding task type, same pet, same day.
          B. Two tasks with scheduled_time set whose times are < 30 min apart, same day.
          C. More than 6 pending tasks for the same pet on the same day.
        """
        today = date.today()
        cutoff = today + timedelta(days=window_days)
        pending = [
            t for t in self._tasks.values()
            if t.status == "pending"
            and t.pet_id in pet_ids
            and today <= t.scheduled_date <= cutoff
        ]

        reports: list[ConflictReport] = []
        seen_pairs: set[frozenset] = set()

        # Rules A & B — pairwise checks within same pet + same day
        by_day: dict = defaultdict(list)
        for t in pending:
            by_day[(t.pet_id, t.scheduled_date)].append(t)

        for group in by_day.values():
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    pair = frozenset({a.id, b.id})
                    if pair in seen_pairs:
                        continue
                    # Rule A
                    if a.task_type == b.task_type and a.task_type != "feeding":
                        reports.append(ConflictReport(
                            task_id=a.id,
                            conflict_type="duplicate_non_feeding",
                            conflicting_task_id=b.id,
                            message=(
                                f"'{a.task_type}' scheduled twice on {a.scheduled_date} "
                                f"for the same pet."
                            ),
                        ))
                        seen_pairs.add(pair)
                        continue
                    # Rule B
                    if a.scheduled_time and b.scheduled_time:
                        if abs(self._to_minutes(a.scheduled_time) - self._to_minutes(b.scheduled_time)) < 30:
                            reports.append(ConflictReport(
                                task_id=a.id,
                                conflict_type="time_proximity",
                                conflicting_task_id=b.id,
                                message=(
                                    f"'{a.task_type}' @ {a.scheduled_time} and "
                                    f"'{b.task_type}' @ {b.scheduled_time} overlap "
                                    f"within 30 min on {a.scheduled_date}."
                                ),
                            ))
                            seen_pairs.add(pair)

            # Rule C — overload
            if len(group) > 6:
                reports.append(ConflictReport(
                    task_id=group[0].id,
                    conflict_type="daily_overload",
                    conflicting_task_id=None,
                    message=(
                        f"{len(group)} tasks scheduled on {group[0].scheduled_date} "
                        f"for the same pet — may be unmanageable."
                    ),
                ))

        # Rule D — exact same time on the same day, different pets
        by_time: dict = defaultdict(list)
        for t in pending:
            if t.scheduled_time:
                by_time[(t.scheduled_date, t.scheduled_time)].append(t)

        for (day, time_str), group in by_time.items():
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    if a.pet_id == b.pet_id:
                        continue  # already covered by same-pet rules above
                    pair = frozenset({a.id, b.id})
                    if pair in seen_pairs:
                        continue
                    reports.append(ConflictReport(
                        task_id=a.id,
                        conflict_type="cross_pet_time_clash",
                        conflicting_task_id=b.id,
                        message=(
                            f"'{a.task_type}' and '{b.task_type}' for different pets "
                            f"both scheduled at {time_str} on {day}."
                        ),
                    ))
                    seen_pairs.add(pair)

        return reports

    # ── Private helpers ───────────────────────────────────────────────────

    def _get_or_raise(self, task_id: str) -> ScheduledTask:
        if task_id not in self._tasks:
            raise ValueError(f"Task '{task_id}' not found")
        return self._tasks[task_id]

    def _spawn_next(self, task: ScheduledTask) -> ScheduledTask:
        """Create the next occurrence of a recurring task."""
        interval = self._recurrence_interval(task)
        return self.create(
            pet_id=task.pet_id,
            task_type=task.task_type,
            scheduled_date=task.scheduled_date + timedelta(days=interval),
            scheduled_time=task.scheduled_time,
            recurrence=task.recurrence,
            recurrence_interval_days=task.recurrence_interval_days,
            notes=task.notes,
            parent_task_id=task.id,
        )

    @staticmethod
    def _recurrence_interval(task: ScheduledTask) -> int:
        if task.recurrence == "daily":
            return 1
        if task.recurrence == "weekly":
            return 7
        if task.recurrence == "custom":
            return max(1, task.recurrence_interval_days)
        return 0

    @staticmethod
    def _to_minutes(time_str: str) -> int:
        """Convert 'HH:MM' string to total minutes since midnight."""
        h, m = time_str.split(":")
        return int(h) * 60 + int(m)
