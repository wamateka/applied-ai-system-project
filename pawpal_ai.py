from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from pawpal_system import (
    Activity,
    ActivityService,
    CareScore,
    CareScoreService,
    CareTarget,
    CareTargetService,
    ConflictReport,
    Pet,
    PetService,
    ScheduledTask,
    TaskService,
    sort_by_urgency,
)


_TOKEN_RE = re.compile(r"[a-z0-9']+")
_EMERGENCY_TERMS = {
    "bleeding",
    "blood",
    "collapse",
    "collapsed",
    "seizure",
    "seizures",
    "poison",
    "poisoning",
    "toxic",
    "vomiting",
    "can't breathe",
    "cannot breathe",
    "not breathing",
    "trouble breathing",
    "choking",
    "unresponsive",
}
_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text.lower())}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


@dataclass(frozen=True)
class KnowledgeDocument:
    id: str
    title: str
    species: str
    source: str
    tags: list[str]
    content: str


@dataclass
class RetrievedKnowledge:
    doc_id: str
    title: str
    source: str
    species: str
    tags: list[str]
    score: float
    matched_terms: list[str]
    excerpt: str


@dataclass
class ActionRecommendation:
    title: str
    priority: str
    rationale: str
    due_date: Optional[date] = None
    task_type: Optional[str] = None
    scheduled_time: Optional[str] = None
    recurrence: str = "none"
    recurrence_interval_days: int = 0
    notes: str = ""
    citations: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass
class CarePlanResult:
    request_id: str
    pet_id: str
    pet_name: str
    question: str
    generated_at: datetime
    status: str
    summary: str
    findings: list[str]
    alerts: list[str]
    missing_data: list[str]
    confidence: float
    confidence_rationale: str
    retrieved_knowledge: list[RetrievedKnowledge]
    actions: list[ActionRecommendation]


@dataclass
class TaskApplicationResult:
    created_tasks: list[ScheduledTask]
    skipped_messages: list[str]


@dataclass
class GuardrailDecision:
    status: str = "normal"
    alerts: list[str] = field(default_factory=list)


@dataclass
class PetContextSnapshot:
    pet: Pet
    targets: Optional[CareTarget]
    score: Optional[CareScore]
    recent_activities: list[Activity]
    today_activities: list[Activity]
    pending_tasks: list[ScheduledTask]
    overdue_tasks: list[ScheduledTask]
    conflicts: list[ConflictReport]
    missing_data: list[str]
    alerts: list[str]


class KnowledgeBase:
    def __init__(self, knowledge_path: Path) -> None:
        raw = json.loads(knowledge_path.read_text(encoding="utf-8"))
        self._documents = [KnowledgeDocument(**item) for item in raw["documents"]]

    def search(
        self,
        query: str,
        species: str,
        context_tags: list[str],
        top_k: int = 4,
    ) -> list[RetrievedKnowledge]:
        query_terms = _tokenize(query)
        context_terms = {tag.lower() for tag in context_tags}
        combined_terms = query_terms | context_terms | {species.lower()}
        scored: list[RetrievedKnowledge] = []

        for doc in self._documents:
            doc_terms = _tokenize(
                " ".join([doc.title, doc.content, doc.species, " ".join(doc.tags)])
            )
            tag_terms = {tag.lower() for tag in doc.tags}
            matched_terms = sorted(combined_terms & (doc_terms | tag_terms))

            score = 0.0
            if doc.species == species:
                score += 5.0
            elif doc.species == "all":
                score += 2.0
            elif doc.species != species:
                continue

            score += 3.0 * len(query_terms & _tokenize(doc.title))
            score += 2.0 * len(query_terms & tag_terms)
            score += 1.0 * len(combined_terms & _tokenize(doc.content))
            score += 2.0 * len(context_terms & tag_terms)

            if score <= 0:
                continue

            scored.append(
                RetrievedKnowledge(
                    doc_id=doc.id,
                    title=doc.title,
                    source=doc.source,
                    species=doc.species,
                    tags=doc.tags,
                    score=score,
                    matched_terms=matched_terms,
                    excerpt=doc.content[:220] + ("..." if len(doc.content) > 220 else ""),
                )
            )

        if not scored:
            fallback = [
                doc
                for doc in self._documents
                if doc.species in {species, "all"}
            ][:top_k]
            return [
                RetrievedKnowledge(
                    doc_id=doc.id,
                    title=doc.title,
                    source=doc.source,
                    species=doc.species,
                    tags=doc.tags,
                    score=1.0,
                    matched_terms=[],
                    excerpt=doc.content[:220] + ("..." if len(doc.content) > 220 else ""),
                )
                for doc in fallback
            ]

        scored.sort(key=lambda item: (-item.score, item.title))
        return scored[:top_k]


class PawPalAICoach:
    def __init__(
        self,
        pet_service: PetService,
        care_target_service: CareTargetService,
        activity_service: ActivityService,
        care_score_service: CareScoreService,
        task_service: TaskService,
        knowledge_base_path: Optional[Path] = None,
        audit_log_path: Optional[Path] = None,
    ) -> None:
        base_dir = Path(__file__).resolve().parent
        self._pet_service = pet_service
        self._care_target_service = care_target_service
        self._activity_service = activity_service
        self._care_score_service = care_score_service
        self._task_service = task_service
        self._knowledge_base = KnowledgeBase(
            knowledge_base_path or base_dir / "knowledge_base" / "pet_care_knowledge.json"
        )
        self._audit_log_path = audit_log_path or base_dir / "logs" / "pawpal_ai_runs.jsonl"

    def generate_plan(
        self,
        pet_id: str,
        question: str,
        owner_pet_ids: Optional[list[str]] = None,
        horizon_days: int = 7,
    ) -> CarePlanResult:
        prompt = (question or "").strip() or (
            "Explain what needs attention and suggest the next best routine-care steps."
        )
        guardrail = self._apply_guardrails(prompt)
        snapshot = self._build_snapshot(pet_id, owner_pet_ids or [pet_id], horizon_days)
        context_tags = self._build_context_tags(snapshot, guardrail)
        retrieved = self._knowledge_base.search(
            query=prompt,
            species=snapshot.pet.species.lower(),
            context_tags=context_tags,
            top_k=4,
        )
        findings = self._build_findings(snapshot)
        drafted_actions = self._draft_actions(
            snapshot=snapshot,
            question=prompt,
            retrieved=retrieved,
            guardrail=guardrail,
            horizon_days=horizon_days,
        )
        actions, verifier_alerts = self._verify_actions(snapshot, drafted_actions, retrieved)
        alerts = [*guardrail.alerts, *snapshot.alerts, *verifier_alerts]
        confidence = self._score_confidence(snapshot, retrieved, actions, guardrail)
        confidence_rationale = self._build_confidence_rationale(
            snapshot, retrieved, actions, guardrail, confidence
        )
        summary = self._build_summary(snapshot, actions, guardrail)

        result = CarePlanResult(
            request_id=str(uuid.uuid4()),
            pet_id=snapshot.pet.id,
            pet_name=snapshot.pet.name,
            question=prompt,
            generated_at=datetime.now(timezone.utc),
            status=guardrail.status,
            summary=summary,
            findings=findings,
            alerts=alerts,
            missing_data=snapshot.missing_data,
            confidence=confidence,
            confidence_rationale=confidence_rationale,
            retrieved_knowledge=retrieved,
            actions=actions,
        )
        log_warning = self._safe_append_audit_log(result)
        if log_warning:
            result.alerts.append(log_warning)
        return result

    def apply_task_suggestions(self, plan: CarePlanResult) -> TaskApplicationResult:
        created: list[ScheduledTask] = []
        skipped: list[str] = []
        pending_tasks = self._task_service.get_all_for_pets([plan.pet_id], status="pending")

        for action in plan.actions:
            if not action.task_type or action.due_date is None:
                continue
            duplicate = next(
                (
                    task
                    for task in pending_tasks
                    if task.task_type == action.task_type
                    and task.scheduled_date == action.due_date
                ),
                None,
            )
            if duplicate:
                skipped.append(
                    f"Skipped '{action.title}' because a pending {action.task_type} task already exists on {action.due_date}."
                )
                continue

            task = self._task_service.create(
                pet_id=plan.pet_id,
                task_type=action.task_type,
                scheduled_date=action.due_date,
                scheduled_time=action.scheduled_time,
                recurrence=action.recurrence,
                recurrence_interval_days=action.recurrence_interval_days,
                notes=action.notes or f"AI Care Coach: {action.title}",
            )
            pending_tasks.append(task)
            created.append(task)

        log_warning = self._safe_append_audit_log(
            {
                "event": "task_application",
                "request_id": plan.request_id,
                "pet_id": plan.pet_id,
                "created_task_ids": [task.id for task in created],
                "skipped_messages": skipped,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        if log_warning:
            skipped.append(log_warning)
        return TaskApplicationResult(created_tasks=created, skipped_messages=skipped)

    def _apply_guardrails(self, question: str) -> GuardrailDecision:
        lowered = question.lower()
        if any(term in lowered for term in _EMERGENCY_TERMS):
            return GuardrailDecision(
                status="emergency",
                alerts=[
                    "This request may involve an urgent health issue. The AI coach only supports routine care planning and is not a diagnostic tool.",
                    "Please contact a veterinarian or emergency clinic instead of relying on an in-app recommendation.",
                ],
            )
        return GuardrailDecision()

    def _build_snapshot(
        self,
        pet_id: str,
        owner_pet_ids: list[str],
        horizon_days: int,
    ) -> PetContextSnapshot:
        pet = self._pet_service.get_profile(pet_id)
        missing_data: list[str] = []
        alerts: list[str] = []
        today = date.today()

        try:
            targets = self._care_target_service.get_targets(pet_id)
        except ValueError:
            targets = None
            missing_data.append("No care targets have been set for this pet yet.")

        score: Optional[CareScore]
        if targets is None:
            score = None
            missing_data.append("Today's care score is unavailable until targets are configured.")
        else:
            score = self._care_score_service.get_by_date(pet_id, today)
            if score is None:
                score = self._care_score_service.calculate(pet_id, today)

        today_activities = self._activity_service.get_by_date(pet_id, today)
        recent_activities = self._activity_service.get_recent(pet_id, days=14, today=today)
        if not recent_activities:
            missing_data.append("No activities have been logged in the last 14 days.")

        pending_tasks = sort_by_urgency(
            self._task_service.get_all_for_pets([pet_id], status="pending"),
            today,
        )
        overdue_tasks = [task for task in pending_tasks if task.scheduled_date < today]

        all_conflicts = self._task_service.detect_conflicts(
            owner_pet_ids, window_days=max(3, horizon_days)
        )
        related_task_ids = {task.id for task in self._task_service.get_all_for_pets([pet_id])}
        conflicts = [
            conflict
            for conflict in all_conflicts
            if conflict.task_id in related_task_ids
            or (
                conflict.conflicting_task_id is not None
                and conflict.conflicting_task_id in related_task_ids
            )
        ]

        if overdue_tasks:
            alerts.append(
                f"{pet.name} has {len(overdue_tasks)} overdue task(s) that should be cleared before adding more optional work."
            )
        if conflicts:
            alerts.append(
                f"{pet.name} is involved in {len(conflicts)} upcoming scheduling conflict(s)."
            )

        return PetContextSnapshot(
            pet=pet,
            targets=targets,
            score=score,
            recent_activities=recent_activities,
            today_activities=today_activities,
            pending_tasks=pending_tasks,
            overdue_tasks=overdue_tasks,
            conflicts=conflicts,
            missing_data=missing_data,
            alerts=alerts,
        )

    def _build_context_tags(
        self,
        snapshot: PetContextSnapshot,
        guardrail: GuardrailDecision,
    ) -> list[str]:
        tags = {"planning", "routine"}
        if guardrail.status == "emergency":
            tags.update({"safety", "emergency"})
            return sorted(tags)

        if snapshot.score:
            if snapshot.score.feeding_pct < 100:
                tags.add("feeding")
            if snapshot.score.exercise_pct < 100:
                tags.add("exercise")
            if snapshot.score.grooming_pct < 100:
                tags.add("grooming")
            if snapshot.score.vet_pct < 100:
                tags.add("vet")
        if snapshot.overdue_tasks:
            tags.add("recovery")
        if snapshot.conflicts:
            tags.update({"scheduling", "conflicts"})
        if snapshot.targets is None:
            tags.add("targets")
        return sorted(tags)

    def _build_findings(self, snapshot: PetContextSnapshot) -> list[str]:
        findings: list[str] = []
        if snapshot.score:
            findings.append(
                f"Today's care score is {snapshot.score.overall_score}/100 (grade {snapshot.score.grade})."
            )
            if snapshot.score.feeding_pct < 100:
                findings.append(
                    f"Feeding completion is {snapshot.score.feeding_pct}%, which suggests the daily meal target is not fully covered."
                )
            if snapshot.score.exercise_pct < 100:
                findings.append(
                    f"Exercise completion is {snapshot.score.exercise_pct}%, so movement or play is the biggest routine gap."
                )
            if snapshot.score.grooming_pct == 0:
                findings.append("Grooming appears overdue based on the current interval target.")
            if snapshot.score.vet_pct == 0:
                findings.append("Preventive vet care appears overdue based on the current interval target.")
        if snapshot.overdue_tasks:
            findings.append(
                f"There are {len(snapshot.overdue_tasks)} overdue task(s) in the schedule backlog."
            )
        if snapshot.conflicts:
            findings.append(
                f"There are {len(snapshot.conflicts)} conflict warning(s) in the next planning window."
            )
        if not findings:
            findings.append("The current routine looks stable, with no major gaps detected in the available data.")
        return findings

    def _draft_actions(
        self,
        snapshot: PetContextSnapshot,
        question: str,
        retrieved: list[RetrievedKnowledge],
        guardrail: GuardrailDecision,
        horizon_days: int,
    ) -> list[ActionRecommendation]:
        today = date.today()
        actions: list[ActionRecommendation] = []

        def add_action(
            title: str,
            rationale: str,
            *,
            priority: str,
            citation_tags: list[str],
            evidence: list[str],
            due_date: Optional[date] = None,
            task_type: Optional[str] = None,
            recurrence: str = "none",
            recurrence_interval_days: int = 0,
            scheduled_time: Optional[str] = None,
        ) -> None:
            actions.append(
                ActionRecommendation(
                    title=title,
                    priority=priority,
                    rationale=rationale,
                    due_date=due_date,
                    task_type=task_type,
                    scheduled_time=scheduled_time,
                    recurrence=recurrence,
                    recurrence_interval_days=recurrence_interval_days,
                    notes=f"AI Care Coach: {title}. {rationale}",
                    citations=self._match_citations(retrieved, citation_tags),
                    evidence=evidence,
                )
            )

        if guardrail.status == "emergency":
            add_action(
                title="Hand this off to a veterinarian immediately",
                rationale="The question contains symptoms or emergency language, so the coach is intentionally stopping at a safety escalation.",
                priority="critical",
                citation_tags=["safety", "emergency"],
                evidence=["Emergency guardrails were triggered by the user's request."],
                due_date=today,
            )
            return actions

        if snapshot.targets is None:
            add_action(
                title="Set care targets before relying on automated planning",
                rationale="The coach can only judge gaps and build a recovery plan when meal, exercise, grooming, and vet targets are defined.",
                priority="high",
                citation_tags=["targets", "routine"],
                evidence=["No care targets were found for this pet."],
            )

        if snapshot.score and snapshot.targets:
            feeding_count = sum(1 for activity in snapshot.today_activities if activity.type == "feeding")
            walk_minutes = sum(
                activity.details.get("duration_min", 0)
                for activity in snapshot.today_activities
                if activity.type == "walk"
            )

            if snapshot.score.feeding_pct < 100:
                due_date = today
                action_title = (
                    "Close today's feeding gap"
                    if not self._has_pending_task(snapshot.pending_tasks, "feeding", due_date)
                    else "Complete the feeding task already on the schedule"
                )
                add_action(
                    title=action_title,
                    rationale=(
                        f"{feeding_count} feeding log(s) were recorded today against a target of "
                        f"{snapshot.targets.daily_meals} meal(s)."
                    ),
                    priority="high",
                    citation_tags=["feeding", "routine"],
                    evidence=[
                        f"Feeding score: {snapshot.score.feeding_pct}%.",
                        f"Today's feeding logs: {feeding_count}.",
                    ],
                    due_date=due_date if "Close" in action_title else None,
                    task_type="feeding" if "Close" in action_title else None,
                    recurrence="daily" if not self._has_task_type(snapshot.pending_tasks, "feeding") else "none",
                )

            if snapshot.score.exercise_pct < 100 and snapshot.targets.daily_walk_min > 0:
                due_date = today if not self._has_pending_task(snapshot.pending_tasks, "walk", today) else today + timedelta(days=1)
                add_action(
                    title="Rebuild exercise consistency with a scheduled walk or play block",
                    rationale=(
                        f"Only {walk_minutes} minute(s) of walk activity are logged today against a target of "
                        f"{snapshot.targets.daily_walk_min} minute(s)."
                    ),
                    priority="high",
                    citation_tags=["exercise", "walk", snapshot.pet.species.lower()],
                    evidence=[
                        f"Exercise score: {snapshot.score.exercise_pct}%.",
                        f"Today's logged walk minutes: {walk_minutes}.",
                    ],
                    due_date=due_date,
                    task_type="walk",
                    recurrence="daily",
                )

            if snapshot.score.grooming_pct == 0 and snapshot.targets.grooming_interval_days > 0:
                due_date = today + timedelta(days=1)
                add_action(
                    title="Book or schedule the next grooming task",
                    rationale=(
                        "The most recent grooming activity falls outside the configured grooming interval."
                    ),
                    priority="medium",
                    citation_tags=["grooming", "interval"],
                    evidence=["Grooming score is currently 0%."],
                    due_date=due_date if not self._has_pending_task(snapshot.pending_tasks, "grooming", due_date, window_days=2) else None,
                    task_type="grooming" if not self._has_pending_task(snapshot.pending_tasks, "grooming", due_date, window_days=2) else None,
                )

            if snapshot.score.vet_pct == 0 and snapshot.targets.vet_interval_days > 0:
                due_date = today + timedelta(days=min(7, max(2, horizon_days)))
                add_action(
                    title="Set a preventive vet reminder",
                    rationale="Preventive care has moved outside the current vet interval, so the next professional follow-up should be scheduled.",
                    priority="medium",
                    citation_tags=["vet", "preventive"],
                    evidence=["Vet score is currently 0%."],
                    due_date=due_date if not self._has_pending_task(snapshot.pending_tasks, "vet_visit", due_date, window_days=7) else None,
                    task_type="vet_visit" if not self._has_pending_task(snapshot.pending_tasks, "vet_visit", due_date, window_days=7) else None,
                )

        if snapshot.overdue_tasks:
            task_names = ", ".join(task.task_type for task in snapshot.overdue_tasks[:3])
            add_action(
                title="Clear the overdue backlog before adding lower-priority work",
                rationale=f"The schedule already has overdue task(s), starting with {task_names}.",
                priority="high",
                citation_tags=["recovery", "planning"],
                evidence=[f"Overdue task count: {len(snapshot.overdue_tasks)}."],
            )

        if snapshot.conflicts:
            add_action(
                title="Spread out the next few scheduled tasks",
                rationale="The current schedule has duplicate or overlapping work that should be spaced out before more reminders are added.",
                priority="medium",
                citation_tags=["scheduling", "conflicts"],
                evidence=[f"Conflict count: {len(snapshot.conflicts)}."],
            )

        if not actions:
            add_action(
                title="Keep the current routine steady and review again tomorrow",
                rationale="The available data does not show a major gap, so the best move is to maintain the routine and keep logging activity.",
                priority="low",
                citation_tags=["routine", "planning"],
                evidence=["No major score, conflict, or backlog issue was detected."],
            )

        if "summary" in question.lower():
            actions = actions[:3]
        return actions

    def _verify_actions(
        self,
        snapshot: PetContextSnapshot,
        actions: list[ActionRecommendation],
        retrieved: list[RetrievedKnowledge],
    ) -> tuple[list[ActionRecommendation], list[str]]:
        verified: list[ActionRecommendation] = []
        alerts: list[str] = []
        seen: set[tuple[str, Optional[str], Optional[date]]] = set()
        today = date.today()

        for action in actions:
            if not action.evidence:
                alerts.append(f"Dropped '{action.title}' because it had no supporting system evidence.")
                continue

            if not action.citations and retrieved:
                action.citations = [retrieved[0].doc_id]

            if action.due_date is not None and action.due_date < today:
                action.due_date = today

            if action.task_type and action.due_date is not None:
                duplicate = self._has_pending_task(
                    snapshot.pending_tasks,
                    action.task_type,
                    action.due_date,
                )
                if duplicate:
                    original_task_type = action.task_type
                    action.task_type = None
                    action.notes = ""
                    action.rationale += (
                        " A matching pending task already exists, so the coach kept this as guidance instead of duplicating it."
                    )
                    alerts.append(
                        f"Converted '{action.title}' into guidance because a pending {original_task_type} task already exists on {action.due_date}."
                    )

            key = (action.title, action.task_type, action.due_date)
            if key in seen:
                continue
            seen.add(key)
            verified.append(action)

        verified.sort(key=lambda action: (_PRIORITY_ORDER.get(action.priority, 99), action.title))
        return verified[:5], alerts

    def _build_summary(
        self,
        snapshot: PetContextSnapshot,
        actions: list[ActionRecommendation],
        guardrail: GuardrailDecision,
    ) -> str:
        if guardrail.status == "emergency":
            return (
                f"{snapshot.pet.name}'s request crossed the app's safety boundary. "
                "The coach stopped at a veterinary handoff instead of generating routine-care advice."
            )

        focus_areas: list[str] = []
        if snapshot.score:
            if snapshot.score.feeding_pct < 100:
                focus_areas.append("feeding")
            if snapshot.score.exercise_pct < 100:
                focus_areas.append("exercise")
            if snapshot.score.grooming_pct == 0:
                focus_areas.append("grooming")
            if snapshot.score.vet_pct == 0:
                focus_areas.append("preventive vet care")

        lead = (
            f"{snapshot.pet.name} needs attention on {', '.join(focus_areas[:3])}."
            if focus_areas
            else f"{snapshot.pet.name}'s routine looks mostly stable."
        )

        evidence_bits: list[str] = []
        if snapshot.score:
            evidence_bits.append(
                f"Today's care score is {snapshot.score.overall_score}/100 (grade {snapshot.score.grade})."
            )
        if snapshot.overdue_tasks:
            evidence_bits.append(f"There are {len(snapshot.overdue_tasks)} overdue task(s).")
        if snapshot.conflicts:
            evidence_bits.append(f"There are {len(snapshot.conflicts)} schedule conflict warning(s).")
        if snapshot.targets is None:
            evidence_bits.append("Targets still need to be configured before the plan can be very precise.")
        if actions:
            evidence_bits.append(f"The coach produced {len(actions)} reviewed action recommendation(s).")

        return " ".join([lead, *evidence_bits]).strip()

    def _score_confidence(
        self,
        snapshot: PetContextSnapshot,
        retrieved: list[RetrievedKnowledge],
        actions: list[ActionRecommendation],
        guardrail: GuardrailDecision,
    ) -> float:
        confidence = 0.45
        if snapshot.targets:
            confidence += 0.15
        if snapshot.score:
            confidence += 0.15
        if snapshot.recent_activities:
            confidence += min(0.10, len(snapshot.recent_activities) * 0.01)
        if retrieved:
            confidence += min(0.10, len(retrieved) * 0.025)
        if any(action.citations and action.evidence for action in actions):
            confidence += 0.10
        if snapshot.missing_data:
            confidence -= min(0.20, len(snapshot.missing_data) * 0.07)
        if guardrail.status == "emergency":
            confidence = min(confidence, 0.35)
        return round(_clamp(confidence, 0.10, 0.98), 2)

    def _build_confidence_rationale(
        self,
        snapshot: PetContextSnapshot,
        retrieved: list[RetrievedKnowledge],
        actions: list[ActionRecommendation],
        guardrail: GuardrailDecision,
        confidence: float,
    ) -> str:
        reasons: list[str] = []
        if snapshot.targets:
            reasons.append("targets are configured")
        else:
            reasons.append("targets are missing")
        if snapshot.score:
            reasons.append("today's care score was available")
        if snapshot.recent_activities:
            reasons.append(f"{len(snapshot.recent_activities)} recent activity log(s) were available")
        if retrieved:
            reasons.append(f"{len(retrieved)} knowledge source(s) were retrieved")
        if actions:
            reasons.append(f"{len(actions)} action(s) survived the self-check stage")
        if guardrail.status == "emergency":
            reasons.append("the response was intentionally narrowed by emergency guardrails")
        return f"Confidence: {int(confidence * 100)}%. This estimate is based on whether {'; '.join(reasons)}."

    def _match_citations(
        self,
        retrieved: list[RetrievedKnowledge],
        wanted_tags: list[str],
    ) -> list[str]:
        lowered = {tag.lower() for tag in wanted_tags}
        matches = [
            item.doc_id
            for item in retrieved
            if lowered & {tag.lower() for tag in item.tags}
        ]
        if matches:
            return matches[:2]
        return [item.doc_id for item in retrieved[:1]]

    def _has_task_type(self, tasks: list[ScheduledTask], task_type: str) -> bool:
        return any(task.task_type == task_type for task in tasks)

    def _has_pending_task(
        self,
        tasks: list[ScheduledTask],
        task_type: str,
        scheduled_date: date,
        window_days: int = 0,
    ) -> bool:
        return any(
            task.task_type == task_type
            and abs((task.scheduled_date - scheduled_date).days) <= window_days
            for task in tasks
        )

    def _append_audit_log(self, payload: Any) -> None:
        self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        record = payload if isinstance(payload, dict) else asdict(payload)
        with self._audit_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=self._json_default) + "\n")

    def _safe_append_audit_log(self, payload: Any) -> Optional[str]:
        try:
            self._append_audit_log(payload)
        except OSError as exc:
            return f"Audit logging failed safely: {exc}"
        return None

    def _json_default(self, value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if is_dataclass(value):
            return asdict(value)
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
