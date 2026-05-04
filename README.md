# PawPal+ AI Care Coach

PawPal+ started as a pet-care tracking app. It is now an applied AI system for routine pet-care planning: it reads live care data, retrieves relevant guidance from a local knowledge base, explains what needs attention, and can turn reviewed recommendations into schedule tasks.

## What the project does

### Core app features

- Multi-pet accounts with pet profiles
- Care targets for meals, exercise, grooming, and vet intervals
- Activity logging with backdated entries
- Care score calculation with history
- Task scheduling with recurrence and conflict detection

### New AI features

- `RAG`: the coach retrieves local pet-care guidance before answering
- `Agentic workflow`: it gathers context, retrieves evidence, drafts actions, self-checks them, and scores confidence
- `Reliability system`: tests, audit logs, duplicate-task prevention, and safety guardrails are integrated into the main workflow
- `Human-in-the-loop automation`: suggested tasks are only added after the user reviews and approves them

## Why this is useful

The original app could tell you that a pet's score was low or that tasks were overdue. The new AI coach closes the gap between data and action by answering questions like:

- "What needs attention this week?"
- "Why is my care score low?"
- "What should I schedule next?"
- "Summarize the biggest routine gaps and suggest the next best tasks."

## Project structure

```text
app.py                               Streamlit application
main.py                              CLI demo, now including the AI coach
pawpal_system.py                     Core domain models and services
pawpal_ai.py                         Retrieval, planning, verification, confidence, logging
knowledge_base/pet_care_knowledge.json
tests/test_pawpal.py                 Existing domain tests
tests/test_pawpal_ai.py              AI workflow and reliability tests
docs/                                Architecture, reliability, reflection, collaboration notes
```

## Setup

### Requirements

- Python 3.10+
- pip

### Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run the project

### Streamlit app

```bash
streamlit run app.py
```

Open the `AI Care Coach` tab after creating at least one pet and some care data.

### CLI demo

```bash
python main.py
```

The CLI demo now prints a sample AI care-plan summary in addition to the original scheduling demo.

## Test the project

```bash
python -B -m pytest tests/test_pawpal.py tests/test_pawpal_ai.py -q --basetemp .pytest_tmp
```

The latest full run passed `40` tests.

## Logging and guardrails

- AI plan runs are written to `logs/pawpal_ai_runs.jsonl`
- Task-application events are logged separately
- Emergency-style prompts are blocked and escalated to a veterinarian handoff
- Duplicate AI task suggestions are prevented before they reach the schedule

## Documentation

- [Documentation index](./docs/README.md)
- [System overview and diagram](./docs/system-overview.md)
- [Reliability notes](./docs/reliability.md)
- [Responsible AI reflection](./docs/responsible-ai-reflection.md)
- [AI collaboration notes](./docs/ai-collaboration.md)
