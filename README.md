# repo-contract-check

**Check the repository expectations you choose, without running project code.**

One repository declares `scripts.verify`; another declares `scripts.test`.
Check explicit JSON/TOML expectations across local repositories and get a
deterministic JSON or Markdown report. Keep portable rules separate from
private directory mappings.

Python 3.11+ · Standard-library runtime · JSON and TOML · MIT

| If you need to… | This tool can… |
| --- | --- |
| Confirm a chosen script declaration exists | Check a nonempty string at a JSON pointer |
| Check an explicit Python version declaration | Compare a TOML value literally |
| Share check outcomes without local paths or manifest values | Produce alias-and-rule reports |

[Try the included examples](#quickstart) · [Declare your own contracts](#declare-your-own-contracts) · [Compare alternatives](#existing-alternatives)

Each repository gets the rules you choose. There is no inferred common runtime
or readiness score.

**A passing check verifies a declaration or file's presence. It does not mean
tests ran, CI works, a runtime is compatible, or evidence is current.**

## Quickstart

Clone the repository, then install into your chosen Python 3.11+ environment.
For macOS or Linux:

```sh
git clone https://github.com/No3214/repo-contract-check.git
cd repo-contract-check
python3 -m venv .venv
. .venv/bin/activate
```

On Windows PowerShell, clone and enter the same repository, then use
`py -3 -m venv .venv` and `.\\.venv\\Scripts\\Activate.ps1` if your execution policy permits.
Alternatively, call `.\\.venv\\Scripts\\python.exe -m pip` and
`.\\.venv\\Scripts\\repo-contract-check.exe` directly instead of activation.

With the environment selected:

```sh
python -m pip install .
repo-contract-check check examples/contracts.json --roots examples/roots.example.json
```

The synthetic examples produce six passing checks. They are data fixtures, not
runnable applications. Their runtime expectations are examples, not recommendations.

For machine-readable output:

```sh
repo-contract-check check examples/contracts.toml --roots examples/roots.example.json --format json
```

Both contract formats express the same checks. The module entry point also works:

```sh
python -m repo_contract_check check examples/contracts.json --roots examples/roots.example.json --format markdown
```

To see a real failure, run the following command. Its expected exit code is **1**
because the declared verification entry is missing:

```sh
repo-contract-check check examples/contracts.failing.json --roots examples/roots.example.json --format json
```

Run the original contract again to return to six passing checks. No example file
is modified by either command.

## Declare your own contracts

Create a portable `contracts.json`:

```json
{
  "schema_version": 1,
  "checks": [
    {
      "id": "verification-entry",
      "repo": "web-example",
      "kind": "nonempty_string",
      "file": "package.json",
      "pointer": "/scripts/verify"
    },
    {
      "id": "declared-python",
      "repo": "worker-example",
      "kind": "equals",
      "file": "pyproject.toml",
      "pointer": "/project/requires-python",
      "expected": ">=3.11"
    }
  ]
}
```

Create a **private** `roots.local.json` next to it:

```json
{
  "schema_version": 1,
  "roots": {
    "web-example": "../web-project",
    "worker-example": "../worker-project"
  }
}
```

Then run:

```sh
repo-contract-check check contracts.json --roots roots.local.json --format json
```

Root paths resolve relative to the roots file, independently of your working
directory. Absolute local root paths are also accepted; `~` and environment
variables are not expanded. Keep this file private. This project's `.gitignore`
excludes `*.local.json` and `*.local.toml`; other repositories need their own
ignore rule. Portable contracts may also be sensitive if their literal
expectations describe private details: review them before sharing.

## Four predicates

| `kind` | Required additional fields | Passing condition |
| --- | --- | --- |
| `file_exists` | None | A named regular file exists; contents are not opened. |
| `value_exists` | `pointer` | The pointer resolves, including a JSON null value. |
| `equals` | `pointer`, `expected` | Exact structural, type-strict equality. |
| `nonempty_string` | `pointer` | A string contains a non-whitespace character. |

Every check also requires `id`, `repo`, `kind`, and `file`. IDs are unique across
the contract. IDs and aliases are 1–64 ASCII letters, digits, periods, underscores,
or hyphens, beginning with a letter or digit. Unknown fields, operators, schema
versions, duplicate JSON keys, missing aliases, and empty contracts are errors.

Manifest checks read only explicitly named `.json` or `.toml` files. File paths
use relative forward-slash segments; absolute paths, `..`, symlinks, special files,
Windows device names, alternate streams, and ambiguous trailing dots/spaces are
refused. No glob expansion, repository discovery, archive extraction, or script
execution occurs. `file_exists` may name any regular-file extension.

### Pointer and equality semantics

Pointers use [RFC 6901](https://www.rfc-editor.org/rfc/rfc6901.txt) string syntax:
`/scripts/verify`, `/items/0`, `~1` for a slash in a key, and `~0` for a tilde.
The empty string selects the document root. URI fragments such as `#/field`
are unsupported. The same syntax traverses parsed TOML mappings and arrays.

Object key order does not matter; array order does. Booleans, integers, floats,
and strings are distinct: `true`, `1`, `1.0`, and `"1"` do not compare equal.
Missing differs from null. `equals` compares declarations literally; it does not
interpret semver ranges or validate installed runtimes. TOML dates/times and
non-finite floats produce `unsupported_value` for `equals`; `value_exists` may
locate them. JSON NaN, Infinity, and overflowing floats are rejected.

## Reports and exit codes

JSON results contain only `repo`, `rule`, `status`, and a fixed `reason` code.
The top level contains `schema_version`, `results`, `errors`, and `summary`.
Results sort by alias and rule ID. There are no timestamps or random identifiers.

```json
{
  "errors": [],
  "results": [
    {
      "reason": "value_missing",
      "repo": "web-example",
      "rule": "missing-verification-entry",
      "status": "fail"
    }
  ],
  "schema_version": 1,
  "summary": {"error": 0, "fail": 1, "pass": 0}
}
```

| Exit | Meaning |
| --- | --- |
| `0` | Every declared check passed. |
| `1` | At least one expectation failed. |
| `2` | Configuration, input, or operational error. |

Errors take precedence over failed expectations. A missing declared source file
is a failed expectation; a missing root directory is an input error. Other
repositories continue after an individual input error. Configuration errors stop
the run before source manifests are opened. See [reason codes](docs/reason-codes.md).

## Privacy and practical limits

Reports omit local paths, filenames, pointers, source excerpts, and actual or
expected values, including in parser and OS errors. **Aliases and rule IDs are
visible**, so choose names suitable for sharing. The tool has no telemetry,
network client, subprocess runner, model integration, or Git inspection.

Only named files are read. Content checks reject common credential locations
such as `.env.*`, `.aws/`, and `secrets.json`. This is not a complete secret
detector: an explicitly selected manifest can contain sensitive data. No secrets
are automatically discovered or scanned.

Files opened for parsing are limited to 1 MiB each; source reads share an 8 MiB budget. Contracts have
at most 256 checks, with 64 levels of data nesting. Documents are cached only
within one invocation. Target-repository access is read-only. Selected roots and
configuration files must be controlled by the caller. This utility is not a
sandbox against concurrent hostile filesystem changes and does not capture an
atomic snapshot across repositories. See [SECURITY.md](SECURITY.md).

## Existing alternatives

[Conftest](https://www.conftest.dev/) already provides richer JSON/TOML policies
using Rego, including cross-file comparisons. Use it when four predicates are
insufficient. [syncpack](https://github.com/JamieMason/syncpack) specializes in
JavaScript dependency-version policy. This project is a small convenience tool,
with no claim of novel policy checking, validated market demand, or measured AI
productivity improvement. [Research and design sources](docs/research.md) explain
the choice and list other useful projects.

## Development

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python -m pip install build
python -m build
```

CI is configured for Python 3.11–3.14 on Linux and Python 3.12 on Windows and macOS,
plus an isolated wheel smoke test. This configuration is not a claim that an
unrun CI matrix passed. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Türkçe hızlı başlangıç

Python 3.11 veya üzeri gerekir. Bu klasörde `python -m pip install .` komutuyla kurun.

```sh
repo-contract-check check examples/contracts.json --roots examples/roots.example.json --format json
```

Araç, her depo için açıkça tanımladığınız dosya ve JSON/TOML alanlarını kontrol
eder. Depo komutlarını çalıştırmaz; testlerin geçtiğini veya CI'ın çalıştığını
iddia etmez. Gerçek klasör yollarını ayrı bir `roots.local.json` dosyasında tutun.
Raporda takma adlar, kural kimlikleri ve sonuç kodları görünür; yollar ve değerler
yer almaz. Çıkış kodları: `0` tüm kontroller geçti, `1` beklenti karşılanmadı,
`2` yapılandırma veya okuma hatası. Örneklerin tamamı sentetiktir.

## License

[MIT](LICENSE), copyright 2026 Yunuscan Oruk.
