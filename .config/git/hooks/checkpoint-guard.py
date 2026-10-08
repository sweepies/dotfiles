#!/usr/bin/env python3
"""Fail closed before Entire's pre-push hook can upload session checkpoints."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

CHECKPOINT_REPO = "sweepies/entire-checkpoints"
APPROVED_URLS = {
    f"git@github.com:{CHECKPOINT_REPO}",
    f"git@github.com:{CHECKPOINT_REPO}.git",
    f"https://github.com/{CHECKPOINT_REPO}",
    f"https://github.com/{CHECKPOINT_REPO}.git",
    f"ssh://git@github.com/{CHECKPOINT_REPO}",
    f"ssh://git@github.com/{CHECKPOINT_REPO}.git",
}


class Refused(Exception):
    """An unverifiable or unsafe checkpoint upload."""


def capture(*args: str) -> subprocess.CompletedProcess[str]:
    """Never inherit push stdin or echo tool output, which may contain secrets."""
    try:
        return subprocess.run(
            args, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        raise Refused(f"Could not verify {args[0]}; install/authenticate it and retry.") from error


def checkpoint_ref(ref: str) -> bool:
    return ref in {"refs/entire", "refs/heads/entire"} or ref.startswith(
        ("refs/entire/", "refs/heads/entire/")
    )


def transfers_checkpoints(data: bytes) -> bool:
    protected = False
    for line in data.splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise Refused("Malformed pre-push ref input; push refused.")
        local_ref, local_oid, remote_ref, remote_oid = fields
        if not all(re.fullmatch(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})", oid)
                   for oid in (local_oid, remote_oid)):
            raise Refused("Malformed pre-push object ID; push refused.")
        # Deletions send no new checkpoint data and must remain possible.
        if local_oid.strip(b"0") and any(
            checkpoint_ref(ref.decode("ascii", errors="replace"))
            for ref in (local_ref, remote_ref)
        ):
            protected = True
    return protected


def private_destination() -> None:
    result = capture("gh", "api", "--hostname", "github.com", f"repos/{CHECKPOINT_REPO}", "--jq", ".private")
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise Refused("The approved checkpoint repository is not verifiably private; authenticate gh and retry.")


def rewritten_url(url: str) -> str:
    result = capture("git", "ls-remote", "--get-url", url)
    if result.returncode != 0:
        raise Refused("Could not resolve the checkpoint destination's Git URL.")
    return result.stdout.strip()


def approved_push_destination(remote: str, url: str) -> None:
    # get-url expands insteadOf/pushInsteadOf, including every pushurl for a
    # named remote. --get-url does not connect to the remote.
    result = capture("git", "remote", "get-url", "--push", "--all", remote)
    urls = result.stdout.splitlines() if result.returncode == 0 else []
    urls.append(rewritten_url(url))
    if any(candidate not in APPROVED_URLS for candidate in urls):
        raise Refused("Checkpoint refs may only be pushed to the approved private checkpoint repository.")


def configured_entire() -> bool:
    root = capture("git", "rev-parse", "--show-toplevel")
    if root.returncode != 0:
        bare = capture("git", "rev-parse", "--is-bare-repository")
        if bare.returncode != 0 or bare.stdout.strip() != "true":
            raise Refused("Could not identify the source repository.")
    else:
        directory = Path(root.stdout.strip()) / ".entire"
        if any(path.exists() or path.is_symlink() for path in (
            directory / "settings.json", directory / "settings.local.json",
        )):
            return True
    # Entire defaults to enabled when settings are absent. Deleting its settings
    # must not let a retained native pre-push hook upload via fallback routing.
    common = capture("git", "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common.returncode != 0:
        raise Refused("Could not inspect the repository's existing hook setup.")
    try:
        hook = Path(common.stdout.strip()) / "hooks/pre-push"
        return b"Entire CLI hooks" in hook.read_bytes()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise Refused("Could not inspect the repository's existing pre-push hook.") from error


def effective_checkpoint_provider() -> None:
    """Verify the provider omitted by status, matching Entire 0.11.4's merge.

    Strategy-option keys merge, but checkpoint_remote is replaced as a whole.
    Clone preferences do not override this option; index-tracked local settings
    are ignored by Entire. Require an explicit, regular, untracked local route
    (including HEAD provenance), because status resolves its elected remote,
    not necessarily the remote passed to the actual pre-push handler.
    """
    root = capture("git", "rev-parse", "--show-toplevel")
    if root.returncode != 0:
        raise Refused("Could not locate Entire's settings.")
    directory = Path(root.stdout.strip()) / ".entire"
    route = None
    local_route_declared = False
    for name in ("settings.json", "settings.local.json"):
        if name == "settings.local.json":
            tracked = capture("git", "ls-files", "--error-unmatch", "--", str(directory / name))
            if tracked.returncode == 0:
                continue
            if tracked.returncode != 1:
                raise Refused("Could not verify Entire's local settings provenance.")
        try:
            data = json.loads((directory / name).read_text())
        except FileNotFoundError:
            continue
        except (OSError, ValueError, UnicodeError) as error:
            raise Refused("Could not verify Entire's checkpoint provider.") from error
        if not isinstance(data, dict):
            raise Refused("Malformed Entire settings; push refused.")
        options = data.get("strategy_options")
        if options is None:
            continue
        if not isinstance(options, dict):
            raise Refused("Malformed Entire strategy options; push refused.")
        if "checkpoint_remote" in options:
            route = options["checkpoint_remote"]
            local_route_declared = name == "settings.local.json"
    if (not isinstance(route, dict) or route.get("provider") != "github"
            or route.get("repo") != CHECKPOINT_REPO):
        raise Refused("Entire's effective checkpoint provider must be github:sweepies/entire-checkpoints.")
    if not local_route_declared or (directory / "settings.local.json").is_symlink():
        raise Refused("Entire must be locally enrolled with an untracked settings.local.json; run mise run entire:checkpoints.")
    # Entire's ownership override uses BOTH index and HEAD. A staged removal
    # alone must not let inherited settings masquerade as clone-local consent.
    historical = capture("git", "ls-tree", "-r", "--name-only", "HEAD", "--", ".entire/settings.local.json")
    if historical.returncode != 0:
        refs = capture("git", "show-ref")
        if refs.returncode != 1 or refs.stdout.strip():
            raise Refused("Could not verify the history of Entire's local settings.")
    elif historical.stdout.strip():
        raise Refused("Entire's settings.local.json is present in HEAD; commit its removal before enrolling locally.")


def push_urls(url: str) -> list[str]:
    # `remote get-url` rejects remotes defined only by -c on Git 2.50.
    # Use a private throwaway Git dir containing ONLY a canonical probe URL;
    # inject the caller's effective rewrite rules in memory. Git itself decides
    # longest-prefix/transport precedence. No repo config or network is touched.
    rewrites = capture("git", "config", "--null", "--get-regexp", r"^url\..*\.(insteadof|pushinsteadof)$")
    if rewrites.returncode not in (0, 1):
        raise Refused("Could not inspect Git's push URL rewrites.")
    try:
        with tempfile.TemporaryDirectory(prefix="checkpoint-url-probe-") as directory:
            root = Path(directory)
            (root / "objects").mkdir()
            (root / "refs").mkdir()
            (root / "HEAD").write_text("ref: refs/heads/probe\n")
            (root / "config").write_text('[core]\n\tbare = true\n[remote "probe"]\n\turl = ' + url + '\n')
            args = ["git", "--git-dir=" + str(root)]
            for entry in rewrites.stdout.split("\0"):
                if entry:
                    key, value = entry.split("\n", 1)
                    args.extend(["-c", key + "=" + value])
            result = capture(*args, "remote", "get-url", "--push", "--all", "probe")
    except (OSError, ValueError) as error:
        raise Refused("Could not resolve the automatic checkpoint push destination.") from error
    if result.returncode != 0 or not result.stdout.strip():
        raise Refused("Could not resolve the automatic checkpoint push destination.")
    return result.stdout.splitlines()


def verify_source_host(remote: str, url: str) -> None:
    # Entire's direct transport derives the checkpoint HOST from the source push
    # URL, preserving enterprise hosts and ports. Only github.com is approved.
    result = capture("git", "remote", "get-url", "--push", "--all", remote)
    if result.returncode != 0 or not result.stdout.strip():
        # status resolves origin, while the actual hook passes its push remote.
        # Entire falls back to that source target when a bare URL/unknown name
        # cannot be enumerated, bypassing the otherwise dedicated store.
        raise Refused("Enabled Entire requires a configured push remote; do not push to a bare URL.")
    candidates = result.stdout.splitlines() + [url]
    for candidate in candidates:
        if candidate.startswith("git@github.com:"):
            continue
        parsed = urlsplit(candidate)
        if (parsed.scheme in {"https", "ssh"} and parsed.hostname == "github.com"
                and parsed.port is None):
            continue
        # Non-network transports make Entire derive a provider URL instead.
        if parsed.scheme == "file" or (not parsed.scheme and ":" not in candidate):
            continue
        raise Refused("Cannot verify Entire's derived checkpoint host; use a github.com source push URL.")


def verify_route(remote: str, url: str) -> bool:
    if not configured_entire():
        return False
    result = capture("entire", "status", "--json")
    try:
        status = json.loads(result.stdout)
    except (ValueError, UnicodeError) as error:
        raise Refused("Entire's configuration could not be verified; repair it before pushing.") from error
    if (result.returncode != 0 or not isinstance(status, dict)
            or status.get("error") or type(status.get("enabled")) is not bool):
        raise Refused("Entire's configuration could not be verified; repair it before pushing.")
    if not status["enabled"]:
        return False
    if (status.get("checkpoint_sync_remote") != CHECKPOINT_REPO
            or status.get("checkpoint_sync_remote_source") != "dedicated"):
        raise Refused("Entire is enabled without the approved private route. Run: mise run entire:checkpoints")
    effective_checkpoint_provider()
    verify_source_host(remote, url)
    # Entire's internal uploads use --no-verify. Check their push-side rewrites
    # here, before allowing the local hook/native handler to perform any upload.
    for target in (f"git@github.com:{CHECKPOINT_REPO}.git", f"https://github.com/{CHECKPOINT_REPO}.git"):
        if any(candidate not in APPROVED_URLS for candidate in push_urls(target)):
            raise Refused("A Git URL rewrite redirects the private checkpoint destination; reconcile it first.")
    return True


def main() -> int:
    if len(sys.argv) != 4:
        raise Refused("Expected a repository hook path, remote name and remote URL.")
    local_hook, remote, url = sys.argv[1:]
    data = sys.stdin.buffer.read()
    protected = transfers_checkpoints(data)
    enabled = verify_route(remote, url)
    if protected:
        approved_push_destination(remote, url)
    if enabled or protected:
        private_destination()
    path = Path(local_hook)
    try:
        if os.access(path, os.X_OK):
            result = subprocess.run([local_hook, remote, url], input=data, check=False)
        elif enabled:
            # Entire already considers the global compatibility entrypoints installed.
            # An enabled clone without local hooks still gets native checkpoint sync.
            result = subprocess.run(["entire", "hooks", "git", "pre-push", remote], input=data, check=False)
        else:
            return 0
    except OSError as error:
        raise Refused("Could not execute the repository's pre-push hook.") from error
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as error:
        print(f"dotfiles: {error}", file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError):
        print("dotfiles: could not verify or execute the repository's pre-push hook.", file=sys.stderr)
        sys.exit(1)
