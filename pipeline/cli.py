"""Command-line interface for the spec-driven pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline.audit import initialize_run
from pipeline.approval import create_approval
from pipeline.errors import PipelineError
from pipeline.generator import implement_run
from pipeline.planner import create_plan, write_plan
from pipeline.spec_parser import parse_feature_spec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline",
        description="AI-native, spec-driven development pipeline prototype.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    intake = subparsers.add_parser("intake", help="Parse and validate a feature specification.")
    intake.add_argument("spec_file", type=Path)
    intake.set_defaults(func=_cmd_intake)

    plan = subparsers.add_parser("plan", help="Create an implementation plan from a spec.")
    plan.add_argument("spec_file", type=Path)
    plan.set_defaults(func=_cmd_plan)

    approve = subparsers.add_parser("approve", help="Record a human approval checkpoint.")
    approve.add_argument("run_id")
    approve.add_argument("--stage", choices=["plan", "release"], required=True)
    approve.add_argument("--approver", required=True)
    approve.set_defaults(func=_cmd_approve)

    implement = subparsers.add_parser("implement", help="Generate bounded code and tests.")
    implement.add_argument("run_id")
    implement.set_defaults(func=_cmd_implement)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _cmd_intake(args: argparse.Namespace) -> int:
    spec = parse_feature_spec(args.spec_file)
    print(json.dumps(spec.to_json_data(), indent=2))
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    spec = parse_feature_spec(args.spec_file)
    run_id, run_dir, spec_hash = initialize_run(spec, args.spec_file)
    plan = create_plan(spec, run_id, spec_hash)
    write_plan(run_dir, plan, spec)
    print(f"created run: {run_id}")
    print(f"plan: {run_dir / 'plan.md'}")
    print("approve before implementation:")
    print(f"  python -m pipeline approve {run_id} --stage plan --approver <name>")
    return 0


def _cmd_approve(args: argparse.Namespace) -> int:
    approval = create_approval(args.run_id, args.stage, args.approver)
    print(f"approved {approval.stage} for run: {approval.run_id}")
    print(f"approval hash: {approval.signature}")
    return 0


def _cmd_implement(args: argparse.Namespace) -> int:
    manifest = implement_run(args.run_id)
    print(f"generated changes for run: {manifest.run_id}")
    for file_entry in manifest.files:
        print(f"- {file_entry.path}")
    return 0
