# Design and implementation plan

## Problem and scope

Separately maintained repositories can have different runtime declarations,
verification entry points, CI files, and evidence locations. This tool checks
only the per-repository expectations explicitly listed in a contract. It does
not infer common runtimes, run commands, discover repositories, inspect Git,
score readiness, or attest that tests have passed.

Portable contracts contain aliases and predicates. A separate, private roots
file maps aliases to local directories. Source manifests are JSON or TOML;
Python 3.11's standard library provides both parsers. All examples are synthetic.

## Interface

`repo-contract-check check CONTRACTS --roots ROOTS --format json|markdown`

Both configuration inputs accept JSON or TOML. The contract schema is
`{schema_version: 1, checks: [...]}`; the roots schema is
`{schema_version: 1, roots: {alias: path}}`. Paths in the roots file resolve from
that file's parent directory. Source paths use relative forward-slash segments.

Checks have `id`, `repo`, `kind`, and `file`; manifest checks also require
`pointer`; `equals` additionally requires `expected`. Kinds are `file_exists`,
`value_exists`, `equals`, and `nonempty_string`. Unknown keys are errors.

Results expose only validated aliases and rule IDs, statuses, fixed reason codes,
and counts. No filenames, pointers, local paths, document excerpts, or actual or
expected values are rendered. User-selected aliases and IDs are deliberately
visible and must themselves be suitable for sharing. Parser and OS exceptions
are replaced with fixed reason codes.

## Semantics

Pointers follow RFC 6901 string syntax; URI-fragment syntax is unsupported.
Equality is structural and type-strict: booleans, integers, floats, and strings
are distinct; object key order is irrelevant and array order matters. A missing
value differs from JSON null. TOML dates/times and non-finite floats cannot be
used by `equals`; existence checks may locate them. Nonempty strings must contain
a non-whitespace character. File presence establishes no claim about contents.

Input files have a 1 MiB limit. Source reads share an 8 MiB budget. A contract has
at most 256 checks. Nesting is limited to 64 levels. JSON duplicate keys and
non-finite numbers are rejected. Input documents are read once per invocation.

## File boundary

The tool reads only named regular JSON/TOML files; `file_exists` uses metadata.
It refuses traversal, absolute source paths, symlinks below a root, and special
files. Explicit root directories cannot themselves be symlinks. Known credential
locations are refused for content checks, but filename checks cannot identify
every secret: selected project manifests may contain sensitive data.

On systems supporting directory descriptors, source traversal uses no-follow
opens relative to directory descriptors. Other systems perform component checks
and verify the opened file. This is a local maintenance utility, not a sandbox
against a hostile process concurrently rewriting the filesystem. Roots and
configuration files must be controlled by the caller. No claim of an atomic
cross-repository snapshot is made.

Exit 0 means all declared checks passed; 1 means an expectation failed; 2 means
configuration or input errors. Error takes precedence over failure. Checks in
other repositories continue after an individual input error.

## Implementation sequence

1. Define strict configuration, pointer, equality, and output semantics.
2. Implement bounded file access and the four predicates without runtime
   dependencies, networking, subprocesses, or source modifications.
3. Add synthetic Node/Python examples and adversarial unit/integration tests.
4. Exercise documented CLI examples, build a wheel, and smoke-test that wheel.
5. Add portable CI and publish limitations and existing alternatives.

## Deliberate exclusions

No shell execution, Git discovery, fix mode, archive extraction, schema plugins,
regular-expression policy language, semver interpretation, timestamps, telemetry,
remote policy loading, generated readiness scores, or unmeasured benefit claims.
For complex configuration policy, prefer Conftest. For JavaScript dependency
version policy, prefer syncpack. See [research.md](research.md).
