"""Command line interface with deterministic, sanitized JSON/Markdown output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from . import __version__
from .core import report, run_checks


class UsageError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        # argparse's default errors echo user arguments, including private paths.
        raise UsageError


def render_json(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def render_markdown(document: dict[str, Any]) -> str:
    counts = document["summary"]
    lines = ["# Repository contract check", "",
             f"Passed: {counts['pass']}; Failed: {counts['fail']}; Errors: {counts['error']}", ""]
    if document["results"]:
        lines.extend(["| Repository alias | Rule | Status | Reason |",
                      "| --- | --- | --- | --- |"])
        for item in document["results"]:
            lines.append(f"| `{item['repo']}` | `{item['rule']}` | {item['status']} | `{item['reason']}` |")
        lines.append("")
    if document["errors"]:
        lines.extend(["## Input errors", ""])
        for error in document["errors"]:
            lines.append(f"- `{error['reason']}`")
        lines.append("")
    return "\n".join(lines)


def parser() -> Parser:
    command = Parser(prog="repo-contract-check", allow_abbrev=False,
                     description="Check explicit local JSON/TOML repository contracts offline.")
    command.add_argument("--version", action="version", version=__version__)
    commands = command.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", allow_abbrev=False,
                                help="check explicitly named files and manifest values")
    check.add_argument("contracts", metavar="CONTRACTS", type=Path,
                       help="portable contract file (.json or .toml)")
    check.add_argument("--roots", required=True, metavar="ROOTS", type=Path,
                       help="private alias-to-directory bindings (.json or .toml)")
    check.add_argument("--format", choices=("json", "markdown"), default="markdown",
                       help="report format (default: markdown)")
    return command


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    # Use a requested known format even for argument errors, without echoing input.
    output_format = "markdown"
    for index, argument in enumerate(arguments):
        if argument == "--format=json":
            output_format = "json"
        elif argument == "--format" and arguments[index + 1:index + 2] == ["json"]:
            output_format = "json"
    try:
        options = parser().parse_args(arguments)
        output_format = options.format
        document, code = run_checks(options.contracts, options.roots)
    except UsageError:
        document, code = report([], ["argument_error"])
    except KeyboardInterrupt:
        document, code = report([], ["interrupted"])
    except Exception:
        # A bug must not turn a private filesystem/parser exception into a report.
        document, code = report([], ["internal_error"])
    rendered = render_json(document) if output_format == "json" else render_markdown(document)
    try:
        sys.stdout.write(rendered)
    except (BrokenPipeError, OSError):
        return 2
    return code
