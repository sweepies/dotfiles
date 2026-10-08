#!/usr/bin/env python3
"""Read-only hook audit; never rewrite repository config or install local hooks."""

import os
from pathlib import Path
import subprocess
import sys

# Do not descend into dependency/cache trees. Explicit roots are still checked.
SKIP = {".git", "node_modules", ".venv", "venv", "vendor", "Library",
        ".Trash", ".cache", ".local", "Downloads", "__pycache__",
        ".vscode", ".vscode-server"}
ENTRYPOINT = '''#!/bin/sh
# Entire CLI hooks — global guarded dispatcher (native detection compatibility).
# Entire invokes its handler only once, via the repo hook or dispatch fallback.
DOTFILES_HOOK_NAME=${0##*/}
export DOTFILES_HOOK_NAME
exec "${0%/*}/dispatch" "$@"
'''
EVENTS = """applypatch-msg pre-applypatch post-applypatch pre-commit pre-merge-commit
prepare-commit-msg commit-msg post-commit pre-rebase post-checkout post-merge
pre-push pre-receive update proc-receive post-receive post-update
reference-transaction push-to-checkout pre-auto-gc post-rewrite sendemail-validate
fsmonitor-watchman p4-changelist p4-prepare-changelist p4-post-changelist
p4-pre-submit post-index-change""".split()


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, check=False)


def repositories(roots: list[Path]):
    seen = set()
    for root in roots:
        for directory, children, files in os.walk(root, followlinks=False):
            path = Path(directory)
            children[:] = sorted(name for name in children if name not in SKIP)
            if (path / ".git").exists() or (
                "HEAD" in files and "config" in files and "objects" in children
            ):
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    yield path
                # Scan nested repositories too, but not this repo's Git metadata.


def main() -> int:
    expected = Path.home() / ".config/git/hooks"
    problems = False
    result = git("config", "--global", "--includes", "--path", "--get", "core.hooksPath")
    if result.returncode != 0 or Path(result.stdout.strip()) != expected:
        print("Global core.hooksPath does not point to ~/.config/git/hooks.")
        problems = True
    if not expected.is_symlink():
        print("Shared hooks must be a mise-managed DIRECTORY symlink to prevent Entire replacing the guard.")
        problems = True
    if expected.is_dir() and expected.stat().st_mode & 0o222:
        print("Shared hook directory is writable; reapply mise dotfiles to protect it from Entire uninstall.")
        problems = True
    source = Path(__file__).resolve().parent
    for name in [*EVENTS, "dispatch", "checkpoint-guard.py"]:
        path = expected / name
        try:
            if not path.is_file() or path.read_bytes() != (source / name).read_bytes():
                print(f"Shared hook missing or changed: {name}")
                problems = True
            elif name in EVENTS:
                if path.is_symlink() or not os.access(path, os.X_OK) or path.read_text() != ENTRYPOINT:
                    print(f"Shared hook must be the executable guarded entrypoint: {name}")
                    problems = True
            if name == "dispatch" and not os.access(path, os.X_OK):
                print("The shared dispatcher is not executable.")
                problems = True
        except OSError:
            print(f"Shared hook could not be read: {name}")
            problems = True
    roots = [Path(arg).expanduser().absolute() for arg in sys.argv[1:]] or [Path.home()]
    count = 0
    for repo in repositories(roots):
        count += 1
        values = []
        scopes = ["--local"]
        extension = git("-C", str(repo), "config", "--local", "--bool", "--get", "extensions.worktreeConfig")
        if extension.returncode not in (0, 1):
            print(f"Could not audit repository config: {repo}")
            problems = True
        elif extension.stdout.strip() == "true":
            scopes.append("--worktree")
        # Git rejects --worktree for multi-worktree repos unless this extension
        # is enabled. Without it all worktrees use the common local config.
        for scope in scopes:
            result = git("-C", str(repo), "config", scope, "--includes", "--show-origin", "--get-all", "core.hooksPath")
            if result.returncode not in (0, 1):
                print(f"Could not audit repository config: {repo}")
                problems = True
            for value in result.stdout.splitlines():
                if value not in values:
                    values.append(value)
        effective = git("-C", str(repo), "config", "--includes", "--path", "--get", "core.hooksPath")
        if effective.returncode != 0 or Path(effective.stdout.strip()) != expected:
            print(f"Effective hook path bypasses the global guard: {repo}")
            problems = True
        if values:
            print(f"Hook-path override (global guard bypassed): {repo}")
            # Report origin only: paths/values can contain sensitive user data.
            for value in values:
                print(f"  {value.split(chr(9), 1)[0]}")
            problems = True
    print(f"Audited {count} repos beneath {', '.join(str(root) for root in roots)} (dependency/cache trees and symlinks excluded).")
    if problems:
        print("Audit failed. Reconcile overrides explicitly; no repository config was changed.")
    else:
        print("Global dispatcher verified; no repository hook-path overrides found.")
    return 1 if problems else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except OSError:
        print("Could not complete the read-only Git hook audit.", file=sys.stderr)
        sys.exit(1)
