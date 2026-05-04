# System Diagram

This page contains the primary system diagram for the PawPal+ AI Care Coach. It shows the main components, the runtime data flow from input to output, and where humans and testing are involved.

## Architecture Diagram

```mermaid
flowchart LR
    Human["Pet owner"] --> UI["Streamlit UI / CLI demo"]
    UI --> Core["PawPal core services\npets, targets, activities,\nscores, tasks, conflicts"]
    UI --> Coach["AI Care Coach\norchestrator"]

    Coach --> Guardrails["Safety guardrails\nemergency boundary"]
    Guardrails --> Snapshot["Context builder\nlive pet snapshot"]
    Snapshot --> Retriever["Retriever\nlocal knowledge base"]
    Retriever --> Planner["Planner\ndraft findings + actions"]
    Planner --> Verifier["Verifier\ncitations, dedupe,\nconsistency checks,\nconfidence scoring"]

    Core --> Snapshot
    Verifier --> Logger["Audit logger\nJSONL run history"]
    Verifier --> Review["Human review"]
    Review -->|Approve AI task suggestions| Apply["Task application"]
    Apply --> Core
    Verifier --> Output["Summary, findings,\nconfidence, evidence,\noptional task suggestions"]
    Output --> UI

    Tests["Automated tests"] --> Retriever
    Tests --> Guardrails
    Tests --> Verifier
    Tests --> Apply
```

## Runtime Data Flow

```mermaid
sequenceDiagram
    participant Owner as Pet owner
    participant App as Streamlit app
    participant Core as Core services
    participant AI as AI Care Coach
    participant KB as Knowledge base
    participant Log as Audit log

    Owner->>App: Enter pet data + ask AI question
    App->>Core: Read pets, targets, activities, tasks, conflicts
    App->>AI: Generate care plan request
    AI->>AI: Apply guardrails
    AI->>Core: Build live context snapshot
    AI->>KB: Retrieve relevant care guidance
    AI->>AI: Draft actions, self-check, score confidence
    AI->>Log: Save run metadata
    AI-->>App: Return summary, findings, evidence, suggestions
    App-->>Owner: Show plan for review
    Owner->>App: Approve task suggestions
    App->>AI: Apply approved suggestions
    AI->>Core: Create non-duplicate tasks
    AI->>Log: Save task-application event
    App-->>Owner: Show updated schedule
```

## What the Diagram Highlights

- `Input -> process -> output`: owner request and live app data flow through retrieval, planning, verification, and back to the UI.
- `Human-in-the-loop control`: the owner reviews the AI output before any suggested tasks are added.
- `Testing and reliability`: automated tests target the retriever, guardrails, verifier, and task application steps.
