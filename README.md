# AI-Native Spec-Driven Development Pipeline

This repository contains a Python prototype for a spec-driven development pipeline. It turns a structured feature specification into a technical plan, bounded generated code, generated tests, validation results, human approvals, and deployment evidence.

The implementation is intentionally self-contained: it can run with a deterministic local generator, while leaving an adapter seam for OpenAI-compatible LLM providers.

## Current Workflow

```powershell
python -m pipeline intake specs/examples/discount_calculator.yaml
python -m pipeline plan specs/examples/discount_calculator.yaml
python -m pipeline approve <run-id> --stage plan --approver "Your Name"
python -m pipeline implement <run-id>
python -m pipeline validate <run-id>
python -m pipeline approve <run-id> --stage release --approver "Your Name"
python -m pipeline evidence <run-id>
```

The pipeline records generated artefacts under `audit/runs/<run-id>/`. Generated audit runs are ignored by Git so local executions do not pollute source control history.

## Design References

The workflow borrows from GitHub Spec Kit concepts: specification as the source of truth, followed by planning, tasks, analysis, implementation, and governance gates. This prototype does not depend on Spec Kit at runtime.

