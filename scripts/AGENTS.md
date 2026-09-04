# Cursor Theme Manager — Script and Filesystem Safety Rules

These instructions apply to everything under `scripts/`.

The repository-level `../AGENTS.md` instructions also apply.

Security-sensitive filesystem operations in this project must preserve
user-owned data and resist symlink, special-file, pathname-race, and unsafe
cleanup attacks.

## Canonical Safety Implementation

Use the hardened filesystem primitives provided by:

```text
scripts/runtime_safety.py
```

Before creating a new filesystem-safety implementation:

1. Read `runtime_safety.py`.
2. Check whether an existing helper already provides the required operation.
3. Reuse or extend the existing helper where practical.
4. Add regression tests for any new security behavior.

Do not create parallel implementations of:

- held-parent directory traversal
- symlink protection
- file ownership validation
- file-type validation
- bounded reads
- safe atomic writes
- safe removal

unless the existing abstraction genuinely cannot support the requirement.

Security logic should remain centralized and auditable.

---

## Protected Configuration

Treat these as security-sensitive:

- `gtk-3.0/settings.ini`
- `gtk-4.0/settings.ini`
- `~/.gtkrc-2.0`
- `~/.icons/default/index.theme`
- other X11 cursor configuration managed by CTM
- UWSM configuration modified by CTM
- CTM state used for restoration or cleanup
- baseline/restoration configuration
- future desktop-environment files modified by CTM

Do not introduce ordinary pathname reads, truncating writes, or unsafe
deletions for these targets.

When adding a new configuration target, determine whether it needs the same
hardened treatment before implementing it.

---

## Pathname and TOCTOU Safety

Do not use an earlier pathname check as the security boundary for a later
filesystem operation.

Unsafe patterns include:

```python
if os.path.exists(path):
    with open(path) as f:
        ...
```

and:

```python
if not path.is_symlink():
    path.write_text(data)
```

and:

```python
st = os.lstat(path)
# time passes
with open(path, "w") as f:
    ...
```

The pathname may refer to a different object by the time the later operation
runs.

Do not rely on:

- `exists()`
- `is_file()`
- `is_symlink()`
- `stat()`
- `lstat()`

followed by an independent pathname operation as a security boundary.

Use descriptor-relative operations and held-parent directory descriptors where
required.

---

## Directory Traversal

Intermediate directories are part of the security boundary.

For security-sensitive paths:

- traverse components without following symlinks
- hold directory descriptors when later operations depend on directory identity
- validate directory type
- validate ownership where required
- reject unsafe intermediate path components
- avoid reopening a previously validated directory through a fresh pathname lookup

Do not validate only the final component.

For example, a safe-looking:

```text
~/.config/gtk-3.0/settings.ini
```

is not sufficient if `gtk-3.0` itself can be replaced with a symlink.

---

## Security-Sensitive Reads

Security-sensitive reads should:

1. operate relative to a validated held parent descriptor
2. refuse symlink traversal
3. use appropriate flags such as:

   ```text
   O_RDONLY
   O_NOFOLLOW
   O_CLOEXEC
   ```

4. use `O_NONBLOCK` where a special file could otherwise block
5. validate the opened descriptor with `fstat()`
6. require the expected file type
7. require a regular file for ordinary configuration data
8. validate ownership where required
9. enforce a bounded maximum file size
10. perform bounded reads
11. close all descriptors reliably

Never perform unbounded or potentially blocking reads from:

- FIFOs
- sockets
- character devices
- block devices
- directories
- unknown special files

Do not use ordinary `Path.read_text()` or equivalent operations for protected
user configuration.

---

## Security-Sensitive Writes

Do not use ordinary truncating pathname writes for protected configuration.

Avoid:

```python
open(path, "w")
```

and:

```python
Path(path).write_text(data)
```

for security-sensitive targets.

Hardened writes should:

1. operate relative to a validated held parent descriptor
2. inspect an existing destination without following symlinks
3. reject unsafe symlink destinations
4. reject unexpected file types
5. reject foreign-owned destinations where ownership checks are required
6. create a unique temporary file relative to the held parent
7. validate the temporary file descriptor
8. write the complete expected content
9. flush the file
10. `fsync()` when persistence is required
11. revalidate the destination where necessary
12. commit using atomic descriptor-relative replacement
13. `fsync()` the parent directory where persistence matters
14. safely remove abandoned temporary files after failures

Never fall back to an ordinary pathname write when the hardened operation
fails.

---

## Safe Removal

Never blindly unlink security-sensitive files.

Before deletion:

- validate the held parent
- reject unsafe symlinks where applicable
- validate file type
- validate ownership where required
- validate CTM-specific markers where applicable
- ensure CTM is entitled to remove the file

Deletion must preserve unrelated user configuration.

Cleanup success is not more important than user-data safety.

---

## Fail-Closed Behavior

When ownership, type, identity, or destination safety cannot be established,
refuse the mutation.

Never use code like:

```python
try:
    safe_operation()
except Exception:
    unsafe_fallback()
```

Do not convert a security validation failure into a successful but weaker
operation.

---

## Error Handling

Do not hide security failures.

Avoid:

```python
try:
    security_sensitive_operation()
except Exception:
    pass
```

Rules:

- do not silently ignore ownership failures
- do not silently ignore symlink detection
- do not silently ignore unexpected file types
- do not silently ignore integrity failures
- preserve actionable error information
- do not expose secrets or unrelated user file contents
- cleanup may tolerate a legitimately missing CTM-owned target
- cleanup must not silently tolerate an unsafe replacement target

If continuing after an error is intentionally safe, document why.

---

## Imported Theme Safety

Treat imported themes and theme metadata as untrusted.

Validate:

- theme names
- cursor names
- size values
- path components
- metadata lengths
- input file sizes
- archive members where relevant

Prevent:

- `..` path traversal
- unexpected absolute paths
- archive escape
- unintended symlink traversal
- special-file processing
- unbounded reads

Do not assume imported content is trustworthy because the user selected it.

---

## Subprocess Safety

When invoking commands:

- prefer argument arrays
- avoid `shell=True`
- never interpolate untrusted values into shell command strings
- check return codes where failure matters
- use bounded timeouts where commands could hang
- avoid unnecessary shells when a direct Python API exists
- do not silently discard security-relevant failures

Prefer:

```python
subprocess.run(
    ["command", "--option", value],
    check=True,
)
```

over:

```python
subprocess.run(
    f"command --option {value}",
    shell=True,
)
```

---

## Shell Safety

For shell scripts:

- quote variable expansions
- prefer arrays for command arguments
- avoid `eval`
- never execute user-controlled strings as shell code
- use `--` before user-controlled paths when supported
- avoid predictable temporary filenames
- use `mktemp` or an equivalent safe primitive
- do not broadly suppress failures with `|| true`
- preserve meaningful error status
- avoid unsafe assumptions about `/tmp`

---

## Security Audit After Changes

When changing security-sensitive filesystem code, search for equivalent unsafe
patterns rather than only reviewing the edited function.

Use:

```bash
rg -n \
'open\(|read_text|read_bytes|write_text|write_bytes|os\.path\.exists|Path\(.*\)\.exists|unlink\(|remove\(|rename\(|replace\(|stat\(|lstat\(' \
scripts/
```

Occurrences are not automatically vulnerabilities.

Review relevant occurrences and determine whether they touch:

- user-controlled paths
- protected configuration
- imported data
- restoration state
- cleanup targets
- attacker-influenceable filesystem objects

Do not mechanically replace ordinary I/O that only reads trusted packaged
assets.

---

## Security Regression Requirements

A security fix should test the vulnerability class, not only one pathname.

Where applicable, test:

- final-component symlinks
- intermediate-directory symlinks
- FIFOs
- other special files
- oversized files
- malformed files
- unexpected directories
- broken symlinks
- foreign-owned files where practical
- failed writes
- cleanup
- restoration
- normal legitimate operation

Any security-sensitive implementation change must still pass:

```bash
./tests/run.sh
```

from the repository root.
