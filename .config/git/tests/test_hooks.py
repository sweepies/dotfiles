"""Regression tests for the global Git hook dispatcher and checkpoint guard.

All Git configuration, repositories, hook entrypoints, and CLI fixtures are
private to each test. No network or real entire/gh executable is used.
Run from the dotfiles checkout with:
    python -m unittest discover -s .config/git/tests -v
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


GIT_CONFIG_DIR = Path(__file__).resolve().parents[1]
DISPATCH = GIT_CONFIG_DIR / "hooks" / "dispatch"
GUARD = GIT_CONFIG_DIR / "hooks" / "checkpoint-guard.py"
ZERO = "0" * 40
OID = "1" * 40
OTHER_OID = "2" * 40
EVENTS = (
    "pre-commit", "prepare-commit-msg", "commit-msg", "post-commit",
    "post-rewrite", "pre-push",
)


class HookTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(DISPATCH.is_file(), "parent must create hooks/dispatch")
        self.assertTrue(GUARD.is_file(), "parent must create checkpoint-guard.py")
        self.assertTrue(os.access(DISPATCH, os.X_OK), "hooks/dispatch must be executable")
        self.temp = tempfile.TemporaryDirectory(prefix="checkpoint-hook-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.hooks = self.root / "global-hooks"
        self.hooks.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "events.jsonl"
        self.entire_log = self.root / "entire.jsonl"
        self.gh_log = self.root / "gh.jsonl"
        # Do not inherit user Git routing, signing, config injection, or tracing.
        self.env = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("GIT_", "ENTIRE_", "GH_", "DOTFILES_GIT_HOOK", "DOTFILES_HOOK_NAME"))
        }
        self.env.update({
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "GIT_CONFIG_GLOBAL": str(self.root / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ALLOW_PROTOCOL": "file",  # Fail closed if a URL rewrite breaks.
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
            "EVENT_LOG": str(self.log),
            "ENTIRE_LOG": str(self.entire_log),
            "GH_LOG": str(self.gh_log),
            "ENTIRE_OUTPUT": json.dumps(self.enabled_status()),
            "ENTIRE_EXIT": "0",
            "GH_OUTPUT": "true\n",
            "GH_EXIT": "0",
            "LOCAL_HOOK_EXIT": "0",
        })
        for event in EVENTS:
            (self.hooks / event).symlink_to(DISPATCH)
        (self.hooks / "checkpoint-guard.py").symlink_to(GUARD)
        self.make_cli_stub("entire", "ENTIRE")
        self.make_cli_stub("gh", "GH")
        for key, value in (
            ("core.hooksPath", str(self.hooks)),
            ("user.name", "Hook Test"),
            ("user.email", "hook-test@example.invalid"),
            ("commit.gpgsign", "false"),
            ("tag.gpgsign", "false"),
            ("init.defaultBranch", "main"),
        ):
            self.run_git("config", "--global", key, value, cwd=self.root)
        self.repo = self.root / "source"
        self.run_git("init", str(self.repo), cwd=self.root)
        (self.repo / "source.txt").write_text("source\n")
        self.run_git("add", "source.txt")
        self.run_git("commit", "-m", "initial")
        self.oid = self.run_git("rev-parse", "HEAD").stdout.strip()
        self.common_hooks = self.repo / ".git" / "hooks"
        # Setup commits may exercise optional Entire commit-hook forwarding.
        for log in (self.log, self.entire_log, self.gh_log):
            if log.exists():
                log.unlink()

    @staticmethod
    def enabled_status(**changes):
        result = {
            "enabled": True,
            "checkpoint_sync_remote": "sweepies/entire-checkpoints",
            "checkpoint_sync_remote_source": "dedicated",
        }
        result.update(changes)
        return result

    def executable(self, path, contents):
        path.write_text(contents)
        path.chmod(0o755)

    def make_cli_stub(self, name, prefix):
        self.executable(self.bin / name, "#!" + sys.executable + "\n" +
            "import json, os, sys\n"
            f"with open(os.environ[{prefix + '_LOG'!r}], 'a') as stream:\n"
            "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            f"sys.stdout.write(os.environ.get({prefix + '_OUTPUT'!r}, ''))\n"
            f"code = int(os.environ.get({prefix + '_EXIT'!r}, '0'))\n"
            "if code: sys.stderr.write('fixture CLI failure\\n')\n"
            "sys.exit(code)\n")

    def command(self, argv, cwd=None, input_text=None, check=False):
        result = subprocess.run(
            [str(arg) for arg in argv], cwd=cwd or self.repo, env=self.env,
            input=input_text if input_text is not None else "",
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15,
        )
        if check:
            self.assertEqual(result.returncode, 0,
                f"command {argv!r}\nstdout: {result.stdout}\nstderr: {result.stderr}")
        return result

    def run_git(self, *args, cwd=None, check=True):
        return self.command(["git", *args], cwd=cwd, check=check)

    def records(self, path=None):
        path = path or self.log
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def local_hook(self, event="pre-push"):
        hooks = self.common_hooks
        hooks.mkdir(exist_ok=True)
        self.executable(hooks / event, "#!" + sys.executable + "\n" +
            "import json, os, sys\n"
            "record = {'event': os.path.basename(sys.argv[0]),\n"
            "          'args': sys.argv[1:], 'cwd': os.getcwd(),\n"
            "          'stdin': sys.stdin.read(),\n"
            "          'privacy_checked': os.path.exists(os.environ['GH_LOG'])}\n"
            "with open(os.environ['EVENT_LOG'], 'a') as stream:\n"
            "    stream.write(json.dumps(record) + '\\n')\n"
            "sys.exit(int(os.environ.get('LOCAL_HOOK_EXIT', '0')))\n")

    def configure_entire(self, filename="settings.json"):
        directory = self.repo / ".entire"
        directory.mkdir(exist_ok=True)
        (directory / filename).write_text(json.dumps({"enabled": True, "strategy_options": {
            "checkpoint_remote": {"provider": "github", "repo": "sweepies/entire-checkpoints"}}}))
        if filename == "settings.json" and not (directory / "settings.local.json").exists():
            (directory / "settings.local.json").write_bytes((directory / filename).read_bytes())
        if self.run_git("remote", "get-url", "origin", check=False).returncode != 0:
            self.run_git("config", "remote.origin.url", "https://github.com/sweepies/source.git")

    def push_row(self, local="refs/heads/main", remote="refs/heads/main", oid=OID):
        return f"{local} {oid} {remote} {OTHER_OID}\n"

    def hook(self, event="pre-push", args=None, stdin=None, cwd=None):
        if args is None:
            args = ["origin", "https://github.com/sweepies/source.git"] if event == "pre-push" else []
        if stdin is None:
            stdin = self.push_row() if event == "pre-push" else ""
        return self.command([self.hooks / event, *args], cwd=cwd, input_text=stdin)

    def assert_blocked(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.records(), [], "guard must reject before invoking local hook")

    def test_missing_local_hook_is_noop(self):
        args_by_event = {
            "prepare-commit-msg": [".git/COMMIT_EDITMSG", "message"],
            "commit-msg": [".git/COMMIT_EDITMSG"],
            "post-rewrite": ["amend"],
        }
        for event in EVENTS:
            with self.subTest(event=event):
                self.assertEqual(self.hook(event, args=args_by_event.get(event)).returncode, 0)
        self.assertEqual(self.records(), [])
        self.assertEqual(self.records(self.gh_log), [])

    def test_real_commit_forwards_hook_arguments_and_cwd(self):
        for event in ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit"):
            self.local_hook(event)
        (self.repo / "source.txt").write_text("changed\n")
        self.run_git("add", "source.txt")
        self.run_git("commit", "-m", "forwarding")
        records = self.records()
        self.assertEqual([r["event"] for r in records],
            ["pre-commit", "prepare-commit-msg", "commit-msg", "post-commit"])
        self.assertTrue(all(Path(r["cwd"]).resolve() == self.repo.resolve() for r in records))
        self.assertEqual(records[0]["args"], [])
        self.assertEqual(records[1]["args"][1], "message")
        self.assertEqual(Path(records[1]["args"][0]).name, "COMMIT_EDITMSG")
        self.assertEqual(Path(records[2]["args"][0]).name, "COMMIT_EDITMSG")
        self.assertEqual(records[3]["args"], [])

    def test_real_amend_forwards_post_rewrite_stdin_and_args(self):
        self.local_hook("post-rewrite")
        self.run_git("commit", "--amend", "-m", "rewritten")
        new_oid = self.run_git("rev-parse", "HEAD").stdout.strip()
        record, = self.records()
        self.assertEqual(record["args"], ["amend"])
        self.assertEqual(record["stdin"], f"{self.oid} {new_oid}\n")
        self.assertEqual(Path(record["cwd"]).resolve(), self.repo.resolve())

    def test_worktree_dispatch_uses_common_directory_hooks(self):
        self.local_hook("pre-commit")
        worktree = self.root / "linked-worktree"
        self.run_git("worktree", "add", "-b", "linked", str(worktree))
        self.run_git("commit", "--allow-empty", "-m", "worktree", cwd=worktree)
        record, = self.records()
        self.assertEqual(record["event"], "pre-commit")
        self.assertEqual(Path(record["cwd"]).resolve(), worktree.resolve())

    def test_pre_commit_preserves_local_failure(self):
        self.local_hook("pre-commit")
        self.env["LOCAL_HOOK_EXIT"] = "23"
        result = self.hook("pre-commit", args=["arg with spaces"])
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(self.records()[0]["args"], ["arg with spaces"])

    def test_recursive_symlink_to_shared_hook_fails(self):
        self.common_hooks.mkdir(exist_ok=True)
        target = self.common_hooks / "pre-commit"
        for shared in (self.hooks / "pre-commit", DISPATCH):
            with self.subTest(target=str(shared)):
                if target.exists() or target.is_symlink():
                    target.unlink()
                target.symlink_to(shared)
                result = self.hook("pre-commit")
                self.assertNotEqual(result.returncode, 0, "recursive hook must fail, not silently pass")

    def test_ordinary_repo_needs_neither_entire_nor_gh(self):
        self.local_hook()
        self.env.update(ENTIRE_EXIT="99", GH_EXIT="99")
        result = self.hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.records(self.entire_log), [])
        self.assertEqual(self.records(self.gh_log), [])

    def test_retained_native_hook_without_settings_cannot_upload_by_default(self):
        self.local_hook()
        hook = self.common_hooks / "pre-push"
        hook.write_text(hook.read_text() + "\n# Entire CLI hooks\n")
        self.assert_blocked(self.hook())
        self.assertEqual(self.records(self.entire_log), [["status", "--json"]])
        self.assertEqual(self.records(self.gh_log), [])

    def test_guard_preserves_pre_push_stdin_arguments_order_and_exit(self):
        self.configure_entire()
        self.local_hook()
        self.env["LOCAL_HOOK_EXIT"] = "37"
        rows = self.push_row() + self.push_row("refs/heads/topic", "refs/heads/topic")
        args = ["remote name", "https://github.com/sweepies/source.git"]
        self.run_git("config", "remote.remote name.url", args[1])
        result = self.hook(args=args, stdin=rows)
        self.assertEqual(result.returncode, 37, result.stderr)
        record, = self.records()
        self.assertEqual(record["stdin"], rows)
        self.assertEqual(record["args"], args)
        self.assertEqual(Path(record["cwd"]).resolve(), self.repo.resolve())
        self.assertTrue(record["privacy_checked"], "privacy check must precede local hook")
        self.assertEqual(self.records(self.entire_log), [["status", "--json"]])
        api_call, = self.records(self.gh_log)
        # Explicitly pinning github.com is also valid (and avoids GH_HOST drift).
        self.assertIn(api_call, (
            ["api", "repos/sweepies/entire-checkpoints", "--jq", ".private"],
            ["api", "--hostname", "github.com", "repos/sweepies/entire-checkpoints", "--jq", ".private"],
        ))

    def test_push_only_rewrite_blocks_automatic_upload_before_local_hook(self):
        self.configure_entire()
        self.local_hook()
        for prefix in ("git@github.com:sweepies/entire-checkpoints.git",
                       "https://github.com/sweepies/entire-checkpoints.git"):
            key = "url.https://github.com/sweepies/public-code.git.pushInsteadOf"
            self.run_git("config", key, prefix)
            result = self.hook()
            self.assert_blocked(result)
            self.assertIn("rewrite", result.stderr)
            self.run_git("config", "--unset", key)
        self.assertEqual(self.records(self.gh_log), [])

    def test_same_slug_wrong_provider_is_rejected(self):
        self.configure_entire()
        self.local_hook()
        path = self.repo / ".entire/settings.local.json"
        settings = json.loads(path.read_text())
        settings["strategy_options"]["checkpoint_remote"]["provider"] = "gitlab"
        path.write_text(json.dumps(settings))
        result = self.hook()
        self.assert_blocked(result)
        self.assertIn("provider", result.stderr)
        self.assertEqual(self.records(self.gh_log), [])

    def test_local_route_replaces_project_route_without_nested_merge(self):
        self.configure_entire()
        self.configure_entire("settings.local.json")
        self.local_hook()
        project = self.repo / ".entire/settings.json"
        settings = json.loads(project.read_text())
        settings["strategy_options"]["checkpoint_remote"]["provider"] = "gitlab"
        project.write_text(json.dumps(settings))
        self.assertEqual(self.hook().returncode, 0)
        self.log.unlink()
        local = self.repo / ".entire/settings.local.json"
        local.write_text(json.dumps({"strategy_options": {"checkpoint_remote": {
            "repo": "sweepies/entire-checkpoints"}}}))
        self.assert_blocked(self.hook())

    def test_index_tracked_local_route_is_not_developer_owned_enrollment(self):
        self.configure_entire()
        self.configure_entire("settings.local.json")
        self.local_hook()
        local = self.repo / ".entire/settings.local.json"
        settings = json.loads(local.read_text())
        settings["strategy_options"]["checkpoint_remote"]["provider"] = "gitlab"
        local.write_text(json.dumps(settings))
        self.run_git("add", ".entire/settings.local.json")
        self.assert_blocked(self.hook())

    def test_inherited_route_does_not_certify_actual_push_remote(self):
        self.configure_entire()
        (self.repo / ".entire/settings.local.json").unlink()
        self.run_git("config", "remote.upstream.url", "https://github.com/another-owner/public.git")
        self.local_hook()
        result = self.hook(args=["upstream", "https://github.com/another-owner/public.git"])
        self.assert_blocked(result)
        self.assertIn("locally enrolled", result.stderr)
        self.assertEqual(self.records(self.gh_log), [])

    def test_head_tracked_local_route_is_not_enrolled_after_staged_removal(self):
        self.configure_entire()
        self.run_git("add", ".entire/settings.local.json")
        self.run_git("commit", "-m", "inherited settings fixture")
        self.run_git("rm", "--cached", ".entire/settings.local.json")
        self.local_hook()
        result = self.hook()
        self.assert_blocked(result)
        self.assertIn("present in HEAD", result.stderr)

    def test_local_enrollment_is_valid_for_other_owner_push_remote(self):
        self.configure_entire()
        self.run_git("config", "remote.upstream.url", "https://github.com/another-owner/public.git")
        self.local_hook()
        self.assertEqual(self.hook(args=["upstream", "https://github.com/another-owner/public.git"]).returncode, 0)

    def test_enabled_direct_url_push_cannot_fall_back_to_source_destination(self):
        self.configure_entire()
        self.local_hook()
        url = "https://github.com/sweepies/public-code.git"
        result = self.hook(args=[url, url])
        self.assert_blocked(result)
        self.assertIn("configured push remote", result.stderr)
        self.assertEqual(self.records(self.gh_log), [])

    def test_enterprise_host_and_entire_mirror_are_not_approved_public_github(self):
        self.configure_entire()
        self.local_hook()
        for url in ("https://enterprise.example.invalid/sweepies/source.git",
                    "git@enterprise.example.invalid:sweepies/source.git",
                    "ssh://git@github.com:2222/sweepies/source.git",
                    "entire://mirror.example.invalid/github.com/sweepies/source"):
            with self.subTest(url=url):
                self.assert_blocked(self.hook(args=["origin", url]))
        self.assertEqual(self.records(self.gh_log), [])

    def test_settings_local_also_enables_guard(self):
        self.configure_entire("settings.local.json")
        self.local_hook()
        self.env["GH_OUTPUT"] = "false\n"
        self.assert_blocked(self.hook())
        self.assertEqual(len(self.records(self.entire_log)), 1)
        self.assertEqual(len(self.records(self.gh_log)), 1)

    def test_worktree_config_is_found_at_worktree_root(self):
        worktree = self.root / "configured-worktree"
        self.run_git("worktree", "add", "-b", "configured", str(worktree))
        (worktree / ".entire").mkdir()
        (worktree / ".entire" / "settings.local.json").write_text('{}\n')
        self.local_hook()
        self.env["GH_OUTPUT"] = "false\n"
        self.assert_blocked(self.hook(cwd=worktree))
        self.assertEqual(len(self.records(self.entire_log)), 1)

    def test_disabled_status_permits_ordinary_push_without_gh(self):
        self.configure_entire()
        self.local_hook()
        self.env["ENTIRE_OUTPUT"] = json.dumps({"enabled": False})
        self.env["GH_EXIT"] = "99"
        result = self.hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.records(self.entire_log), [["status", "--json"]])
        self.assertEqual(self.records(self.gh_log), [])

    def test_invalid_entire_status_blocks_before_local_hook(self):
        self.configure_entire()
        self.local_hook()
        outputs = (
            "not json", "", "[]", "null", "true", "{}",
            json.dumps({"enabled": "true"}),
            json.dumps({"enabled": 1}),
            json.dumps({"enabled": None}),
            json.dumps(self.enabled_status(error="status failure")),
            json.dumps({"enabled": False, "error": "status failure"}),
        )
        for output in outputs:
            with self.subTest(output=output):
                self.env["ENTIRE_OUTPUT"] = output
                self.assert_blocked(self.hook())
        self.assertEqual(self.records(self.gh_log), [])

    def test_failed_entire_cli_blocks_even_with_valid_output(self):
        self.configure_entire()
        self.local_hook()
        self.env["ENTIRE_EXIT"] = "17"
        self.assert_blocked(self.hook())
        self.assertEqual(self.records(self.gh_log), [])

    def test_enabled_wrong_or_fallback_route_blocks(self):
        self.configure_entire()
        self.local_hook()
        statuses = (
            {"enabled": True},
            self.enabled_status(checkpoint_sync_remote="sweepies/source"),
            self.enabled_status(checkpoint_sync_remote="origin"),
            self.enabled_status(checkpoint_sync_remote_source="fallback"),
            self.enabled_status(checkpoint_sync_remote_source="default"),
            self.enabled_status(checkpoint_sync_remote_source=None),
        )
        for status in statuses:
            with self.subTest(status=status):
                self.env["ENTIRE_OUTPUT"] = json.dumps(status)
                self.assert_blocked(self.hook())
        self.assertEqual(self.records(self.gh_log), [])

    def test_gh_errors_public_and_malformed_privacy_block(self):
        self.configure_entire()
        self.local_hook()
        for output, code in (("false\n", "0"), ("", "0"), ("null\n", "0"),
                             ('"true"\n', "0"), ("true\n", "9")):
            with self.subTest(output=output, code=code):
                self.env.update(GH_OUTPUT=output, GH_EXIT=code)
                self.assert_blocked(self.hook())
        self.assertEqual(len(self.records(self.gh_log)), 5)

    def test_protected_local_or_remote_refs_are_denied_for_source_remote(self):
        self.local_hook()
        protected = ("refs/entire/checkpoints", "refs/heads/entire/checkpoints",
                     "refs/entire/deep/nested", "refs/heads/entire/deep/nested")
        for ref in protected:
            for local_field in (True, False):
                with self.subTest(ref=ref, local_field=local_field):
                    row = self.push_row(local=ref) if local_field else self.push_row(remote=ref)
                    self.assert_blocked(self.hook(stdin=row))

    def test_protected_deletions_are_allowed(self):
        self.local_hook()
        for ref in ("refs/entire/checkpoints", "refs/heads/entire/checkpoints"):
            with self.subTest(ref=ref):
                result = self.hook(stdin=self.push_row("(delete)", ref, ZERO))
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(self.records(self.gh_log), [])

    def test_similarly_named_ordinary_refs_are_not_protected(self):
        self.local_hook()
        for ref in ("refs/heads/entirely", "refs/heads/feature/entire/topic"):
            with self.subTest(ref=ref):
                result = self.hook(stdin=self.push_row(ref, ref))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_canonical_checkpoint_ssh_and_https_targets_are_approved(self):
        self.local_hook()
        urls = (
            "git@github.com:sweepies/entire-checkpoints.git",
            "ssh://git@github.com/sweepies/entire-checkpoints.git",
            "https://github.com/sweepies/entire-checkpoints.git",
            "https://github.com/sweepies/entire-checkpoints",
        )
        for url in urls:
            with self.subTest(url=url):
                result = self.hook(args=["checkpoints", url],
                    stdin=self.push_row("refs/entire/checkpoints", "refs/entire/checkpoints"))
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.records()), len(urls))

    def test_lookalike_checkpoint_urls_are_denied(self):
        self.local_hook()
        urls = (
            "https://github.com/sweepies/source.git",
            "git@github.com:someone/entire-checkpoints.git",
            "https://github.com.evil.invalid/sweepies/entire-checkpoints.git",
            "https://github.com/sweepies/entire-checkpoints.git/extra",
            "https://github.com/sweepies/entire-checkpoints-evil.git",
            "https://github.com/sweepies/entire-checkpoints.git?other=1",
            "https://github.com/sweepies/entire-checkpoints.git#fragment",
            "file:///sweepies/entire-checkpoints.git",
            str(self.root / "entire-checkpoints.git"),
        )
        for url in urls:
            with self.subTest(url=url):
                self.assert_blocked(self.hook(args=["origin", url],
                    stdin=self.push_row("refs/entire/checkpoints", "refs/entire/checkpoints")))

    def test_actual_git_push_allows_source_and_blocks_protected_transfer(self):
        self.configure_entire()
        self.local_hook()
        bare = self.root / "source-remote.git"
        self.run_git("init", "--bare", str(bare), cwd=self.root)
        self.run_git("remote", "set-url", "origin", str(bare))
        self.run_git("push", "origin", "HEAD:refs/heads/main")
        self.assertEqual(self.run_git("rev-parse", "refs/heads/main", cwd=bare).stdout.strip(), self.oid)
        records = self.records()
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]["privacy_checked"])
        self.assertIn("refs/heads/main", records[0]["stdin"])
        self.log.unlink()
        (self.repo / "source.txt").write_text("not transferred\n")
        self.run_git("add", "source.txt")
        self.run_git("commit", "-m", "must not reach remote")
        blocked_oid = self.run_git("rev-parse", "HEAD").stdout.strip()
        self.run_git("update-ref", "refs/entire/checkpoints", blocked_oid)
        for refspec in ("refs/entire/checkpoints:refs/entire/checkpoints",
                        "HEAD:refs/heads/entire/checkpoints"):
            with self.subTest(refspec=refspec):
                result = self.run_git("push", "origin", refspec, check=False)
                self.assert_blocked(result)
                refs = self.run_git("for-each-ref", "--format=%(refname)", cwd=bare).stdout
                self.assertEqual(refs.strip(), "refs/heads/main")
                self.assertNotEqual(
                    self.run_git("cat-file", "-e", blocked_oid, cwd=bare, check=False).returncode,
                    0, "blocked push must not transfer the new commit object")

    def test_actual_push_uses_effective_instead_of_and_push_instead_of_url(self):
        self.local_hook()
        bare = self.root / "rewritten-remote.git"
        self.run_git("init", "--bare", str(bare), cwd=self.root)
        canonical = "https://github.com/sweepies/entire-checkpoints.git"
        for rewrite in ("insteadOf", "pushInsteadOf"):
            with self.subTest(rewrite=rewrite):
                key = f"url.{bare}.{rewrite}"
                self.run_git("config", key, canonical)
                # Git supplies the rewritten, actual destination to pre-push.
                # A canonical-looking configured URL must not bless a local target.
                result = self.run_git("push", canonical, "HEAD:refs/entire/checkpoints", check=False)
                self.assert_blocked(result)
                self.assertEqual(self.run_git("for-each-ref", cwd=bare).stdout, "")
                self.run_git("config", "--unset", key)


if __name__ == "__main__":
    unittest.main()
