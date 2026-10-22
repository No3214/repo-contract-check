# Reason codes

All reasons are fixed strings; no values or exception messages are interpolated.

| Category | Reasons |
| --- | --- |
| Passing expectations | `file_present`, `value_present`, `value_matches`, `nonempty_string` |
| Failed expectations | `file_missing`, `value_missing`, `value_mismatch`, `empty_string`, `type_mismatch` |
| Source errors | `root_missing`, `not_directory`, `not_regular_file`, `symlink_refused`, `read_error`, `file_changed`, `file_too_large`, `read_budget_exceeded`, `invalid_document`, `duplicate_key`, `nonfinite_number`, `nesting_limit`, `unsupported_value` |
| Configuration errors | `invalid_contract`, `invalid_roots`, `unknown_repo`, `invalid_pointer`, `unsupported_source_format`, `sensitive_path_refused`, `invalid_expected_value` |
| CLI/operational errors | `argument_error`, `interrupted`, `internal_error` |

Reading/parsing a configuration file uses the same underlying input reasons
prefixed with `contracts_` or `roots_`, such as `contracts_file_missing`,
`roots_invalid_document`, and `contracts_duplicate_key`. Unsupported configuration
extensions use `contracts_unsupported_format` or `roots_unsupported_format`.

`value_mismatch` includes unequal types and unequal values for `equals`.
`type_mismatch` means `nonempty_string` found something other than a string.
`unsupported_value` means an `equals` target includes a value outside finite JSON
types, such as a native TOML date/time. A pointer that cannot traverse the selected
document produces `value_missing`; malformed pointer syntax is `invalid_pointer`.

Configuration errors appear in the top-level `errors` list and prevent source
checks. Source errors attach to their individual rule and do not stop other rules.
Any error leads to exit 2; a failure without errors leads to exit 1.

For `internal_error`, report a synthetic reproduction without private inputs.
The CLI deliberately does not emit an unsanitized traceback.
