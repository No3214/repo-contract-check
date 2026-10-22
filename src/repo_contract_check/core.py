"""Strict configuration, bounded reads, and explicit contract predicates."""

from __future__ import annotations

import errno
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import tomllib
from dataclasses import dataclass
from typing import Any

MAX_DOCUMENT_BYTES = 1_048_576
MAX_SOURCE_BYTES = 8 * MAX_DOCUMENT_BYTES
MAX_CHECKS = 256
MAX_DEPTH = 64
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
ARRAY_INDEX = re.compile(r"(?:0|[1-9][0-9]*)\Z")
KINDS = frozenset({"file_exists", "value_exists", "equals", "nonempty_string"})
SENSITIVE_DIRS = frozenset({".git", ".ssh", ".aws", ".gnupg", ".azure", ".kube"})
SENSITIVE_STEMS = frozenset({"credentials", "secrets", "private-key", "private_key"})
WINDOWS_DEVICES = frozenset({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
                           | {f"{prefix}{number}" for prefix in ("COM", "LPT")
                              for number in (*range(1, 10), "¹", "²", "³")})


class InputError(Exception):
    """A fixed, shareable reason code, never the underlying exception text."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Check:
    id: str
    repo: str
    kind: str
    file: str
    tokens: tuple[str, ...] = ()
    expected: Any = None


def pointer_tokens(pointer: str) -> tuple[str, ...]:
    """Parse RFC 6901 string syntax (URI fragments are intentionally excluded)."""
    if not isinstance(pointer, str) or len(pointer) > 1024:
        raise InputError("invalid_pointer")
    if pointer == "":
        return ()
    if not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
        raise InputError("invalid_pointer")
    return tuple(token.replace("~1", "/").replace("~0", "~")
                 for token in pointer[1:].split("/"))


def resolve_pointer(document: Any, tokens: tuple[str, ...]) -> tuple[bool, Any]:
    current = document
    for token in tokens:
        if isinstance(current, dict):
            if token not in current:
                return False, None
            current = current[token]
        elif isinstance(current, list):
            if not ARRAY_INDEX.fullmatch(token):
                return False, None
            index = int(token)
            if index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def json_value(value: Any, depth: int = 0) -> bool:
    """Whether a value has bounded, finite JSON data types."""
    if depth > MAX_DEPTH:
        return False
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(json_value(item, depth + 1) for item in value)
    if type(value) is dict:
        return all(type(key) is str and json_value(item, depth + 1)
                   for key, item in value.items())
    return False


def strict_equal(left: Any, right: Any) -> bool:
    """Structural equality without Python's bool/int or int/float coercion."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return (left.keys() == right.keys()
                and all(strict_equal(left[key], right[key]) for key in left))
    if isinstance(left, list):
        return (len(left) == len(right)
                and all(strict_equal(a, b) for a, b in zip(left, right)))
    return bool(left == right)


def _nesting(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise InputError("nesting_limit")
    if isinstance(value, dict):
        for item in value.values():
            _nesting(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _nesting(item, depth + 1)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate_key")
        result[key] = value
    return result


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise InputError("nonfinite_number")
    return value


def _reject_constant(_text: str) -> Any:
    raise InputError("nonfinite_number")


def parse_document(data: bytes, suffix: str) -> Any:
    try:
        text = data.decode("utf-8")
        if suffix == ".json":
            document = json.loads(text, object_pairs_hook=_unique_pairs,
                                  parse_float=_finite_float,
                                  parse_constant=_reject_constant)
        elif suffix == ".toml":
            document = tomllib.loads(text)
        else:
            raise InputError("unsupported_format")
        _nesting(document)
        return document
    except InputError:
        raise
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise InputError("invalid_document") from None


def _os_error(error: OSError, *, root: bool = False) -> InputError:
    if error.errno == errno.ENOENT:
        return InputError("root_missing" if root else "file_missing")
    if error.errno == errno.ELOOP:
        return InputError("symlink_refused")
    return InputError("read_error")


def _mode_check(mode: int, *, directory: bool = False, attributes: int = 0) -> None:
    # Reparse-point detection also covers Windows junctions on Python 3.11,
    # which predates Path.is_junction(). Conservatively refuse all reparse points.
    if stat.S_ISLNK(mode) or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise InputError("symlink_refused")
    if directory and not stat.S_ISDIR(mode):
        raise InputError("not_directory")
    if not directory and not stat.S_ISREG(mode):
        raise InputError("not_regular_file")


def _read_fd(fd: int, limit: int, limit_code: str) -> bytes:
    info = os.fstat(fd)
    _mode_check(info.st_mode)
    if info.st_size > limit:
        raise InputError(limit_code)
    with os.fdopen(os.dup(fd), "rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise InputError(limit_code)
    return data


def _descriptor_access(root: Path, parts: tuple[str, ...], read: bool,
                       limit: int, limit_code: str) -> bytes | None:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_fd = os.open(root, flags)
    try:
        for part in parts[:-1]:
            info = os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
            _mode_check(info.st_mode, directory=True)
            next_fd = os.open(part, flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = next_fd
        info = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        _mode_check(info.st_mode)
        if not read:
            return None
        file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        file_fd = os.open(parts[-1], file_flags, dir_fd=parent_fd)
        try:
            return _read_fd(file_fd, limit, limit_code)
        finally:
            os.close(file_fd)
    finally:
        os.close(parent_fd)


def _portable_access(root: Path, parts: tuple[str, ...], read: bool,
                     limit: int, limit_code: str) -> bytes | None:
    path = root
    for index, part in enumerate(parts):
        path = path / part
        info = path.lstat()
        _mode_check(info.st_mode, directory=index < len(parts) - 1,
                    attributes=getattr(info, "st_file_attributes", 0))
        if hasattr(path, "is_junction") and path.is_junction():
            raise InputError("symlink_refused")
    if not read:
        return None
    flags = (os.O_RDONLY | getattr(os, "O_BINARY", 0)
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise InputError("file_changed")
        return _read_fd(fd, limit, limit_code)
    finally:
        os.close(fd)


def file_access(root: Path, relative: str, *, read: bool,
                limit: int = MAX_DOCUMENT_BYTES,
                limit_code: str = "file_too_large") -> bytes | None:
    """Access one named file; root is explicit and source traversal is refused."""
    try:
        root_info = root.lstat()
        _mode_check(root_info.st_mode, directory=True,
                    attributes=getattr(root_info, "st_file_attributes", 0))
        if hasattr(root, "is_junction") and root.is_junction():
            raise InputError("symlink_refused")
    except OSError as error:
        raise _os_error(error, root=True) from None
    parts = tuple(relative.split("/"))
    try:
        descriptor_support = (os.open in os.supports_dir_fd
                              and os.stat in os.supports_dir_fd
                              and hasattr(os, "O_NOFOLLOW")
                              and hasattr(os, "O_DIRECTORY"))
        if descriptor_support:
            return _descriptor_access(root, parts, read, limit, limit_code)
        return _portable_access(root, parts, read, limit, limit_code)
    except OSError as error:
        raise _os_error(error) from None


def _load_config(path: Path, label: str) -> Any:
    suffix = path.suffix.lower()
    if suffix not in {".json", ".toml"}:
        raise InputError(f"{label}_unsupported_format")
    try:
        data = file_access(path.parent, path.name, read=True)
        assert data is not None
        return parse_document(data, suffix)
    except InputError as error:
        raise InputError(f"{label}_{error.code}") from None


def _identifier(value: Any) -> bool:
    return type(value) is str and IDENTIFIER.fullmatch(value) is not None


def _source_path(value: Any) -> bool:
    if type(value) is not str or not value or len(value) > 512:
        return False
    if (any(character in value for character in ('\\', ':', '<', '>', '"', '|', '?', '*'))
            or any(ord(character) < 32 for character in value)
            or PureWindowsPath(value).drive):
        return False
    return all(part not in {"", ".", ".."}
               and not part.endswith((".", " "))
               and part.split(".")[0].rstrip(" ").upper() not in WINDOWS_DEVICES
               for part in value.split("/"))


def _sensitive_path(path: str) -> bool:
    parts = [part.casefold() for part in path.split("/")]
    return (any(part in SENSITIVE_DIRS or part == ".env" or part.startswith(".env.")
                for part in parts)
            or Path(parts[-1]).stem in SENSITIVE_STEMS)


def validate_roots(document: Any, base: Path) -> dict[str, Path]:
    if (type(document) is not dict
            or set(document) != {"schema_version", "roots"}
            or type(document["schema_version"]) is not int
            or document["schema_version"] != 1
            or type(document["roots"]) is not dict
            or not document["roots"] or len(document["roots"]) > MAX_CHECKS):
        raise InputError("invalid_roots")
    roots: dict[str, Path] = {}
    for alias, value in document["roots"].items():
        if (not _identifier(alias) or type(value) is not str or not value
                or len(value) > 4096 or "\x00" in value
                or value.startswith(("//", "\\\\"))):
            raise InputError("invalid_roots")
        path = Path(value)
        roots[alias] = path if path.is_absolute() else base / path
    return roots


def validate_contract(document: Any, roots: dict[str, Path]) -> list[Check]:
    if (type(document) is not dict
            or set(document) != {"schema_version", "checks"}
            or type(document["schema_version"]) is not int
            or document["schema_version"] != 1
            or type(document["checks"]) is not list
            or not 1 <= len(document["checks"]) <= MAX_CHECKS):
        raise InputError("invalid_contract")
    checks = []
    identifiers: set[str] = set()
    for item in document["checks"]:
        if type(item) is not dict:
            raise InputError("invalid_contract")
        kind = item.get("kind")
        if type(kind) is not str or kind not in KINDS:
            raise InputError("invalid_contract")
        fields = {"id", "repo", "kind", "file"}
        if kind != "file_exists":
            fields.add("pointer")
        if kind == "equals":
            fields.add("expected")
        if (set(item) != fields or not _identifier(item["id"])
                or not _identifier(item["repo"]) or not _source_path(item["file"])
                or item["id"] in identifiers):
            raise InputError("invalid_contract")
        if item["repo"] not in roots:
            raise InputError("unknown_repo")
        if kind != "file_exists":
            if Path(item["file"]).suffix.lower() not in {".json", ".toml"}:
                raise InputError("unsupported_source_format")
            if _sensitive_path(item["file"]):
                raise InputError("sensitive_path_refused")
            tokens = pointer_tokens(item["pointer"])
        else:
            tokens = ()
        if kind == "equals" and not json_value(item["expected"]):
            raise InputError("invalid_expected_value")
        identifiers.add(item["id"])
        checks.append(Check(item["id"], item["repo"], kind, item["file"],
                            tokens, item.get("expected")))
    return sorted(checks, key=lambda check: (check.repo, check.id))


class Documents:
    def __init__(self, roots: dict[str, Path]):
        self.roots = roots
        self.cache: dict[tuple[str, str], Any] = {}
        self.errors: dict[tuple[str, str], str] = {}
        self.remaining = MAX_SOURCE_BYTES

    def load(self, check: Check) -> Any:
        key = (check.repo, check.file)
        if key in self.errors:
            raise InputError(self.errors[key])
        if key not in self.cache:
            try:
                if self.remaining <= 0:
                    raise InputError("read_budget_exceeded")
                limit = min(MAX_DOCUMENT_BYTES, self.remaining)
                code = "read_budget_exceeded" if limit < MAX_DOCUMENT_BYTES else "file_too_large"
                data = file_access(self.roots[check.repo], check.file, read=True,
                                   limit=limit, limit_code=code)
                assert data is not None
                self.remaining -= len(data)
                self.cache[key] = parse_document(data, Path(check.file).suffix.lower())
            except InputError as error:
                self.errors[key] = error.code
                raise
        return self.cache[key]


def evaluate(check: Check, documents: Documents) -> tuple[str, str]:
    try:
        if check.kind == "file_exists":
            file_access(documents.roots[check.repo], check.file, read=False)
            return "pass", "file_present"
        document = documents.load(check)
        found, value = resolve_pointer(document, check.tokens)
        if not found:
            return "fail", "value_missing"
        if check.kind == "value_exists":
            return "pass", "value_present"
        if check.kind == "nonempty_string":
            if type(value) is not str:
                return "fail", "type_mismatch"
            return ("pass", "nonempty_string") if value.strip() else ("fail", "empty_string")
        if not json_value(value):
            return "error", "unsupported_value"
        if strict_equal(value, check.expected):
            return "pass", "value_matches"
        return "fail", "value_mismatch"
    except InputError as error:
        status = "fail" if error.code in {"file_missing"} else "error"
        return status, error.code


def report(results: list[dict[str, str]], errors: list[str]) -> tuple[dict[str, Any], int]:
    counts = {status: sum(result["status"] == status for result in results)
              for status in ("pass", "fail", "error")}
    counts["error"] += len(errors)
    output = {"schema_version": 1, "results": results,
              "errors": [{"reason": reason} for reason in errors], "summary": counts}
    code = 2 if counts["error"] else 1 if counts["fail"] else 0
    return output, code


def run_checks(contracts_path: Path, roots_path: Path) -> tuple[dict[str, Any], int]:
    """Return a value-free/path-free report; make no writes or external calls."""
    try:
        contracts_path = contracts_path.absolute()
        roots_path = roots_path.absolute()
        contract = _load_config(contracts_path, "contracts")
        roots_document = _load_config(roots_path, "roots")
        roots = validate_roots(roots_document, roots_path.parent)
        checks = validate_contract(contract, roots)
    except InputError as error:
        return report([], [error.code])
    documents = Documents(roots)
    results = []
    for check in checks:
        status, reason = evaluate(check, documents)
        results.append({"repo": check.repo, "rule": check.id,
                        "status": status, "reason": reason})
    return report(results, [])
