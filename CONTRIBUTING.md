# Contributing

Keep this utility small: explicit predicates, deterministic diagnostics, no
runtime dependencies, and no network or project-command execution. All examples
and tests must be synthetic. Do not contribute private source, actual local
bindings, credentials, or reports containing identifying values.

## Setup and verification

Use Python 3.11 or newer in a virtual environment of your choice:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

Tests cover JSON/TOML behavior, RFC 6901 pointers, strict equality, malformed
configuration, privacy, source boundaries, repeatability, and CLI examples.
Tests may create temporary fixture directories and invoke the installed module;
the checker itself never executes project commands. FIFO tests skip on Windows;
symlink tests skip only when the host cannot create their fixtures.

For packaging:

```sh
python -m pip install build
python -m build
```

The build backend is setuptools; it is a build-time dependency. The installed
checker has no third-party runtime dependencies. CI installs the wheel into a
fresh environment and runs the documented synthetic example without importing
the source checkout. GitHub Actions references are pinned to verified official
commit IDs; [research.md](docs/research.md) records their sources.

## Changes

Explain the observed problem and resulting behavior. Include an independent
regression test for changed semantics or boundaries. Preserve report field and
reason-code contracts, or document a deliberate version change. Do not expand
the tool into a general policy language; use Conftest for that need.

Before proposing a change, run the relevant suite and documented example. If an
environment was not available, say so instead of claiming its checks passed.
See [SECURITY.md](SECURITY.md) for handling suspected vulnerabilities.
