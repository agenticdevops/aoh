---
name: author-and-promote-skill
description: Use when you've drafted or improved a skill locally and want to publish it to a shared pack — walks through validating the draft, finding the target pack, running the promote script, and reviewing the staged diff before it ships.
---

# Author and Promote a Skill

Draft a skill locally, then promote it into a shared, git-hosted AOH pack using
`aoh skill promote` (this pack ships a thin wrapper around it — see
`scripts/promote.sh`). AOH never executes your skill or the promote itself in
some hidden way — running the CLI from your own shell, with your own
credentials, is the whole mechanism.

## Process

1. **Confirm the draft validates standalone.** Before promoting, check:
   - The skill lives in a directory whose name matches the `name:` field in its
     `SKILL.md` frontmatter (e.g. `skills/my-skill/SKILL.md` has
     `name: my-skill`).
   - The frontmatter has both `name` and a non-empty `description`.
   - Any scripts under `scripts/` are executable (`ls -l scripts/` should show
     `x` bits; if not, `chmod +x scripts/*.sh`).

2. **Identify the target pack.** Promote publishes into a pack you've already
   configured by name in `~/.aoh/config.yaml`. Read the file directly, or ask
   for one pack's entry with:

   ```
   aoh config get packs.<pack-name>
   ```

   This resolves the nested `packs.<pack-name>` key from the config's
   `packs: {<name>: {repo: ...}}` structure and prints that pack's
   configuration (e.g. its `repo` URL). If it prints `(unset)`, the pack isn't
   configured yet — set it first with
   `aoh config set packs.<pack-name> <repo-url>` (promote requires a
   git-hosted pack; a `local_path`-only entry will be rejected).

3. **Run the promote script.**

   ```
   scripts/promote.sh <skill-name> --pack <pack-name>
   ```

   Add `--from <draft-dir>` if the draft isn't discoverable from the current
   directory's `.claude/skills/<name>` or `.agents/skills/<name>`. Add `--pr`
   to open a pull request instead of committing directly to the pack's
   default branch.

4. **Read the staged diff before it's pushed.** The command prints the staged
   diff (`git diff --cached`) from inside a throwaway worktree before it
   announces success. Stop and ask the user if anything in that diff looks
   unexpected — an unrelated file, a change outside the new skill's directory,
   or content that shouldn't be shared.

   **AOH does not intentionally manage secrets — review the staged diff
   yourself before this proceeds.**

5. **Report the result.** The final line tells you what happened:
   - `promoted <name> to <pack> @ <sha>` — committed directly; report the sha.
   - `opened PR: <pr_url>` — report the PR link.
   - `<name> already up to date in <pack> @ <sha> (no-op)` — nothing changed;
     say so, don't claim a new promotion happened.

   If promote fails instead (`promote failed: ...`), report the exact message
   — common cases are an unconfigured pack name, a pack configured as a local
   path, a validation failure in the draft, or the upstream branch having
   moved since the promotion started (re-run with `--pr` in that case).
