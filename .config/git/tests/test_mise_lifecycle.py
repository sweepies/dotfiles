"""Optional offline native mise test of read-only shared-hook repo updates.

Set MISE_TEST_BINARY to the absolute mise executable to run this integration.
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

CONFIG = Path(__file__).resolve().parents[3] / "mise.toml"


@unittest.skipUnless(os.environ.get("MISE_TEST_BINARY"), "MISE_TEST_BINARY not supplied")
class MiseLifecycleTests(unittest.TestCase):
    def test_remote_bootstrap_scopes_native_update_and_relocks_on_success_and_failure(self):
        remote_config = CONFIG.parent.parent / "remote-agent/mise.toml"
        if not remote_config.is_file():
            self.skipTest("the remote-agent sibling checkout is not available")
        with tempfile.TemporaryDirectory(prefix="mise-hook-update-") as directory:
            root = Path(directory)
            home = root / "home"
            home.mkdir()
            project = root / "project"
            project.mkdir()
            source = root / "source"
            source.mkdir()
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(("GIT_", "MISE_", "ENTIRE_", "GH_", "FNOX_", "DOTFILES_"))}
            env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                       MISE_CONFIG_DIR=str(home / ".config/mise"), MISE_DATA_DIR=str(home / ".local/share/mise"),
                       MISE_CACHE_DIR=str(home / ".cache/mise"), MISE_STATE_DIR=str(home / ".local/state/mise"),
                       MISE_TRUSTED_CONFIG_PATHS=str(root), MISE_EXPERIMENTAL="1", MISE_AUTO_UPDATE="0",
                       GIT_CONFIG_GLOBAL=str(root / "gitconfig"), GIT_CONFIG_NOSYSTEM="1",
                       GIT_ALLOW_PROTOCOL="file", GIT_TERMINAL_PROMPT="0")

            def command(*args, cwd=project):
                result = subprocess.run(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                        capture_output=True, text=True, timeout=60, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result

            command("git", "init", "-b", "main", str(source))
            command("git", "config", "--global", "user.name", "Mise Fixture")
            command("git", "config", "--global", "user.email", "mise@example.invalid")
            command("git", "config", "--global", "commit.gpgsign", "false")
            hooks = source / ".config/git/hooks"
            hooks.mkdir(parents=True)
            (hooks / "original").write_text("original\n")
            (source / "mise.toml").write_text('[settings]\nexperimental = true\n')
            command("git", "add", ".", cwd=source)
            command("git", "commit", "-m", "initial", cwd=source)
            checkout = home / "dotfiles"
            url = source.as_uri()
            command("git", "clone", url, str(checkout))
            installed = checkout / ".config/git/hooks"
            installed.chmod(0o555)
            try:
                (hooks / "new-event").write_text("updated\n")
                command("git", "add", ".", cwd=source)
                command("git", "commit", "-m", "add hook", cwd=source)
                config = tomllib.loads(remote_config.read_text())
                update = config["bootstrap"]["hooks"]["pre-repos"]["run"]
                lines = ['min_version = "2026.10.3"', '[bootstrap.repos]',
                         '"~/dotfiles" = { url = ' + json.dumps(url) + ', ref = "main" }',
                         '[bootstrap.hooks.pre-repos]', 'run = ' + json.dumps(update)]
                (project / "mise.toml").write_text("\n".join(lines) + "\n")
                command(os.environ["MISE_TEST_BINARY"], "bootstrap", "--yes")
                self.assertEqual((installed / "new-event").read_text(), "updated\n")
                self.assertEqual(installed.stat().st_mode & 0o222, 0)
                # Test the same native inline updater's cleanup even on a
                # repository-origin safety failure. No filesystem/network
                # write outside this fixture, and no forced Git resets.
                command("git", "remote", "set-url", "origin", "file:///nonexistent-dotfiles-fixture", cwd=checkout)
                result = subprocess.run([os.environ["MISE_TEST_BINARY"], "exec", "--", "sh", "-c", update],
                                        cwd=project, env=env, stdin=subprocess.DEVNULL,
                                        capture_output=True, text=True, timeout=60, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(installed.stat().st_mode & 0o222, 0)
            finally:
                installed.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
