"""Behavioral tests use synthetic repositories and no private project data."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from repo_contract_check import core
from repo_contract_check.cli import main, render_json, render_markdown


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="contract-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "synthetic-private-root"
        self.repo.mkdir()
        self.contracts = self.base / "contracts.json"
        self.roots = self.base / "roots.json"
        self.write_json(self.roots, {"schema_version": 1, "roots": {"demo": str(self.repo)}})

    def write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def rule(self, kind="equals", *, id="check", file="package.json", pointer="/value", **extra):
        result = {"id": id, "repo": "demo", "kind": kind, "file": file}
        if kind != "file_exists":
            result["pointer"] = pointer
        if kind == "equals":
            result["expected"] = extra.pop("expected", "ok")
        result.update(extra)
        return result

    def check(self, *rules):
        self.write_json(self.contracts, {"schema_version": 1, "checks": list(rules)})
        return core.run_checks(self.contracts, self.roots)

    def result(self, *rules):
        report, code = self.check(*rules)
        self.assertFalse(report["errors"], report)
        return report["results"][0], code

    def test_all_predicates_and_mixed_repositories(self):
        other = self.base / "worker"
        other.mkdir()
        (other / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n', encoding="utf-8")
        self.write_json(self.repo / "package.json", {"value": ">=22", "scripts": {"verify": "node --test"}})
        self.write_json(self.roots, {"schema_version": 1, "roots": {"demo": str(self.repo), "worker": "worker"}})
        report, code = self.check(
            self.rule(expected=">=22"),
            self.rule("file_exists", id="file"),
            self.rule("value_exists", id="exists", pointer="/scripts/verify"),
            self.rule("nonempty_string", id="script", pointer="/scripts/verify"),
            self.rule(id="python", repo="worker", file="pyproject.toml",
                      pointer="/project/requires-python", expected=">=3.11"),
        )
        self.assertEqual(0, code)
        self.assertEqual({"pass": 5, "fail": 0, "error": 0}, report["summary"])

    def test_each_predicate_failure(self):
        self.write_json(self.repo / "package.json", {"value": "wrong"})
        cases = [(self.rule(), "value_mismatch"),
                 (self.rule("file_exists", file="missing.md"), "file_missing"),
                 (self.rule("value_exists", pointer="/missing"), "value_missing"),
                 (self.rule("nonempty_string", pointer="/missing"), "value_missing")]
        for rule, expected in cases:
            with self.subTest(expected=expected):
                result, code = self.result(rule)
                self.assertEqual(("fail", expected, 1), (result["status"], result["reason"], code))

    def test_missing_manifest_is_failed_expectation(self):
        result, code = self.result(self.rule())
        self.assertEqual(("file_missing", 1), (result["reason"], code))

    def test_null_is_present_and_distinct_from_missing(self):
        self.write_json(self.repo / "package.json", {"value": None})
        report, code = self.check(self.rule(expected=None), self.rule("value_exists", id="exists"))
        self.assertEqual(0, code)
        self.assertEqual(2, report["summary"]["pass"])
        result, code = self.result(self.rule(expected=None, pointer="/missing"))
        self.assertEqual(("value_missing", 1), (result["reason"], code))

    def test_string_empty_whitespace_and_type(self):
        for value, reason in [("", "empty_string"), (" \n\t", "empty_string"),
                              ([], "type_mismatch"), (None, "type_mismatch"),
                              (1, "type_mismatch"), (" npm test ", "nonempty_string")]:
            with self.subTest(reason=reason):
                self.write_json(self.repo / "package.json", {"value": value})
                result, code = self.result(self.rule("nonempty_string"))
                self.assertEqual(reason, result["reason"])
                self.assertEqual(0 if reason == "nonempty_string" else 1, code)

    def test_equality_is_structural_and_type_strict(self):
        cases = [(True, 1, False), (1, 1.0, False), ("1", 1, False),
                 ({"x": [True]}, {"x": [1]}, False),
                 ({"a": 1, "b": [None]}, {"b": [None], "a": 1}, True),
                 ([1, 2], [2, 1], False), (1.5, 1.5, True)]
        for actual, expected, matches in cases:
            with self.subTest(actual=actual, expected=expected):
                self.write_json(self.repo / "package.json", {"value": actual})
                result, code = self.result(self.rule(expected=expected))
                self.assertEqual(0 if matches else 1, code)
                self.assertEqual("value_matches" if matches else "value_mismatch", result["reason"])

    def test_pointer_special_keys_root_and_arrays(self):
        document = {"": "empty", "a/b": "slash", "a~b": "tilde", "~1": "literal",
                    "items": [{"0": "numeric-key"}], "list": ["first", "second"]}
        self.write_json(self.repo / "package.json", document)
        cases = [("", document), ("/", "empty"), ("/a~1b", "slash"),
                 ("/a~0b", "tilde"), ("/~01", "literal"),
                 ("/items/0/0", "numeric-key"), ("/list/1", "second")]
        for pointer, expected in cases:
            with self.subTest(pointer=pointer):
                _, code = self.result(self.rule(pointer=pointer, expected=expected))
                self.assertEqual(0, code)

    def test_noncanonical_and_missing_array_indexes_do_not_resolve(self):
        self.write_json(self.repo / "package.json", {"items": [1]})
        for pointer in ("/items/01", "/items/-", "/items/-1", "/items/1", "/items/+0", "/items/٠", "/items/0/child"):
            with self.subTest(pointer=pointer):
                result, code = self.result(self.rule("value_exists", pointer=pointer))
                self.assertEqual(("value_missing", 1), (result["reason"], code))

    def test_malformed_pointers_fail_configuration(self):
        for pointer in ("field", "#/field", "/~2", "/tail~", 1, None, "/" + "a" * 1024):
            with self.subTest(pointer=pointer):
                report, code = self.check(self.rule(pointer=pointer))
                self.assertEqual(2, code)
                self.assertEqual("invalid_pointer", report["errors"][0]["reason"])

    def test_json_parser_rejects_ambiguity_and_nonfinite_numbers(self):
        cases = [(b'{"value": 1, "value": 2}', "duplicate_key"),
                 (b'{"value": NaN}', "nonfinite_number"),
                 (b'{"value": Infinity}', "nonfinite_number"),
                 (b'{"value": 1e999}', "nonfinite_number"),
                 (b'{"value":', "invalid_document"),
                 (b'\xff', "invalid_document")]
        for data, reason in cases:
            with self.subTest(reason=reason):
                (self.repo / "package.json").write_bytes(data)
                result, code = self.result(self.rule())
                self.assertEqual((reason, 2), (result["reason"], code))

    def test_toml_malformed_and_non_json_values(self):
        source = self.repo / "pyproject.toml"
        for text in ('value = [', 'value = 1\nvalue = 2'):
            source.write_text(text, encoding="utf-8")
            result, code = self.result(self.rule(file="pyproject.toml"))
            self.assertEqual(("invalid_document", 2), (result["reason"], code))
        for text in ('value = 2026-01-01', 'value = nan', 'value = inf', 'value = [2026-01-01]'):
            source.write_text(text, encoding="utf-8")
            result, code = self.result(self.rule(file="pyproject.toml"))
            self.assertEqual(("unsupported_value", 2), (result["reason"], code))
            _, exists_code = self.result(self.rule("value_exists", file="pyproject.toml"))
            self.assertEqual(0, exists_code)

    def test_toml_configuration_and_relative_root(self):
        self.write_json(self.repo / "package.json", {"value": "ok"})
        contract = self.base / "contracts.toml"
        roots = self.base / "roots.toml"
        contract.write_text('schema_version = 1\n[[checks]]\nid="one"\nrepo="demo"\nkind="equals"\nfile="package.json"\npointer="/value"\nexpected="ok"\n', encoding="utf-8")
        roots.write_text('schema_version=1\n[roots]\ndemo="synthetic-private-root"\n', encoding="utf-8")
        _, code = core.run_checks(contract, roots)
        self.assertEqual(0, code)

    def test_invalid_contract_shapes_are_not_silent_passes(self):
        valid = self.rule()
        documents = [{}, [], {"schema_version": True, "checks": [valid]},
                     {"schema_version": 1, "checks": []},
                     {"schema_version": 1, "checks": [valid, valid]},
                     {"schema_version": 1, "checks": [{**valid, "unknown": 1}]},
                     {"schema_version": 1, "checks": [{**valid, "kind": "execute"}]},
                     {"schema_version": 1, "checks": [{**valid, "kind": []}]},
                     {"schema_version": 1, "checks": [{**valid, "id": "bad|table"}]},
                     {"schema_version": 1, "checks": [valid], "extra": 1},
                     {"schema_version": 2, "checks": [valid]}]
        for document in documents:
            with self.subTest(document=document):
                self.write_json(self.contracts, document)
                report, code = core.run_checks(self.contracts, self.roots)
                self.assertEqual(2, code)
                self.assertEqual("invalid_contract", report["errors"][0]["reason"])

    def test_invalid_roots_and_unknown_alias(self):
        for roots in ({}, {"schema_version": 1, "roots": {}},
                      {"schema_version": True, "roots": {"demo": "x"}},
                      {"schema_version": 1, "roots": {"bad|alias": "x"}},
                      {"schema_version": 1, "roots": {"demo": ""}},
                      {"schema_version": 1, "roots": {"demo": "//host/share"}}):
            self.write_json(self.roots, roots)
            report, code = self.check(self.rule())
            self.assertEqual(("invalid_roots", 2), (report["errors"][0]["reason"], code))
        self.write_json(self.roots, {"schema_version": 1, "roots": {"different": str(self.repo)}})
        report, code = self.check(self.rule())
        self.assertEqual(("unknown_repo", 2), (report["errors"][0]["reason"], code))

    def test_maximum_check_count(self):
        rules = [self.rule(id=f"rule-{i}") for i in range(core.MAX_CHECKS + 1)]
        report, code = self.check(*rules)
        self.assertEqual(("invalid_contract", 2), (report["errors"][0]["reason"], code))

    def test_duplicate_configuration_keys_rejected(self):
        self.contracts.write_text('{"schema_version":1,"checks":[],"checks":[]}', encoding="utf-8")
        report, code = core.run_checks(self.contracts, self.roots)
        self.assertEqual(("contracts_duplicate_key", 2), (report["errors"][0]["reason"], code))

    def test_unsafe_source_paths_rejected_before_reading(self):
        for path in ("../outside.json", "/absolute.json", "a/../b.json", "a//b.json",
                     "./package.json", "C:/private.json", "C:private.json",
                     "a\\b.json", "", "a\x00.json", "package.json:stream.json",
                     ".. /outside.json", "folder./package.json", "NUL.json", "COM1.json",
                     "COM¹.json", "NUL .json"):
            with self.subTest(path=path):
                report, code = self.check(self.rule(file=path))
                self.assertEqual(("invalid_contract", 2), (report["errors"][0]["reason"], code))

    def test_sensitive_named_locations_refused_for_content(self):
        for path in (".env.json", ".aws/config.json", ".git/config.json",
                     "nested/secrets.toml", "credentials.json"):
            report, code = self.check(self.rule(file=path))
            self.assertEqual(("sensitive_path_refused", 2), (report["errors"][0]["reason"], code))

    def test_archive_and_other_content_formats_rejected(self):
        for path in ("source.zip", "source.tar.gz", "config.yaml", ".env"):
            report, code = self.check(self.rule(file=path))
            self.assertEqual(("unsupported_source_format", 2), (report["errors"][0]["reason"], code))

    def test_nonregular_file_refused(self):
        (self.repo / "package.json").mkdir()
        for rule in (self.rule(), self.rule("file_exists")):
            result, code = self.result(rule)
            self.assertEqual(("not_regular_file", 2), (result["reason"], code))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO fixture requires POSIX")
    def test_fifo_refused_without_blocking(self):
        os.mkfifo(self.repo / "package.json")
        result, code = self.result(self.rule())
        self.assertEqual(("not_regular_file", 2), (result["reason"], code))

    def symlink(self, source, destination, directory=False):
        try:
            destination.symlink_to(source, target_is_directory=directory)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Symlink fixture unavailable: {type(error).__name__}")

    def test_file_symlink_refused(self):
        outside = self.base / "outside.json"
        self.write_json(outside, {"value": "PRIVATE-SYNTHETIC"})
        self.symlink(outside, self.repo / "package.json")
        result, code = self.result(self.rule())
        self.assertEqual(("symlink_refused", 2), (result["reason"], code))

    def test_parent_symlink_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        self.write_json(outside / "package.json", {"value": "PRIVATE-SYNTHETIC"})
        self.symlink(outside, self.repo / "linked", directory=True)
        result, code = self.result(self.rule(file="linked/package.json"))
        self.assertEqual(("symlink_refused", 2), (result["reason"], code))

    def test_root_symlink_refused(self):
        linked = self.base / "linked-root"
        self.symlink(self.repo, linked, directory=True)
        self.write_json(self.roots, {"schema_version": 1, "roots": {"demo": str(linked)}})
        result, code = self.result(self.rule())
        self.assertEqual(("symlink_refused", 2), (result["reason"], code))

    def test_config_symlink_refused(self):
        source = self.base / "source.json"
        self.write_json(source, {"schema_version": 1, "checks": [self.rule()]})
        self.symlink(source, self.contracts)
        report, code = core.run_checks(self.contracts, self.roots)
        self.assertEqual(("contracts_symlink_refused", 2), (report["errors"][0]["reason"], code))

    def test_missing_root_error_and_other_repository_continues(self):
        self.write_json(self.repo / "package.json", {"value": "ok"})
        self.write_json(self.roots, {"schema_version": 1, "roots": {"demo": str(self.repo), "absent": "absent"}})
        report, code = self.check(self.rule(id="valid"), self.rule(id="missing", repo="absent"))
        self.assertEqual(2, code)
        self.assertEqual({"pass": 1, "fail": 0, "error": 1}, report["summary"])
        self.assertEqual("root_missing", report["results"][0]["reason"])

    def test_limits_and_error_precedence(self):
        (self.repo / "large.json").write_bytes(b" " * (core.MAX_DOCUMENT_BYTES + 1))
        report, code = self.check(self.rule(file="large.json", id="large"),
                                  self.rule("file_exists", id="missing", file="missing.md"))
        self.assertEqual(2, code)
        self.assertEqual({"pass": 0, "fail": 1, "error": 1}, report["summary"])
        self.assertEqual("file_too_large", report["results"][0]["reason"])
        self.write_json(self.repo / "package.json", {"value": "ok"})
        with patch.object(core, "MAX_SOURCE_BYTES", 3):
            result, code = self.result(self.rule())
        self.assertEqual(("read_budget_exceeded", 2), (result["reason"], code))

    def test_nesting_limit(self):
        (self.repo / "package.json").write_text("[" * 66 + "0" + "]" * 66, encoding="utf-8")
        result, code = self.result(self.rule("value_exists", pointer=""))
        self.assertEqual(("nesting_limit", 2), (result["reason"], code))

    def test_same_size_change_is_read_on_next_run(self):
        source = self.repo / "package.json"
        source.write_text('{"value":"aa"}', encoding="utf-8")
        _, first = self.result(self.rule(expected="aa"))
        stamp = source.stat()
        source.write_text('{"value":"bb"}', encoding="utf-8")
        os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        _, second = self.result(self.rule(expected="aa"))
        self.assertEqual((0, 1), (first, second))

    def test_manifest_read_once_per_run(self):
        self.write_json(self.repo / "package.json", {"value": "ok"})
        original = core.file_access
        seen = []
        def tracked(root, relative, **options):
            if options.get("read"):
                seen.append(relative)
            return original(root, relative, **options)
        with patch.object(core, "file_access", side_effect=tracked):
            _, code = self.check(self.rule(id="a"), self.rule(id="b"))
        self.assertEqual(0, code)
        self.assertEqual(1, seen.count("package.json"))

    def test_read_only_no_network_no_commands_no_unrelated_reads(self):
        sentinel = self.repo / "SHOULD-NOT-EXIST"
        self.write_json(self.repo / "package.json", {"value": f"touch {sentinel}"})
        (self.repo / ".env").write_text("PRIVATE-SYNTHETIC", encoding="utf-8")
        self.write_json(self.repo / "credentials.json", {"secret": "PRIVATE-SYNTHETIC"})
        self.write_json(self.repo / "unrelated.json", {"secret": "PRIVATE-SYNTHETIC"})
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.repo.iterdir()}
        original = core.file_access
        seen = []
        def tracked(root, relative, **options):
            seen.append(relative)
            return original(root, relative, **options)
        with patch.object(core, "file_access", side_effect=tracked), \
                patch.object(socket, "socket", side_effect=AssertionError("network attempted")), \
                patch.object(subprocess, "Popen", side_effect=AssertionError("command attempted")):
            _, code = self.check(self.rule("nonempty_string"))
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.repo.iterdir()}
        self.assertEqual(0, code)
        self.assertEqual(before, after)
        self.assertEqual({"contracts.json", "roots.json", "package.json"}, set(seen))
        self.assertFalse(sentinel.exists())

    def test_file_exists_does_not_read_contents(self):
        (self.repo / "report.md").write_text("PRIVATE-SYNTHETIC", encoding="utf-8")
        original = core.file_access
        def tracked(root, relative, **options):
            if relative == "report.md":
                self.assertFalse(options["read"])
            return original(root, relative, **options)
        with patch.object(core, "file_access", side_effect=tracked):
            _, code = self.result(self.rule("file_exists", file="report.md"))
        self.assertEqual(0, code)

    def test_json_and_markdown_reports_are_deterministic_and_value_free(self):
        secret = "PRIVATE-SYNTHETIC-SECRET"
        self.write_json(self.repo / "package.json", {"value": secret})
        first, _ = self.check(self.rule(expected="OTHER-PRIVATE-SYNTHETIC", id="z"),
                              self.rule("value_exists", id="a"))
        second, _ = core.run_checks(self.contracts, self.roots)
        for render in (render_json, render_markdown):
            output = render(first)
            self.assertEqual(output, render(second))
            for forbidden in (secret, "OTHER-PRIVATE-SYNTHETIC", str(self.repo), "package.json", "/value"):
                self.assertNotIn(forbidden, output)
        self.assertEqual(["a", "z"], [result["rule"] for result in first["results"]])

    def cli(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_errors_never_echo_values_paths_or_unknown_arguments(self):
        secret = "PRIVATE-SYNTHETIC-SECRET"
        (self.repo / "package.json").write_text('{"value":"' + secret, encoding="utf-8")
        self.write_json(self.contracts, {"schema_version": 1, "checks": [self.rule()]})
        args = ["check", str(self.contracts), "--roots", str(self.roots), "--format", "json"]
        for arguments in (args, args + ["--unknown", secret + str(self.repo)],
                          ["check", str(self.repo / "missing.json"), "--roots", str(self.roots), "--format", "json"]):
            code, stdout, stderr = self.cli(arguments)
            self.assertEqual(2, code)
            json.loads(stdout)
            self.assertNotIn(secret, stdout + stderr)
            self.assertNotIn(str(self.repo), stdout + stderr)
            self.assertEqual("", stderr)

    def test_os_and_unexpected_exception_text_is_sanitized(self):
        secret = "PRIVATE-SYNTHETIC-SECRET"
        self.write_json(self.contracts, {"schema_version": 1, "checks": [self.rule()]})
        args = ["check", str(self.contracts), "--roots", str(self.roots), "--format=json"]
        with patch("repo_contract_check.cli.run_checks", side_effect=RuntimeError(secret + str(self.repo))):
            code, stdout, stderr = self.cli(args)
        self.assertEqual(2, code)
        self.assertEqual("internal_error", json.loads(stdout)["errors"][0]["reason"])
        self.assertNotIn(secret, stdout + stderr)
        self.assertNotIn(str(self.repo), stdout + stderr)

    def test_os_error_text_is_sanitized(self):
        secret = "PRIVATE-SYNTHETIC-SECRET"
        self.write_json(self.contracts, {"schema_version": 1, "checks": [self.rule()]})
        args = ["check", str(self.contracts), "--roots", str(self.roots), "--format", "json"]
        with patch.object(core.os, "open", side_effect=PermissionError(secret + str(self.repo))):
            code, stdout, stderr = self.cli(args)
        self.assertEqual(2, code)
        self.assertEqual("contracts_read_error", json.loads(stdout)["errors"][0]["reason"])
        self.assertNotIn(secret, stdout + stderr)
        self.assertNotIn(str(self.repo), stdout + stderr)

    def test_portable_file_access_branch(self):
        self.write_json(self.repo / "package.json", {"value": "ok"})
        with patch.object(core.os, "supports_dir_fd", set()):
            _, code = self.result(self.rule())
        self.assertEqual(0, code)

    def test_windows_reparse_point_refused_without_junction_api(self):
        folder = self.repo / "linked"
        folder.mkdir()
        original = Path.lstat
        def synthetic_reparse(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if path == folder:
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            return info
        with patch.object(core.os, "supports_dir_fd", set()), \
                patch.object(Path, "lstat", synthetic_reparse):
            result, code = self.result(self.rule(file="linked/package.json"))
        self.assertEqual(("symlink_refused", 2), (result["reason"], code))

    def test_module_entrypoint(self):
        self.write_json(self.repo / "package.json", {"value": "ok"})
        self.write_json(self.contracts, {"schema_version": 1, "checks": [self.rule()]})
        result = subprocess.run([sys.executable, "-m", "repo_contract_check", "check",
                                 str(self.contracts), "--roots", str(self.roots), "--format", "json"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        self.assertEqual(1, json.loads(result.stdout)["summary"]["pass"])
        self.assertEqual("", result.stderr)


class CommittedExampleTests(unittest.TestCase):
    def test_examples_are_runnable_and_synthetic(self):
        base = Path(__file__).resolve().parents[1] / "examples"
        for filename in ("contracts.json", "contracts.toml"):
            report, code = core.run_checks(base / filename, base / "roots.example.json")
            self.assertEqual(0, code, report)
            self.assertEqual(6, report["summary"]["pass"])
        report, code = core.run_checks(base / "contracts.failing.json", base / "roots.example.json")
        self.assertEqual(1, code)
        self.assertEqual(1, report["summary"]["fail"])


if __name__ == "__main__":
    unittest.main()
