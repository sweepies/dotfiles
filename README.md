# Dotfiles

Personal development configuration managed with
[mise's native dotfiles and bootstrap](https://mise.jdx.dev/dotfiles.html).
Requires **mise 2026.10.3 or newer**.

## Overview

- **`mise.toml`** — shared development tools and Git, fnox, Pi, and
  billion-context configuration, plus local T3 prompt-cleanup and tool-discovery
  extensions.
- **`mise.macos.toml`** — Mac-only interactive tools, Fish setup, aliases,
  and the Secure Enclave age plugin.
- **`.miserc.toml`** — automatically selects the Mac overlay on macOS.
  Linux uses only the shared configuration; the host manages its shell and PATH.

Dotfiles are linked from `~/dotfiles`. Managed groups include only Git-indexed
files and leave neighboring machine-local state alone.

## Getting started

Install mise and Git, then:

```sh
git clone https://github.com/sweepies/dotfiles.git "$HOME/dotfiles"
cd "$HOME/dotfiles"
mise trust
mise bootstrap --dry-run
```

Review the preview and resolve existing-file conflicts before applying.
On macOS, install Fish and GNU coreutils first, then apply activation before
full bootstrap:

```sh
mise bootstrap mise-shell-activate apply --yes
mise bootstrap --yes
```

On Linux, run `mise bootstrap --yes`. Without shell activation, use
`mise exec -- <command>` or the host's existing mise shims.

To preview or apply dotfile changes without installing tools:

```sh
mise dot apply --dry-run
mise dot apply --yes
```

## Machine-local Git configuration

Shared Git defaults are linked to `~/.config/git/config`, Git's XDG global
file. `~/.gitconfig` is a regular per-machine file: Git reads it after the XDG
file, so its values win, and `git config --global` and `gh auth setup-git`
write there instead of into this checkout. The post-dotfiles hook creates it
when missing and replaces the old `~/.gitconfig` symlink. Sign in per machine
as usual with `gh auth login` and `gh auth setup-git`; never commit that state.

## Pi / T3 prompt cleanup

The global Pi extension at `~/.pi/agent/extensions/t3-prompt-cleanup.ts` removes
T3's duplicate tool-catalog snippets and exact generic routing rules. It leaves
callable tools, descriptions, parameter schemas, permission handling, meaningful
tool guidance, and orchestration instructions intact. Other tools and conversation
messages are unaffected. This reduces repeated prompt text, not the tool-schema
payload or the shared cross-harness instructions.

The extension first edits Pi's structured prompt options, then handles T3's
forced-prompt override through the final `context_with_system` hook. Its source
is `.pi/agent/extensions/t3-prompt-cleanup/index.ts`; deployment is a mise-managed
symlink. Apply it with `mise dot apply --yes` and open a fresh T3 thread or reload
Pi. Run its regression tests with `mise run test:pi-prompt-cleanup`.

To disable it without uninstalling, add
`"extensions": ["-~/.pi/agent/extensions/t3-prompt-cleanup.ts"]` to Pi's settings
(merge with any existing extension entries), then start a fresh session or reload.

This is a temporary workaround for
[pingdotgg/t3code#16651](https://github.com/pingdotgg/t3code/issues/16651).
Remove it once the upstream fix is included in the installed T3 release. Recheck
fresh-session prompt duplication and T3 tool availability before removal.

## Pi / T3 on-demand tools

The companion extension at `~/.pi/agent/extensions/t3-tool-discovery` reduces
T3's initially declared tool schemas. It keeps `orchestrator_capabilities`,
`delegate_task`, `task_status`, and `task_cancel` active and adds `t3_tools` to
find and activate the remaining T3 tools. All non-T3 active tools are preserved.

For example, `t3_tools({"query":"browser screenshot"})` searches live T3 tool
names and descriptions and activates up to five matches. To load a known tool,
use `t3_tools({"names":["preview_snapshot"]})`. Then call that tool directly
with its original parameters. Discovery executes no T3 operation and never
re-registers tools, rewrites schemas, or bypasses T3's permission hook. Restricted
runtime modes can require approval for discovery itself as well as the loaded
operation.

Loaded tools accumulate for the current session branch and survive resume/reload;
returning to an earlier branch restores that branch's selection. This avoids
unloading/reloading schemas every turn, though each new activation changes the
tool prefix and can affect prompt caching. Keep the prompt-cleanup extension too:
T3's forced prompt otherwise repeats tool descriptions. Shared orchestration and
workspace instructions remain unchanged.

Source: `.pi/agent/extensions/t3-tool-discovery/index.ts` and
`.pi/agent/extensions/t3-tool-discovery/discovery.ts`. Deployment uses a
mise-managed directory symlink so Pi can resolve the adjacent helper. Apply with
`mise dot apply --yes`, then
open a fresh T3 session or reload Pi. Run `mise run test:pi-tool-discovery` for
unit tests and a deterministic integration probe using the installed Pi CLI and
T3 bridge. It uses a local fake MCP server, no LLM requests, and no real server
credentials. Bridge integration tests skip when the generated bridge is absent;
set `T3_PI_BRIDGE_PATH` or `PI_DISCOVERY_CLI` to use non-default installations.

To restore eager T3 tool declarations, exclude the extension in Pi settings:
`"extensions": ["-~/.pi/agent/extensions/t3-tool-discovery"]`
(merge with existing entries), then start a fresh session or reload.

## Private session checkpoints

Entire checkpoints belong in the private `sweepies/entire-checkpoints`
repository, never the public code repository. For an already-enabled clone:

```sh
mise run entire:checkpoints
```

This saves routing in gitignored `.entire/settings.local.json`. New clones of
these dotfiles have automatic checkpoint uploads disabled by default; the owner
can enable them locally after configuring the private destination. The private
route still needs local enrollment; **the guard does not**. This does not relocate
existing published sessions.

### Global Git hook guard

Shared `.gitconfig` (linked as `~/.config/git/config`) sets
`core.hooksPath = ~/.config/git/hooks`. One native mise
apply activates the guard for all existing and future repositories on that
machine, without installing a guard in each clone:

```sh
mise dot apply "$HOME/.config/git/hooks" "$HOME/.config/git/config" --yes
mise run git:hooks:audit
mise run test:git-hooks
```

The pre-push guard runs before repository-local hooks or Entire's automatic
checkpoint sync. Enabled Entire repos must report the dedicated
`sweepies/entire-checkpoints` route; `gh api` must confirm that repository is
private on github.com. The approved route must be explicitly enrolled in regular,
untracked `.entire/settings.local.json`, absent from both index and HEAD. A
project-inherited route can look dedicated in status but fall back for a different
push remote, so it does not establish local consent. Enabled Entire must push
through a configured remote name, not a bare URL. Missing authentication,
malformed configuration, public visibility, fallback routing, and unsafe Git URL
rewrites fail closed. Retained native Entire hooks remain guarded even if their
settings files were deleted. Ordinary repos without Entire do not need Entire or
GitHub authentication to push code.

Outgoing `refs/entire/*` and `refs/heads/entire/*` refs are blocked unless the
actual destination is the approved private checkpoint repo, including renamed
refspecs and Git URL rewrites. Checkpoint deletions remain allowed. This protects
known checkpoint namespaces; it is not a content/secret scanner and cannot
identify deliberately renamed checkpoint objects. Git contacts the remote for
ref discovery before pre-push runs; rejection prevents object/ref transfer, not
the initial connection.

All documented Git hook events dispatch to existing executable hooks in the
Git common directory, preserving arguments, stdin, working directory and exit
status, including linked worktrees. Entire's five Git events also have native
handler fallbacks when the repo has no local hook; existing local Entire hooks
are never invoked twice. Entire's effective provider must be **GitHub**, not
merely a matching repo slug on another forge. Automatic uploads also validate
push-only URL rewrites and the source remote's derived host. Enterprise hosts,
nondefault ports and `entire://` mirrors are refused until they can be verified
as the approved public github.com destination.

Entire 0.11.4 refuses to install through the managed hooks-directory symlink.
The regular compatibility entrypoints satisfy its hook detection, and native
mise hooks make the shared source directory read-only to prevent its uninstall
from deleting the guard. Run lifecycle operations through the scoped task so
Entire edits only the repository's own hooks:

```sh
mise run entire:cli -- enable --local --agent pi --skip-initial-commit \
  --checkpoint-remote github:sweepies/entire-checkpoints
mise run entire:cli -- configure --force
mise run entire:cli -- disable --uninstall --force
```

Remote-agent provisioning scopes its native repository updater's temporary
unlock with a cleanup trap that restores protection on success or failure.
Standalone `mise bootstrap repos update` commands do **not** run bootstrap
phase hooks. Before a **manual** dotfiles pull/edit or standalone update, run
`chmod u+w "$HOME/dotfiles/.config/git/hooks"`; afterward run `mise dot apply
--yes` to protect it again. Recheck compatibility when upgrading Entire.

The audit runs after bootstrap tool installation and reports local/worktree
`core.hooksPath` overrides, including included files, without changing them. It
also checks each repo's effective path across all config scopes, including
conditional global includes and command-scope overrides. By default it scans home,
excluding dependency/cache trees and symlinked directories; pass other roots
with `mise run git:hooks:audit -- /path/to/repos`. Husky/custom hook-path overrides
must be reconciled explicitly, because they supersede the global guard.

This is a default-workflow safeguard, not a security boundary: `--no-verify`,
command-line/local hook-path overrides, removing the configuration, or direct
Entire uploads can bypass Git's pre-push hook. No credentials or session data
are stored in the shared hook files.

## Secrets and signing

Committed fnox configuration contains 1Password references, not credentials.
Each machine keeps its own untracked fnox config, age identity, and encrypted
caches. Remote machines use their own ordinary age identity, not a Mac Secure
Enclave identity; do not export `FNOX_AGE_KEY`.

Git uses SSH commit signing with a separately provisioned machine-local key at
`~/.ssh/git-signing`. Bootstrap does not create or deploy private keys, secret
caches, or authentication tokens.
