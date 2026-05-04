# Responsible AI Reflection

## Limitations and biases

- The system is strongest on routine, measurable care tasks because it reasons over structured targets, schedules, and logs. It is weaker on fuzzy concerns that are hard to quantify.
- The knowledge base is intentionally small and local, so it reflects the topics and assumptions we curated. Right now it is best for dogs, cats, and general household routine planning.
- The planner may overvalue actions that are easy to schedule because the app's data model is task-oriented. That is useful for automation, but it can bias the system toward "add a task" as a solution.

## Possible misuse and prevention

- Misuse risk: asking the coach to diagnose illness or handle an emergency.
  Prevention: emergency guardrails detect risky symptom language and stop the normal planning workflow with a veterinary handoff.
- Misuse risk: blindly trusting automation.
  Prevention: AI-generated task suggestions are shown for human review before they are added to the schedule.
- Misuse risk: schedule spam from repeated AI runs.
  Prevention: the verifier and task application layer block duplicate tasks on the same date.

## What surprised me while testing reliability

- The biggest surprise was how quickly duplicate suggestions became a usability problem. Without the self-check stage, the coach kept finding the same real gap and trying to schedule the same fix repeatedly.
- Another useful lesson was that confidence should drop sharply when targets are missing. The planner can still say something sensible, but the advice becomes much less specific without structured goals.
