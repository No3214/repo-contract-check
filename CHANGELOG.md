# Changelog

All notable changes to this project are documented in this file.

## [0.1.1] - 2026-11-24

### Packaging & Release
- Add `project.urls`, `CHANGELOG.md`, `twine check --strict` metadata verification in CI, and a commit-SHA-pinned OIDC Trusted Publishing `release.yml` workflow.

## [0.1.0] - 2026-11-20

### Added
- Initial offline JSON and TOML repository contract checker (`repo-contract-check`) with four explicit predicates (`file_exists`, `value_exists`, `equals`, `nonempty_string`), exact decimal equality, path confinement, and zero-leak alias-and-rule reports.
