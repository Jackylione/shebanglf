#!/usr/bin/env python3
"""Check Git-tracked shebang scripts for CRLF line endings."""

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile


def replace_script(path, content, info):
    """Finish writing a sibling temporary file before replacing the original."""
    descriptor, temporary = tempfile.mkstemp(prefix=".shebanglf-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fchown(output.fileno(), info.st_uid, info.st_gid)
            os.fchmod(output.fileno(), stat.S_IMODE(info.st_mode))
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="Convert CRLF to LF in matching scripts.")
    parser.add_argument("repository", nargs="?", default=".")
    args = parser.parse_args()
    git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    git_env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        root_output = subprocess.run(
            ["git", "-C", args.repository, "rev-parse", "--show-toplevel"],
            capture_output=True, check=True, env=git_env,
        ).stdout
        root = Path(os.fsdecode(root_output[:-1]))
        listing = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--stage", "-z"],
            capture_output=True, check=True, env=git_env,
        ).stdout
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="replace").strip()
        print(f"ERROR: Git could not read the working tree: {detail}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: Git could not start; install Git and check PATH: {exc}", file=sys.stderr)
        return 2
    scripts = affected = fixed = skipped = errors = 0
    seen = set()
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, _oid, stage = metadata.split()
        relative = os.fsdecode(name)
        if name in seen:
            continue
        seen.add(name)
        if stage != b"0":
            print(f"ERROR {json.dumps(relative)}: unmerged index entry; resolve the conflict first", file=sys.stderr)
            errors += 1
            continue
        if mode in (b"120000", b"160000"):
            kind = "symlink" if mode == b"120000" else "submodule"
            print(f"SKIP {json.dumps(relative)}: {kind}")
            skipped += 1
            continue
        path = root / relative
        if any(part.is_symlink() for part in [path, *path.parents] if part != root):
            print(f"ERROR {json.dumps(relative)}: symlink in working-tree path", file=sys.stderr)
            errors += 1
            continue
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("not a regular file")
            content = path.read_bytes()
        except (OSError, ValueError) as exc:
            detail = exc.strerror if isinstance(exc, OSError) else str(exc)
            print(f"ERROR {json.dumps(relative)}: {detail}", file=sys.stderr)
            errors += 1
            continue
        if not content.startswith(b"#!"):
            continue
        scripts += 1
        try:
            content.decode("utf-8")
            if any((byte < 32 and byte not in (9, 10, 13)) or byte == 127 for byte in content):
                raise ValueError("binary control byte in script")
        except (UnicodeError, ValueError) as exc:
            detail = "not UTF-8 text" if isinstance(exc, UnicodeError) else str(exc)
            print(f"ERROR {json.dumps(relative)}: {detail}", file=sys.stderr)
            errors += 1
            continue
        if b"\r\n" in content:
            affected += 1
            count = content.count(b"\r\n")
            if args.fix:
                if info.st_nlink > 1:
                    print(f"ERROR {json.dumps(relative)}: hard-linked file; refusing repair", file=sys.stderr)
                    errors += 1
                    continue
                if not os.access(path, os.W_OK):
                    print(f"ERROR {json.dumps(relative)}: file is not writable", file=sys.stderr)
                    errors += 1
                    continue
                try:
                    replace_script(path, content.replace(b"\r\n", b"\n"), info)
                except OSError as exc:
                    print(f"ERROR {json.dumps(relative)}: {exc.strerror}", file=sys.stderr)
                    errors += 1
                    continue
                fixed += 1
            action = "FIXED" if args.fix else "CRLF"
            print(f"{action} {json.dumps(relative)}: {count} CRLF line endings")
    print(f"scripts={scripts} affected={affected} fixed={fixed} skipped={skipped} errors={errors}")
    if errors:
        return 2
    return 1 if affected and not args.fix else 0


if __name__ == "__main__":
    raise SystemExit(main())
