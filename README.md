# AI-Native Spec-Driven Development Pipeline

This repository contains a Python 3.11 prototype for an AI-native, spec-driven development pipeline. It turns a structured feature specification into an implementation plan, bounded generated code, generated tests, validation artefacts, human approvals, and deployment evidence.

The workflow borrows from GitHub Spec Kit concepts: specification as the source of truth, followed by planning, tasking, analysis, implementation, and governance gates. The prototype does not depend on Spec Kit at runtime.

## Setup

```powershell
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edit `.env` if you want live OpenAI-backed generation. The default `auto` mode uses OpenAI
when `OPENAI_API_KEY` is configured and falls back to deterministic local generation when it is not.

## Local Governance UI

Start the local dashboard:

```powershell
python -m pipeline_web
```

Open `http://127.0.0.1:8000`. The UI reads and writes the same audit artefacts as the CLI, so both interfaces remain interoperable.

The dashboard supports:

- creating a run from either a known repository spec or an uploaded `.yaml`, `.yml`, `.json`, `.md`, or `.markdown` spec
- viewing sanitized AI provider readiness, including mode, resolved provider, model, and credential presence
- paging recent runs with `?page=<n>&page_size=<n>`; the default page size is 10
- reviewing the normalized spec, plan, AI interactions, generated change manifest, validation gates, approvals, and evidence
- approving the plan before implementation
- generating implementation and tests
- running validation gates
- approving release only after validation passes
- generating deployment evidence after release approval

Uploaded specs are saved under `specs/uploads/` and ignored by Git except for the directory marker.

Lightweight JSON endpoints are also available for assessment review:

- `GET /api/health`
- `GET /api/config`
- `GET /api/runs`
- `GET /api/runs/{run-id}`

## Input Contract

Specs can be Markdown, YAML, or JSON. The normalized schema requires:

- `feature_objective`
- `user_story`
- `business_rules`
- `acceptance_criteria`
- `non_functional_requirements`
- `out_of_scope`

Acceptance criteria must have stable IDs, such as `AC-001`, so generated tests and policy checks can map coverage back to the spec.

## Manual Workflow

```powershell
python -m pipeline intake specs/examples/discount_calculator.yaml
python -m pipeline plan specs/examples/discount_calculator.yaml
python -m pipeline approve <run-id> --stage plan --approver "Your Name"
python -m pipeline implement <run-id>
python -m pipeline validate <run-id>
python -m pipeline approve <run-id> --stage release --approver "Your Name"
python -m pipeline evidence <run-id>
```

The resumable orchestration command creates pause points instead of silently approving its own work:

```powershell
python -m pipeline run specs/examples/discount_calculator.yaml
python -m pipeline approve <run-id> --stage plan --approver "Your Name"
python -m pipeline run specs/examples/discount_calculator.yaml --run-id <run-id>
python -m pipeline approve <run-id> --stage release --approver "Your Name"
python -m pipeline run specs/examples/discount_calculator.yaml --run-id <run-id>
```

## AI Provider

The default provider mode is `auto`:

```powershell
$env:PIPELINE_AI_PROVIDER = "auto"
```

In `auto` mode, the pipeline uses OpenAI when `OPENAI_API_KEY` is configured and otherwise
uses the deterministic local template provider. Explicit modes are also supported:

```powershell
$env:PIPELINE_AI_PROVIDER = "openai"
$env:OPENAI_API_KEY = "<key>"
$env:OPENAI_MODEL = "gpt-4o-mini"
```

`OPENAI_REASONING_EFFORT` is only sent when the configured model supports reasoning controls.

```powershell
$env:PIPELINE_AI_PROVIDER = "local"
```

The OpenAI provider uses the Responses API with Structured Outputs. All provider interactions
are captured in `audit/runs/<run-id>/ai_interactions.jsonl` with sanitized request metadata,
response IDs, usage, prompts, and generated outputs. API keys are never written to audit files
or the dashboard.

## Quality Gates

`python -m pipeline validate <run-id>` runs:

- `ruff check .`
- `mypy pipeline demo_app/src`
- `pytest`
- `bandit` against runtime source
- a custom policy gate for allowed paths, manifest hashes, and acceptance-criteria coverage

The pipeline fails closed when a required gate, approval, or artefact is missing.

## Audit Artefacts

Each run writes:

- `spec.normalized.json`
- `plan.json` and `plan.md`
- `approval.plan.json`
- `ai_interactions.jsonl`
- `generated_output.json`
- `change_manifest.json`
- `change_summary.md`
- `validation_results.json`
- `approval.release.json`
- `deployment_evidence.md`

Generated audit runs live under `audit/runs/<run-id>/` and are ignored by Git to keep local executions reproducible without creating source-control noise.

## Assessment Coverage

| Requirement | Implementation | UI Flow |
| --- | --- | --- |
| Spec Intake | `pipeline/spec_parser.py` normalizes Markdown, YAML, and JSON specs | Create Run spec selector/upload |
| Planning Layer | `pipeline/planner.py` writes `plan.json` and `plan.md` | Run detail workflow and artefacts |
| AI-assisted Implementation | `pipeline/ai.py` and `pipeline/generator.py` produce bounded changes | Generate Implementation action |
| Automated Test Generation | Generated test files map to acceptance criterion IDs | Generated Changes and Coverage panels |
| Quality Gates | `pipeline/gates.py` runs lint, type, test, security, and policy checks | Run Validation action and Validation panel |
| Human Approval Workflow | `pipeline/approval.py` records hash-bound plan/release approvals | Approve Plan and Approve Release actions |
| Auditability | `pipeline/audit.py` captures versioned run artefacts | Artefacts and Coverage panels |

## Verification

```powershell
python -m ruff check .
python -m mypy pipeline pipeline_web demo_app/src
python -m pytest
python -m bandit -q -r pipeline pipeline_web demo_app/src -x tests,demo_app/tests -ll
```
