# shebanglf

Repair CRLF line endings in Git-tracked shebang scripts with one local command, including extensionless launchers such as `bootstrap` and `gradlew`.

```sh
python3 shebanglf.py --fix /path/to/repo
```

An executable script beginning with `#!/bin/sh\r\n` can fail with `bad interpreter` or `No such file or directory` on Unix. shebanglf finds files by their `#!` prefix and converts their CRLF pairs to LF. It never executes the scripts it inspects.

[中文说明](docs/zh-CN.md) · [Problem evidence and alternatives](docs/problem.md) · [TDD record](docs/tdd.md)

## Requirements and installation

- Python 3.9+ and Git on `PATH`; Python standard library only.
- Linux, macOS, or Linux inside WSL. Tested on Linux with Python 3.14.4 and Git 2.53.0; other versions and macOS have not been tested. Native Windows is unsupported.
- A local Git working tree with the files already in its index. A first commit is unnecessary.

The single file `shebanglf.py` is the complete tool. Use it directly with Python; there is no package installation, account, network request, or runtime service dependency. To install a command inside this project, run from this directory:

```sh
mkdir -p bin
cp shebanglf.py bin/shebanglf
chmod +x bin/shebanglf
./bin/shebanglf --help
```

You can then use `/absolute/path/to/this/project/bin/shebanglf --fix /path/to/repo`. No global installation or configuration change is needed.

## Minimal example

For an indexed file named `bootstrap` containing `#!/bin/sh\r\necho hello\r\n`:

```sh
# Check without writing. Omit the path to use the current working tree.
python3 shebanglf.py /path/to/repo
# CRLF "bootstrap": 2 CRLF line endings
# scripts=1 affected=1 fixed=0 skipped=0 errors=0

# Repair the working-tree file.
python3 shebanglf.py --fix /path/to/repo
# FIXED "bootstrap": 2 CRLF line endings
# scripts=1 affected=1 fixed=1 skipped=0 errors=0
```

The default check exits **1** when it finds CRLF. A successful repair exits **0**. Review the change with `git -C /path/to/repo diff`; the Git index is unchanged, so staging remains your choice.

Passing a subdirectory still selects the **whole repository**. Filenames are printed as JSON strings so spaces, newlines, and other unusual characters cannot corrupt report lines. Non-ASCII characters may appear as escapes.

| Exit | Meaning |
| --- | --- |
| `0` | No CRLF found in supported scripts, or all supported repairs succeeded. Skipped files may remain. |
| `1` | Check mode found CRLF; nothing was written. |
| `2` | Invalid arguments, Git failure, or at least one file error. Other files may already have been repaired. |

The summary counts `scripts` with a `#!` prefix, `affected` supported text scripts containing CRLF, `fixed` successful replacements, `skipped` indexed symlinks/submodules, and `errors`. Unsupported scripts count as errors, not as affected files.

## Scope and limits

- Only files in the Git index whose current contents start with the exact bytes `#!` are candidates. Untracked files, scripts without a shebang, BOM-prefixed files, and files inside submodules are outside the scope. Executable permission is preserved, not added.
- Candidates must be UTF-8, without ASCII control bytes other than tab, CR, and LF. Unsupported encodings or binary-looking candidates cause exit 2. Indexed symlinks and submodules are reported as skipped; working-tree symlink substitutions, missing/unreadable files, non-regular entries, and unresolved merge entries are errors. Sparse checkouts with missing indexed files therefore produce errors.
- Repair replaces **every** CRLF pair in a candidate, including pairs inside literals and heredocs. Standalone CR bytes and a missing final newline remain unchanged. Use check mode first when embedded CRLF is intentional; this tool does not parse language syntax or validate interpreters.
- Repairs preserve the owner, group, and permission bits. A completed sibling temporary file replaces the original, so an ordinary write failure leaves that original intact. Hard-linked or non-writable affected files are refused. This changes the inode and modification time; ACLs and extended attributes are not preserved. There is no repository-wide rollback or backup.
- Run in a trusted, idle working tree. Concurrent edits or path replacements are not protected against. Each tracked regular file is read fully; large tracked assets can consume substantial memory. Forced termination may leave a temporary file. This is not a sandbox or a crash-durable transaction.
- This fixes the current working tree only. Future checkouts can reintroduce CRLF. Set appropriate Git [`text` / `eol` attributes](https://git-scm.com/docs/gitattributes) separately for lasting prevention. Global/system Git configuration and inherited `GIT_*` overrides are ignored by this tool; repository-local configuration still applies.

For a known single file, `dos2unix file` is already sufficient. shebanglf is useful when the repetitive part is selecting the right tracked scripts, especially extensionless ones. Teams with a suitable pre-commit setup may gain little from another command.

## Tests

Run as a regular user on a POSIX system; permission-error tests depend on unprivileged permission checks:

```sh
python3 -B -m unittest discover -s tests -v
```

The 17 integration tests invoke the real CLI and Git in disposable repositories under this project's `.test-tmp/`. They cover detection, executable repair, unchanged index and permissions, idempotence, unusual names, links, submodules, conflicts, invalid encodings, missing Git, permissions, and an actual size-limited write failure. The execution test runs only a tiny shell script created by the test.

Recorded result: **17 tests passed** in 1.673 seconds on Linux; see [the actual test output](docs/test-results.txt). The [red/green transcript](docs/tdd-transcript.txt) is retained separately.
