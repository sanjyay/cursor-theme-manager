# Cursor Theme Manager — Test Instructions

These instructions apply to everything under `tests/`.

The repository-level `../AGENTS.md` instructions also apply.

Tests are part of the project's security boundary.

A test suite that passes while modifying the developer's real configuration is
a failure.

---

## Test Isolation

Tests must not modify real-user configuration.

Use isolated temporary locations and controlled environment variables for
tests involving:

- `$HOME`
- `$XDG_CONFIG_HOME`
- `$XDG_DATA_HOME`
- GTK configuration
- cursor configuration
- icon configuration
- UWSM configuration
- Cursor Theme Manager state
- imported themes
- cleanup
- restoration

Tests must not depend on the developer's existing desktop configuration.

Temporary resources should be removed after tests complete.

Zero real-user directory pollution is required.

---

## Security Regression Tests

Every security bug fix should include a regression test where practical.

The test should:

1. reproduce the unsafe condition
2. fail against the vulnerable behavior
3. pass with the security fix
4. verify that unrelated user data remains unchanged
5. verify that legitimate normal behavior still works

Do not remove or weaken existing security regression tests merely to make the
suite pass.

When a reviewer identifies a vulnerability class, test the class rather than
only the exact pathname or line numbers from the report.

---

## Adversarial Filesystem Cases

For security-sensitive filesystem changes, consider tests for:

- final-component symlinks
- intermediate-directory symlinks
- FIFOs
- sockets where relevant
- special/device files where practical
- oversized files
- malformed configuration
- unexpected directories
- broken symlinks
- foreign-owned files where practical
- missing files
- failed writes
- interrupted operations where practical
- repeated apply
- repeated cleanup
- baseline restoration
- legitimate configuration updates

Tests must verify both:

1. unsafe input is rejected safely
2. legitimate input continues to work

---

## Cleanup and Restoration Tests

Cleanup tests must verify that:

- unrelated user configuration is preserved
- only expected CTM-owned or positively identified files are removed
- suspicious symlinks are not followed
- restoration returns configuration to the expected baseline
- repeated cleanup is safe where intended
- missing CTM-owned files are handled correctly
- unsafe replacement targets are rejected

State-related tests should verify that:

- the original baseline is preserved
- an already-modified state is not silently accepted as a fresh baseline
- generation mismatches are handled safely
- first mutation does not occur before required state is persisted

---

## Test Determinism

Avoid tests that depend on:

- arbitrary long sleeps
- existing user configuration
- external network availability
- interactive input
- unrelated machine state
- pre-existing filesystem contents outside the test environment

Prefer explicit synchronization or bounded polling instead of fixed delays
where practical.

Do not weaken assertions merely to eliminate flakiness without understanding
the cause.

---

## Full Suite

Targeted tests may be run while developing a change.

Before declaring the work complete, run from the repository root:

```bash
./tests/run.sh
```

The complete suite must pass.

Also run:

```bash
git diff --check
git status --short
```

Do not report completion based only on a targeted test.

---

## Test Changes

When modifying tests:

- preserve meaningful existing coverage
- do not alter expectations simply to accommodate incorrect implementation behavior
- keep tests focused on observable behavior and security invariants
- avoid coupling tests unnecessarily to internal implementation details
- make failure messages useful for diagnosis

If an existing test appears wrong, establish why before changing it.

Security tests should express the invariant being protected, not merely mirror
the current implementation.
