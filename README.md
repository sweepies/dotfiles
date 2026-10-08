# Dotfiles

Personal development configuration managed with
[mise's native dotfiles and bootstrap](https://mise.jdx.dev/dotfiles.html).
Requires **mise 2026.10.3 or newer**.

## Overview

- **`mise.toml`** — shared development tools and Git, fnox, Pi, and
  billion-context configuration, plus the local T3 prompt-cleanup extension.
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

## Private session checkpoints

Entire checkpoints belong in the private `sweepies/entire-checkpoints`
repository, never the public code repository. For an already-enabled clone:

```sh
mise run entire:checkpoints
```

This saves routing in gitignored `.entire/settings.local.json`. New clones of
these dotfiles have automatic checkpoint uploads disabled by default; the owner
can enable them locally after configuring the private destination. Each machine
and clone needs its own setup. This does not relocate existing published sessions.

## Secrets and signing

Committed fnox configuration contains 1Password references, not credentials.
Each machine keeps its own untracked fnox config, age identity, and encrypted
caches. Remote machines use their own ordinary age identity, not a Mac Secure
Enclave identity; do not export `FNOX_AGE_KEY`.

Git uses SSH commit signing with a separately provisioned machine-local key at
`~/.ssh/git-signing`. Bootstrap does not create or deploy private keys, secret
caches, or authentication tokens.
