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
- **`mise.linux.toml`** — Linux dev-box bash activation, the 1Password CLI,
  and the `secrets:init` / `secrets:sync` tasks.
- **`.miserc.toml`** — automatically selects the platform overlay.

Dotfiles are linked from `~/dotfiles`. Managed groups include only Git-indexed
files and leave neighboring machine-local state alone.

## Getting started

Install mise and Git, then clone to `~/dotfiles`. Every dotfile source points
there, so don't use `mise bootstrap --adopt`: it clones into `~/.config/mise`.

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

### New Linux box

Install mise, Git, and `ssh-keygen` (Debian/Ubuntu: `openssh-client`). Clone
as above, then:

```sh
mise bootstrap --yes
exec bash -l            # pick up mise activation
mise run secrets:init   # prompts for a 1Password service account token
gh auth login
gh auth setup-git
```

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

## Secrets and signing

Committed fnox configuration contains 1Password references, not credentials.
Each machine keeps its own untracked fnox config, age identity, and encrypted
caches. Linux boxes use their own ordinary age identity, not a Mac Secure
Enclave identity; do not export `FNOX_AGE_KEY`.

Git uses SSH commit signing with a separately provisioned machine-local key at
`~/.ssh/git-signing`. Bootstrap does not create or deploy private keys, secret
caches, or authentication tokens.

On Linux, `mise run secrets:init` handles this once per box:

- creates `~/.config/fnox/age.txt` and a machine-local
  `~/.config/fnox/config.toml` that imports `shared.toml` and adds the
  `sync-age` provider;
- prompts for a 1Password service account token with read access to the `dev`
  vault and stores it age-encrypted in the `op-auth` profile;
- runs `secrets:sync`.

`mise run secrets:sync` exposes the token only to fnox's sync commands, refreshes
the age-encrypted caches of the shared 1Password secrets, and writes
`~/.ssh/git-signing` when it is missing. Re-run it after adding or rotating
secrets in 1Password. To replace the signing key, delete it first. Each step is
skipped if already done, so both tasks are safe to re-run. Give each box its own
service account so you can revoke it independently.
