"""Read-only global-hook audits of disposable real Git repositories/worktrees."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="git-hook-audit-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.source = self.root / "shared-hooks"
        shutil.copytree(HOOKS, self.source)
        self.source.chmod(0o555)
        self.addCleanup(self.source.chmod, 0o755)
        self.link = self.home / ".config/git/hooks"
        self.link.parent.mkdir(parents=True)
        self.link.symlink_to(self.source, target_is_directory=True)
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("GIT_", "ENTIRE_", "GH_", "DOTFILES_"))}
        self.env.update(HOME=str(self.home), GIT_CONFIG_GLOBAL=str(self.home / ".gitconfig"),
                        XDG_CONFIG_HOME=str(self.home / ".config"),
                        GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0", GIT_ALLOW_PROTOCOL="file")
        self.command("git", "config", "--global", "core.hooksPath", str(self.link))
        self.command("git", "config", "--global", "user.name", "Audit Fixture")
        self.command("git", "config", "--global", "user.email", "audit@example.invalid")
        self.command("git", "config", "--global", "commit.gpgsign", "false")
        self.repo = self.home / "repo"
        self.command("git", "init", str(self.repo))
        (self.repo / "source").write_text("fixture\n")
        self.command("git", "-C", str(self.repo), "add", "source")
        self.command("git", "-C", str(self.repo), "-c", "core.hooksPath=/dev/null", "commit", "-m", "fixture")

    def command(self, *args, check=True):
        result = subprocess.run(args, cwd=self.root, env=self.env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=30, check=False)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def audit(self):
        return self.command(sys.executable, str(HOOKS / "audit.py"), check=False)

    def use_xdg_defaults(self):
        self.env.pop("GIT_CONFIG_GLOBAL")
        local = self.home / ".gitconfig"
        local.rename(self.home / ".config/git/config")
        local.touch()

    def test_xdg_defaults_with_empty_machine_local_config(self):
        self.use_xdg_defaults()
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_xdg_defaults_preserve_machine_local_settings(self):
        self.use_xdg_defaults()
        self.command("git", "config", "--global", "alias.fixture", "status")
        configs = [self.home / ".gitconfig", self.home / ".config/git/config"]
        before = [path.read_bytes() for path in configs]
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([path.read_bytes() for path in configs], before)

    def test_machine_local_hook_override_takes_precedence_over_xdg(self):
        self.use_xdg_defaults()
        self.command("git", "config", "--global", "core.hooksPath", "/fixture/custom")
        result = self.audit()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Global core.hooksPath does not point", result.stdout)

    def test_last_global_hook_value_wins(self):
        self.use_xdg_defaults()
        self.command("git", "config", "--file", str(self.home / ".config/git/config"), "core.hooksPath", "/fixture/old")
        self.command("git", "config", "--global", "core.hooksPath", "~/.config/git/hooks")
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_command_scope_cannot_substitute_for_missing_global_hooks(self):
        self.command("git", "config", "--global", "--unset", "core.hooksPath")
        self.env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.hooksPath", GIT_CONFIG_VALUE_0=str(self.link))
        result = self.audit()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Global core.hooksPath does not point", result.stdout)

    def test_multiple_worktrees_without_extension_are_auditable(self):
        self.command("git", "-C", str(self.repo), "worktree", "add", "-b", "fixture", str(self.home / "linked"))
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Audited 2 repos", result.stdout)

    def test_worktree_override_is_reported_without_modification(self):
        linked = self.home / "linked"
        self.command("git", "-C", str(self.repo), "worktree", "add", "-b", "fixture", str(linked))
        self.command("git", "-C", str(self.repo), "config", "extensions.worktreeConfig", "true")
        self.command("git", "-C", str(linked), "config", "--worktree", "core.hooksPath", "/fixture/custom")
        result = self.audit()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Hook-path override", result.stdout)
        self.assertEqual(self.command("git", "-C", str(linked), "config", "--worktree", "--get", "core.hooksPath").stdout.strip(), "/fixture/custom")

    def test_local_override_is_reported_without_modification(self):
        self.command("git", "-C", str(self.repo), "config", "--local", "core.hooksPath", "/fixture/custom")
        result = self.audit()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Hook-path override", result.stdout)
        self.assertEqual(self.command("git", "-C", str(self.repo), "config", "--local", "--get", "core.hooksPath").stdout.strip(), "/fixture/custom")

    def test_local_include_override_is_reported_without_modification(self):
        included = self.home / "included.config"
        included.write_text("[core]\n\thooksPath = /fixture/included\n")
        self.command("git", "-C", str(self.repo), "config", "--local", "include.path", str(included))
        result = self.audit()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Effective hook path bypasses", result.stdout)
        self.assertIn("Hook-path override", result.stdout)
        self.assertEqual(self.command("git", "-C", str(self.repo), "config", "--get", "core.hooksPath").stdout.strip(), "/fixture/included")

    def test_conditional_global_include_effective_override_is_reported(self):
        included = self.home / "conditional.config"
        included.write_text("[core]\n\thooksPath = /fixture/conditional\n")
        self.command("git", "config", "--global", f"includeIf.gitdir:{self.repo.resolve()}/.path", str(included))
        self.assertEqual(self.command("git", "-C", str(self.repo), "config", "--get", "core.hooksPath").stdout.strip(), "/fixture/conditional")
        result = self.audit()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Effective hook path bypasses", result.stdout)

    def test_command_scope_effective_override_is_reported(self):
        self.env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.hooksPath", GIT_CONFIG_VALUE_0="/fixture/command")
        result = self.audit()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Effective hook path bypasses", result.stdout)

    def test_editor_dependency_git_stubs_are_not_repositories(self):
        nested = self.home / ".vscode/extensions/fixture"
        nested.mkdir(parents=True)
        (nested / ".git").write_text("gitdir: ../missing\n")
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Audited 1 repos", result.stdout)


if __name__ == "__main__":
    unittest.main()
