"""Command line interface with deterministic, sanitized JSON/Markdown output."""

from __future__ import annotations

import argparse
from functools import partial
import json
import os
from pathlib import Path
import sys
from typing import Any

from . import __version__
from .core import report, run_checks


class UsageError(Exception):
    pass


class OutputError(Exception):
    pass


def _discard_failed_stream(stream) -> None:
    """Prevent a failed descriptor from being flushed again at shutdown."""
    try:
        descriptor = stream.fileno()
        with open(os.devnull, "wb") as sink:
            os.dup2(sink.fileno(), descriptor)
    except (OSError, AttributeError, ValueError):
        # Closed or text-only captures may have no descriptor to redirect.
        pass


def _write_output(text: str, stream) -> None:
    """Finish short UTF-8 writes and detect buffered errors before success."""
    try:
        binary = getattr(stream, "buffer", None)
        target = stream if binary is None else binary
        payload = text if binary is None else memoryview(text.encode("utf-8"))
        offset = 0
        while offset < len(payload):
            chunk = payload[offset:offset + 65536]
            written = target.write(chunk)
            if type(written) is not int or not 0 < written <= len(chunk):
                raise OSError("output stream did not make valid progress")
            offset += written
        stream.flush()
    except (OSError, ValueError):
        _discard_failed_stream(stream)
        raise OutputError from None


class Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        # argparse's default errors echo user arguments, including private paths.
        raise UsageError

    def _print_message(self, message, file=None) -> None:
        # Help and version output need the same I/O guarantees as reports.
        if message:
            _write_output(message, sys.stderr if file is None else file)


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
    parser_options = {}
    if sys.version_info >= (3, 14):
        parser_options["color"] = False
        if sys.version_info < (3, 15):
            # 3.14 probes stdout before applying parser.color; 3.15 removed
            # the formatter's color constructor argument.
            parser_options["formatter_class"] = partial(argparse.HelpFormatter, color=False)
    command = Parser(prog="repo-contract-check", allow_abbrev=False,
                     description="Check explicit local JSON/TOML repository contracts offline.",
                     **parser_options)
    command.add_argument("--version", action="version", version=__version__)
    commands = command.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", allow_abbrev=False,
                                help="check explicitly named files and manifest values",
                                **parser_options)
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
    except OutputError:
        return 2
    except UsageError:
        document, code = report([], ["argument_error"])
    except KeyboardInterrupt:
        document, code = report([], ["interrupted"])
    except Exception:
        # A bug must not turn a private filesystem/parser exception into a report.
        document, code = report([], ["internal_error"])
    rendered = render_json(document) if output_format == "json" else render_markdown(document)
    try:
        _write_output(rendered, sys.stdout)
    except OutputError:
        return 2
    return code
