# Synthetic examples

These are data fixtures, not runnable applications. The Node verification string,
Python test-path declaration, CI filename, and evidence location deliberately
illustrate the limits of static checks. No project commands are executed.

`contracts.json` and `contracts.toml` express the same six checks.
`contracts.failing.json` requires a verification entry that does not exist, so
its expected exit code is 1. `roots.example.json` resolves paths relative to its
own directory. All names and values were created for this example.
