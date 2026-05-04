# Demo Walkthrough

This walkthrough shows the system running end-to-end with three example user inputs and the corresponding AI responses. It is backed by the runnable script [demo_walkthrough.py](../demo_walkthrough.py).

## Run It

```bash
python demo_walkthrough.py
```

## What the Demo Covers

### Example 1: Weekly planning and task application

User input:

```text
Explain what needs attention this week and suggest the next best routine-care tasks.
```

What it demonstrates:

- live pet data is read from the core app services
- the AI retrieves grounded knowledge before answering
- the planner recommends actions with priorities and rationale
- approved AI suggestions are turned into scheduled tasks
- duplicate-safe task application is shown in the final schedule state

### Example 2: Schedule-aware reasoning for backlog and conflicts

User input:

```text
Summarize Luna's biggest routine gaps and tell me whether I should reschedule anything.
```

What it demonstrates:

- the AI notices routine gaps from care scores and activity logs
- the AI reasons over scheduling conflicts and overloaded days
- the app keeps a human in the loop instead of silently rescheduling tasks

### Example 3: Emergency guardrail

User input:

```text
Pepper ate something toxic and is vomiting. What should I do?
```

What it demonstrates:

- the safety boundary interrupts normal planning
- the AI returns a veterinary handoff instead of routine task automation

## Why this qualifies as end-to-end

The walkthrough shows the full chain:

1. structured pet data and user prompt enter the system
2. the AI coach builds a live snapshot and retrieves supporting knowledge
3. the planner drafts findings and actions
4. the verifier adds confidence, deduplication, and guardrails
5. the system either applies approved tasks or safely stops at escalation

## Related Files

- [demo_walkthrough.py](../demo_walkthrough.py)
- [System Diagram](./system-diagram.md)
- [System Overview](./system-overview.md)
