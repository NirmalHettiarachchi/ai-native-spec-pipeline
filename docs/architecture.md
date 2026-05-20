# Architecture

The pipeline is organized as a deterministic shell around optional AI-assisted generation.

## Stages

1. Intake parses Markdown, YAML, or JSON into a normalized feature specification.
2. Planning converts the specification into a technical design summary, implementation tasks, impacted files, risks, and a test strategy.
3. Plan approval records a human checkpoint before any code generation.
4. Implementation asks an AI provider abstraction for a change set, then writes only files allowed by the approved plan.
5. Validation runs lint, type, test, security, and policy gates.
6. Release approval records a human checkpoint after validation.
7. Evidence writes a release packet with hashes, approvals, validation results, and Git commit state.

## Governance Model

The implementation keeps AI output bounded by deterministic controls:

- every generated file must appear in a manifest before it is written
- writes are restricted to approved paths
- acceptance tests must trace back to every acceptance criterion ID
- approvals bind to artefact hashes
- audit records capture prompts, provider metadata, outputs, and gate results

## Source-Control Practice

The repository is intentionally committed in small milestones:

- project and tooling bootstrap
- spec intake
- planning
- approvals
- bounded generation
- quality gates and evidence
- documentation and verification

This matches the pipeline's own governance posture: reviewable changes, visible checkpoints, and no single opaque final commit.
