import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path


def git(args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, errors="surrogateescape")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {args[0]} failed")
    return result.stdout


def fingerprint_working_tree(cwd=None):
    cwd = cwd or Path.cwd()
    root = Path(git(["rev-parse", "--show-toplevel"], cwd).strip())
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"], cwd=root, capture_output=True, text=True, errors="surrogateescape"
    )
    if head.returncode not in (0, 128):
        raise RuntimeError(head.stderr.strip() or "Could not read Git HEAD")
    revision = head.stdout.strip() if head.returncode == 0 else "(unborn)"
    paths = sorted(
        path for path in git(["ls-files", "--cached", "--others", "--exclude-standard", "-z"], root).split("\0") if path
    )
    digest = hashlib.sha256(f"HEAD\0{revision}\0".encode("utf-8", "surrogateescape"))
    index = subprocess.run(["git", "ls-files", "--stage", "-z"], cwd=root, capture_output=True)
    if index.returncode != 0:
        raise RuntimeError(index.stderr.decode("utf-8", "replace").strip() or "Could not read Git index")
    digest.update(b"INDEX\0" + index.stdout + b"\0")

    for relative_path in paths:
        path = root / relative_path
        try:
            info = path.lstat()
        except FileNotFoundError:
            digest.update(f"{relative_path}\0missing\0".encode("utf-8", "surrogateescape"))
            continue

        digest.update(f"{relative_path}\0{info.st_mode & 0o777}\0".encode("utf-8", "surrogateescape"))
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(path)
            target_bytes = target.encode("utf-8", "surrogateescape")
            target_length = len(target.encode("utf-16-le", "surrogatepass")) // 2
            digest.update(f"symlink\0{target_length}\0".encode())
            digest.update(target_bytes)
            digest.update(b"\0")
        elif stat.S_ISREG(info.st_mode):
            contents = path.read_bytes()
            digest.update(f"file\0{len(contents)}\0".encode())
            digest.update(contents)
            digest.update(b"\0")
        else:
            raise RuntimeError(f"Cannot fingerprint non-file repository entry: {relative_path}")

    return digest.hexdigest()


def main(args):
    expected = args[0] if args else None
    if len(args) > 1 or (expected and not re.fullmatch(r"[a-f0-9]{64}", expected, re.IGNORECASE)):
        raise ValueError("Usage: python3 scripts/verification_snapshot.py [expected-sha256]")

    fingerprint = fingerprint_working_tree()
    status = "missing" if not expected else "current" if expected.lower() == fingerprint else "stale"
    report = {"status": status, "fingerprint": fingerprint}
    if expected:
        report["expected"] = expected
    print(json.dumps(report, separators=(",", ":")))
    return 1 if status == "stale" else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as error:
        print(f"Unable to create verification snapshot: {error}", file=sys.stderr)
        sys.exit(2)
