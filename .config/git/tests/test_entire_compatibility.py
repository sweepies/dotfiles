"""Optional offline integration checks against the installed Entire CLI.

Set ENTIRE_TEST_BINARY to the absolute mise-installed executable to run them.
Fixtures never use the real HOME, Git config, credentials or repositories.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import sys
import subprocess
import tempfile
import unittest

HOOK_SOURCE = Path(__file__).resolve().parents[1] / "hooks"


@unittest.skipUnless(os.environ.get("ENTIRE_TEST_BINARY"), "ENTIRE_TEST_BINARY not supplied")
class EntireCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="entire-global-hooks-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.source = self.root / "shared-hooks"
        shutil.copytree(HOOK_SOURCE, self.source)
        self.link = self.home / ".config/git/hooks"
        self.link.parent.mkdir(parents=True)
        self.link.symlink_to(self.source, target_is_directory=True)
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("GIT_", "ENTIRE_", "GH_", "FNOX_", "DOTFILES_"))}
        self.env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / ".config"),
                        GIT_CONFIG_GLOBAL=str(self.root / "gitconfig"), GIT_CONFIG_NOSYSTEM="1",
                        GIT_TERMINAL_PROMPT="0", GIT_ALLOW_PROTOCOL="file")
        self.binary = os.environ["ENTIRE_TEST_BINARY"]
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.command("git", "init")
        self.command("git", "config", "--global", "core.hooksPath", str(self.link))
        self.settings = self.repo / ".entire/settings.json"
        self.settings.parent.mkdir()
        self.settings.write_text(json.dumps({"enabled": True, "telemetry": False,
                                            "strategy_options": {"push_sessions": False}}))
        self.source.chmod(0o555)
        self.addCleanup(self.source.chmod, 0o755)
        self.initial = self.fingerprints()

    def command(self, *args, check=True):
        result = subprocess.run(args, cwd=self.repo, env=self.env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=30, check=False)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def fingerprints(self):
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.source.iterdir() if path.is_file()}

    def test_native_status_and_hook_preserve_global_regular_entrypoints(self):
        status = json.loads(self.command(self.binary, "status", "--json").stdout)
        self.assertTrue(status["enabled"])
        self.assertTrue(status["checkpoint_push_disabled"])
        self.command(self.binary, "hooks", "git", "pre-push", "origin")
        self.assertEqual(self.fingerprints(), self.initial)

    def test_native_force_install_cannot_replace_global_guard(self):
        result = self.command(self.binary, "configure", "--local", "--force", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr + result.stdout)
        self.assertEqual(self.fingerprints(), self.initial)

    def test_native_uninstall_cannot_delete_global_guard(self):
        result = self.command(self.binary, "disable", "--uninstall", "--force", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.fingerprints(), self.initial)

    def invoke_guard_with_native_status(self, provider="github", push_rewrite=False,
                                       inherited=False, push_remote="origin"):
        self.command("git", "remote", "add", "origin", "https://github.com/sweepies/source.git")
        route = {"provider": provider, "repo": "sweepies/entire-checkpoints"}
        if inherited:
            settings = json.loads(self.settings.read_text())
            settings["strategy_options"]["checkpoint_remote"] = route
            self.settings.write_text(json.dumps(settings))
        else:
            local = self.repo / ".entire/settings.local.json"
            local.write_text(json.dumps({"strategy_options": {"checkpoint_remote": route}}))
        push_url = "https://github.com/sweepies/source.git"
        if push_remote == "upstream":
            push_url = "https://github.com/another-owner/public.git"
            self.command("git", "remote", "add", "upstream", push_url)
        elif push_remote.startswith("https://"):
            push_url = push_remote
        if push_rewrite:
            self.command("git", "config", "url.https://github.com/sweepies/public-code.git.pushInsteadOf",
                         "git@github.com:sweepies/entire-checkpoints.git")
        marker = self.root / "local-hook-called"
        local_hook = self.repo / ".git/hooks/pre-push"
        local_hook.write_text("#!/bin/sh\nprintf called > " + shlex.quote(str(marker)) + "\n")
        local_hook.chmod(0o755)
        binary_dir = self.root / "bin"
        binary_dir.mkdir()
        gh = binary_dir / "gh"
        gh.write_text("#!/bin/sh\nprintf 'true\\n'\n")
        gh.chmod(0o755)
        self.env["PATH"] = str(binary_dir) + os.pathsep + str(Path(self.binary).parent) + os.pathsep + self.env["PATH"]
        status = json.loads(self.command(self.binary, "status", "--json").stdout)
        self.assertEqual(status["checkpoint_sync_remote"], "sweepies/entire-checkpoints")
        self.assertEqual(status["checkpoint_sync_remote_source"], "dedicated")
        result = self.command(sys.executable, str(HOOK_SOURCE / "checkpoint-guard.py"),
                              str(local_hook), push_remote, push_url, check=False)
        return result, marker

    def test_real_native_github_route_is_approved_before_local_hook(self):
        result, marker = self.invoke_guard_with_native_status()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(marker.exists())

    def test_real_native_default_enablement_cannot_bypass_deleted_settings(self):
        result, marker = self.invoke_guard_with_native_status()
        self.assertEqual(result.returncode, 0)
        marker.unlink()
        self.settings.unlink()
        (self.repo / ".entire/settings.local.json").unlink()
        hook = self.repo / ".git/hooks/pre-push"
        hook.write_text(hook.read_text() + "\n# Entire CLI hooks\n")
        result = self.command(sys.executable, str(HOOK_SOURCE / "checkpoint-guard.py"),
                              str(hook), "origin", "https://github.com/sweepies/source.git", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(marker.exists())

    def test_real_native_inherited_route_does_not_certify_upstream_push(self):
        result, marker = self.invoke_guard_with_native_status(inherited=True, push_remote="upstream")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("locally enrolled", result.stderr)
        self.assertFalse(marker.exists())

    def test_real_native_local_route_can_certify_other_owner_upstream_push(self):
        result, marker = self.invoke_guard_with_native_status(push_remote="upstream")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(marker.exists())

    def test_real_native_dedicated_status_does_not_certify_direct_url_push(self):
        result, marker = self.invoke_guard_with_native_status(push_remote="https://github.com/sweepies/public-code.git")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("configured push remote", result.stderr)
        self.assertFalse(marker.exists())

    def test_real_native_gitlab_same_slug_is_rejected_before_local_hook(self):
        result, marker = self.invoke_guard_with_native_status(provider="gitlab")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("provider", result.stderr)
        self.assertFalse(marker.exists())

    def test_real_native_route_push_only_redirect_is_rejected_before_local_hook(self):
        result, marker = self.invoke_guard_with_native_status(push_rewrite=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rewrite", result.stderr)
        self.assertFalse(marker.exists())

    def test_scoped_git_alias_installs_only_repository_hooks(self):
        common = self.command("git", "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        self.command("git", "-c", f"core.hooksPath={common}/hooks", "-c", "alias.entire-local=!" + self.binary,
                 "entire-local", "configure", "--local", "--force")
        for name in ("prepare-commit-msg", "commit-msg", "post-commit", "post-rewrite", "pre-push"):
            self.assertIn("hooks git", (Path(common) / "hooks" / name).read_text())
        self.assertEqual(self.fingerprints(), self.initial)
        self.assertEqual(self.command("git", "config", "--global", "--get", "core.hooksPath").stdout.strip(), str(self.link))


if __name__ == "__main__":
    unittest.main()
