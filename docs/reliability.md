# Reliability Notes

## What proves the AI works

### Automated tests

Run:

```bash
python -B -m pytest tests/test_pawpal.py tests/test_pawpal_ai.py -q --basetemp .pytest_tmp
```

Current coverage includes:

- Existing domain tests for sorting, recurrence, conflict detection, scoring, and target reset.
- New AI tests for:
  - retrieval choosing the right knowledge document for a dog exercise query
  - emergency guardrails blocking unsafe health-style prompts
  - plan generation using live pet data and attaching evidence
  - duplicate-safe task application
  - audit log writing

At the end of development, the combined suite passed with `40` tests.

### Confidence scoring

Each AI plan includes a confidence score. The score rises when:

- care targets exist
- a current care score is available
- recent activities are logged
- relevant knowledge documents are retrieved
- actions survive the self-check stage with evidence and citations

The score drops when:

- targets are missing
- activity history is sparse
- the request triggers a safety guardrail and the coach deliberately narrows its response

### Logging and safe failure

- Every AI plan is appended to `logs/pawpal_ai_runs.jsonl`.
- Task applications are logged as separate events.
- Logging failures are caught and surfaced as warnings instead of crashing the app.

### Manual review

Three manual spot checks were used during development:

| Scenario | Expected behavior | Observed result |
|---|---|---|
| Pet has low exercise and no walk tasks | Suggest a walk with evidence | Coach recommended a recurring walk and cited exercise guidance |
| Prompt mentions poisoning/vomiting | Stop routine advice and escalate | Coach returned a veterinary handoff instead of task automation |
| Plan applied twice | Avoid duplicate tasks | First apply created tasks, second apply converted repeats into skips |

## Known reliability boundaries

- The retriever uses keyword scoring over a curated local knowledge base, not embeddings or web search.
- The planner is specialized for routine pet care, not free-form medical reasoning.
- Streamlit UI behavior is best verified by running the app normally with `streamlit run app.py`.
