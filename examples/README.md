# Synthetic examples

These are data fixtures, not runnable applications. The Node verification string,
Python test-path declaration, CI filename, and evidence location deliberately
illustrate the limits of static checks. No project commands are executed.

`contracts.json` and `contracts.toml` express the same six checks.
`contracts.failing.json` requires a verification entry that does not exist, so
its expected exit code is 1. `roots.example.json` resolves paths relative to its
own directory. All names and values were created for this example.

| Situation | Expected result |
| --- | --- |
| `contracts.json` with `roots.example.json` | Six passing checks, exit `0`. |
| `contracts.failing.json` with the same roots | One failed expectation, exit `1`. |
| A configured root directory does not exist | An input error, exit `2`. |

Run commands from the repository directory as shown in the main README. The
report must be written successfully for exit `0` or `1`; output failures return
`2`. A successful static check does not mean that a referenced test or workflow ran.
