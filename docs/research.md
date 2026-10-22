# Research and existing alternatives

Reviewed on 2026-10-22. These are primary repositories, first-hand engineering
posts, official documentation, and a primary research paper. The comparisons
describe documented capabilities; they are not security audits or benchmarks.
No implementation, tests, or private project data were copied into this project.

## Design motivation

[Simon Willison's "First run the tests"](https://simonwillison.net/guides/agentic-engineering-patterns/first-run-the-tests/)
describes starting agent sessions with the actual test suite. It motivates having
an explicit verification entry point. His [manual testing guidance](https://simonwillison.net/guides/agentic-engineering-patterns/agentic-manual-testing/)
also explains why passing unit tests alone does not establish that a feature
works. A static manifest check makes an even narrower claim.

[Mitchell Hashimoto's "My AI Adoption Journey"](https://mitchellh.com/writing/my-ai-adoption-journey)
(2026-02-05) describes converting observed agent mistakes into improved
instructions and concrete feedback tools. [OpenAI's engineering account by Ryan
Lopopolo](https://openai.com/index/harness-engineering/) (2026-02-11) describes
mechanical enforcement of repository invariants and structured documentation.
These support small explicit checks; neither establishes demand for this tool.

[Anthropic's long-running-agent report](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents)
(2025-11-26) describes premature completion and session handoff problems.
File-presence checks can locate declared artifacts, but cannot verify whether
their assertions are accurate or current.

The primary paper [Evaluating AGENTS.md](https://arxiv.org/html/2602.11988v3)
reports that context files did not generally improve task success in its studied
settings. That finding is not a universal rejection of instructions; it cautions
against assuming that more generated context yields better outcomes. This project
makes no measured productivity or model-performance claim.

## Candidate comparison

| Need | Existing projects | Decision for this project |
| --- | --- | --- |
| General structured configuration policies | [Conftest](https://www.conftest.dev/) | Conftest already supports JSON/TOML and [combined cross-file policies](https://www.conftest.dev/options/#combine) in Rego. Prefer it for richer logic. This project's limited convenience is four predicates, separate local bindings, and reports that omit paths and values. |
| JavaScript dependency consistency | [syncpack](https://github.com/JamieMason/syncpack) | Prefer syncpack for version groups, semver policies, and dependency updates. Literal equality here is not semver analysis. |
| Test-evidence freshness | [stalegreen](https://github.com/pavangupta352/stalegreen) | Existing working-tree fingerprints and receipt gates make a new receipt engine unnecessary for this scope. |
| Agent change receipts | [agent-receipt](https://github.com/pramodreddyboddu/agent-receipt) | Existing Git receipts and policy rules address a different workflow. |
| Reproducible demonstrations | [Showboat](https://github.com/simonw/showboat) | Executable demo documents are useful for demonstrating work. This checker does not replay commands. |
| Instruction/harness linting | [AgentLint](https://github.com/0xmariowu/AgentLint), [agent-readiness](https://github.com/harrydaihaolin/agent-readiness) | Existing projects cover instruction/configuration checks and readiness workflows. This checker assigns no readiness score. |
| Multi-repository Git operations | [gita](https://github.com/nosarthur/gita), [all-repos](https://github.com/asottile/all-repos) | Use established Git tools for status, search, and bulk operations. This checker does not inspect Git. |

The observed licenses are MIT for syncpack, stalegreen, agent-receipt, AgentLint,
gita, all-repos, and agent-readiness's code (its branding has separate terms).
Showboat and [Conftest](https://github.com/open-policy-agent/conftest/blob/master/LICENSE)
use Apache-2.0. They are alternatives and references, not bundled dependencies.

[obra/superpowers](https://github.com/obra/superpowers) (MIT) offers composable
engineering workflows, including evidence before completion claims.
[Andrej Karpathy's autoresearch](https://github.com/karpathy/autoresearch) (MIT)
is a useful example of constrained editable scope and a measurable experiment.
Neither is a runtime dependency, and this project does not adopt another tool's
permission model.

## Technical references

- [RFC 6901: JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901.txt): pointer syntax and evaluation; implemented independently.
- [Python 3.11 tomllib](https://docs.python.org/3.11/library/tomllib.html): standard-library TOML parsing.
- [Conftest supported formats](https://www.conftest.dev/): existing JSON/TOML configuration-policy support.

## CI action pins

The official release pages and linked commits were checked on 2026-10-22:

| Action | Release | Full commit |
| --- | --- | --- |
| [actions/checkout](https://github.com/actions/checkout/releases/tag/v7.0.1) | v7.0.1 | [3d3c42e5aac5ba805825da76410c181273ba90b1](https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1) |
| [actions/setup-python](https://github.com/actions/setup-python/releases/tag/v7.1.0) | v7.1.0 | [6d4fd22b20465ccc0f7354476588e8df7c9ca0e0](https://github.com/actions/setup-python/commit/6d4fd22b20465ccc0f7354476588e8df7c9ca0e0) |

The workflow grants only `contents: read`, disables persisted checkout credentials,
and neither publishes packages nor uploads reports. A configured workflow is not
evidence that its platform matrix has already run successfully.

## Claims deliberately left unvalidated

External customer demand, originality of the general idea, comparative performance,
and productivity gains have not been established. The goal is a small, documented
and testable utility for people who want explicit local repository expectations.
