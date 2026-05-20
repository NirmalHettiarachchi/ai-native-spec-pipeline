"""Command-line interface for the spec-driven pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline.errors import PipelineError
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

