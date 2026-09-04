# Cursor Theme Manager — Agent Instructions

These instructions apply to the entire repository.

Cursor Theme Manager is distributed through the Omarchy plugin marketplace.
Security, backwards compatibility, clean uninstall behavior, preservation of
user-owned data, and reproducible behavior are mandatory requirements.

## Core Principle

Cursor Theme Manager modifies configuration belonging to the user.

> Preserving unrelated user data is more important than forcing an operation
> to succeed.

If the project cannot safely determine whether a file, directory, state entry,
or configuration belongs to the expected target, fail safely and report the
problem instead of risking modification of unrelated user data.

Do not weaken an existing security invariant to make a feature, test, cleanup,
or migration succeed.

---

## Development Rules

Before modifying code:

1. Read the relevant implementation.
2. Read the relevant tests.
3. Inspect existing helpers and abstractions.
4. Understand the current behavior and security assumptions.
5. Make the smallest change that completely addresses the task.

General rules:

- Prefer focused changes over unrelated refactors.
- Preserve backwards compatibility unless explicitly instructed otherwise.
- Reuse existing helpers before introducing new implementations.
- Keep security-sensitive logic centralized.
- Avoid unnecessary dependencies.
- Do not silently change behavior unrelated to the task.
- Do not hide known failures or limitations.
- Do not claim a problem is fixed unless it has actually been verified.
- Do not remove or weaken security checks merely because they make an operation fail.
- Do not replace a hardened operation with an unsafe fallback.

When fixing a security issue, address the underlying vulnerability class rather
than only the exact lines mentioned by a reviewer.

---

## Security Model

Treat filesystem content outside trusted packaged plugin files as potentially
untrusted.

This includes content below or derived from:

- `$HOME`
- `$XDG_CONFIG_HOME`
- `$XDG_DATA_HOME`
- `$XCURSOR_PATH`
- GTK configuration
- cursor and icon directories
- imported cursor themes
- runtime state
- restoration state
- temporary directories
- environment-provided paths
- user-selected paths

Never assume that a path still refers to the same object simply because it was
validated earlier.

Never assume that a path refers to a regular file merely because it exists.

Security-sensitive operations must fail closed when ownership, file type, path
identity, state integrity, or restoration safety cannot be established.

Detailed filesystem-security requirements for implementation under `scripts/`
are defined in:

```text
scripts/AGENTS.md
```

---

## State and Restoration

The project must preserve the user's original configuration.

Before modifying user configuration:

- establish the required restoration baseline
- persist the baseline safely
- ensure restoration state belongs to the expected generation
- do not replace a known-good baseline with already-modified state
- do not silently generate a new baseline from uncertain state
- fail safely when state integrity cannot be established

Do not modify lifecycle or state semantics without reviewing relevant:

- startup lifecycle tests
- persistent lifecycle tests
- cleanup tests
- first-mutation barrier tests
- restoration tests

The first mutation of user configuration must not occur before the required
restoration state has been safely established.

---

## Cleanup and Uninstall

Cleanup is security-sensitive.

Cleanup must:

- preserve unrelated user configuration
- remove only files CTM owns or can positively identify
- restore saved baselines safely
- reject suspicious filesystem objects
- tolerate already-absent CTM-owned files where appropriate
- be idempotent where practical

Never broaden cleanup rules merely to make uninstall appear successful.

Never delete a file only because its pathname happens to match a path normally
used by CTM.

---

## Imported and Untrusted Data

Treat imported cursor themes, filenames, metadata, archives, and
user-selected filesystem content as untrusted.

Validate before use.

At minimum:

- validate names before using them as path components
- prevent `..` traversal
- reject unexpected absolute paths
- reject or explicitly handle symlinks
- reject unexpected special files
- prevent archive extraction outside the intended destination
- bound input sizes
- validate expected formats
- do not treat untrusted text as executable code
- do not render untrusted metadata as rich markup by default
- do not allow imported content to trigger unintended remote-resource loading

Reuse existing validators such as `valid_name` and supported-size validation.

Do not weaken validation rules without a clear technical justification.

---

## QML and UI Safety

Treat strings originating from imported themes, configuration files,
filesystem metadata, subprocesses, or user-selected content as untrusted.

For QML:

- render untrusted strings as plain text by default
- do not enable rich-text interpretation for untrusted values
- do not allow untrusted markup to trigger remote-resource loading
- keep filesystem-sensitive operations outside presentation code where practical
- preserve existing accessibility behavior
- avoid unrelated UI changes

UI convenience must not override filesystem or state safety.

---

## Dependencies

Do not add a dependency when the standard library or existing project code can
reasonably solve the problem.

A new dependency must have:

- a concrete technical justification
- a clear maintenance benefit
- acceptable security implications
- compatibility with the supported environment
- no unnecessary privilege or network requirement

---

## Testing

After modifying code, run:

```bash
./tests/run.sh
```

The complete suite must pass before considering a task complete.

Targeted tests may be used during development, but they do not replace the
full suite.

Detailed testing and isolation requirements are defined in:

```text
tests/AGENTS.md
```

A passing test suite does not override a known unresolved security issue.

---

## Security Fixes

Every security fix should include a regression test where practical.

When a reviewer identifies a vulnerability:

1. reproduce the issue
2. understand the underlying vulnerability class
3. fix the root cause
4. search for equivalent code paths
5. add or update adversarial regression coverage
6. verify legitimate behavior still works
7. run the full suite

Do not fix only the exact line numbers mentioned by the reviewer.

A security fix is incomplete if the vulnerable primitive remains reachable
through another relevant code path.

---

## Git and Working Tree Safety

Before making destructive or wide-ranging changes:

```bash
git status
```

Preserve pre-existing user work.

Do not use destructive commands such as:

```bash
git reset --hard
git clean -fd
git checkout -- .
git restore .
```

unless explicitly requested and the consequences are understood.

Unless explicitly requested:

- do not force-push
- do not rewrite unrelated history
- do not amend previously reviewed commits
- do not squash commits automatically
- do not create tags
- do not create releases
- do not push
- do not create a pull request
- do not modify remote repository state

Never push unless explicitly requested.

---

## Pre-Completion Checklist

Before declaring a task complete:

1. Review the full diff.
2. Confirm all changes are intentional.
3. Run the relevant targeted tests where useful.
4. Run:

   ```bash
   ./tests/run.sh
   ```

5. Run:

   ```bash
   git diff --check
   git status --short
   ```

6. For security-sensitive work, audit related code for the same vulnerability class.
7. Confirm no existing security invariant was weakened.
8. Confirm legitimate existing behavior still works.
9. Confirm cleanup/restoration still works if affected.
10. Confirm tests did not modify real-user configuration.
11. Report known limitations rather than hiding them.

---

## Completion Report

When finishing a task, report:

- root cause
- files changed
- important implementation decisions
- security implications where relevant
- tests executed
- test results
- remaining limitations, if any

For security fixes, also report:

- vulnerability class
- how the unsafe primitive was eliminated
- adversarial regression coverage added
- whether equivalent code paths were audited

Use precise claims.

Do not claim that something is fully secure or that all possible issues are
resolved unless the available evidence actually supports that statement.
