# AI-Native Spec-Driven Development Pipeline

This repository contains a Python 3.11 prototype for an AI-native, spec-driven development pipeline. It turns a structured feature specification into an implementation plan, bounded generated code, generated tests, validation artefacts, human approvals, and deployment evidence.

The workflow borrows from GitHub Spec Kit concepts: specification as the source of truth, followed by planning, tasking, analysis, implementation, and governance gates. The prototype does not depend on Spec Kit at runtime.

## Setup

```powershell
python -m pip install -e ".[dev]"
```

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

The default provider is deterministic and local:

```powershell
$env:PIPELINE_AI_PROVIDER = "local"
```

An optional OpenAI-compatible adapter is available:

```powershell
$env:PIPELINE_AI_PROVIDER = "openai"
$env:OPENAI_API_KEY = "<key>"
$env:OPENAI_MODEL = "gpt-4.1-mini"
```

All provider interactions are captured in `audit/runs/<run-id>/ai_interactions.jsonl`.

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

## Verification

```powershell
python -m ruff check .
python -m mypy pipeline demo_app/src
python -m pytest
```
