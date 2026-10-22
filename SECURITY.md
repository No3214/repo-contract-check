# Security and privacy boundaries

## Intended use

Run this local utility against explicitly selected project directories and
configuration files you control. It is a static declaration checker, not a
security scanner, permission boundary, test runner, or evidence attestation.

The runtime uses the Python standard library. It does not start subprocesses,
contact services, inspect Git metadata, load code from scanned projects, extract
archives, expand shell expressions, or write to target repositories.

## Data exposure

Reports contain user-selected aliases and rule IDs, statuses, reason codes, and
counts. They do not contain file paths, pointers, configuration values, source
snippets, raw parser exceptions, or raw OS errors. Use shareable aliases and IDs.
Portable rules can still contain private expectations; review them before
publishing. Keep local roots files out of version control.

Only explicitly selected JSON/TOML files are opened. File-existence checks use
metadata without reading contents. Known credential directory names (`.git`,
`.ssh`, `.aws`, `.gnupg`, `.azure`, `.kube`), `.env`/`.env.*` path components, and
manifest stems `credentials`, `secrets`, `private-key`, and `private_key` are
refused for content checks. This is a limited guard, not exhaustive secret
detection. Sensitive data in a selected project manifest is parsed locally but
is not rendered. The caller's operating system, filesystem, terminal history,
and Python environment remain outside this tool's guarantees. Network-mounted
local directories may involve the operating system's own filesystem networking;
the tool does not establish network connections itself.

## Filesystem handling

Source selectors cannot be absolute, traverse `..`, use Windows alternate
streams/device names, or contain ambiguous portable path spellings. Root
directories cannot themselves be symlinks; symlinks below them and nonregular
files are refused. Windows reparse points, including junctions, are conservatively
refused. Config-file symlinks are refused as well. On platforms with
directory-descriptor support, reads use no-follow opens relative to parent
descriptors. The fallback checks each path component and verifies the opened
file identity. Parsed files have a 1 MiB bound, source reads an 8 MiB budget, and data
nesting a 64-level bound.

These checks are not a security sandbox. In particular, a malicious concurrent
process can race filesystem operations, and Windows' fallback is not an atomic
traversal mechanism. The caller must control the roots and their containing
directories. An invocation may observe different files at different instants.
The tool does not authenticate or cryptographically attest its report.

## Reporting a problem

Report ordinary bugs with a minimal synthetic reproduction and the fixed reason
codes. Never attach private roots files, credentials, source archives, or
unredacted private configuration.

If the repository's Security tab offers private vulnerability reporting, use it
for a suspected data exposure or boundary bypass. Otherwise open a public issue
requesting a private contact route without including the sensitive details.
There is no promised response-time or support SLA. This is an initial 0.1 release;
fixes target the latest released version.
