# `aoh skill promote` — draft local, publish central

`aoh skill promote <name> [--from <dir>] --pack <pack-name> [--pr]` takes a skill
you drafted locally (in any Claude Code or Codex session) and lands it in a
shared, git-hosted AOH pack — a hardened git write-path, not a plain `git push`.
This doc is grounded directly in the shipped implementation:
`src/aoh/promote.py`, `src/aoh/gitops.py`, `src/aoh/skillcopy.py`, and
`src/aoh/cli.py`'s `_cmd_skill_promote`. If this doc and the code ever disagree,
the code wins.

## The flow

```
discover draft -> ensure mirror -> fetch default branch -> create worktree
  -> repoint worktree's origin at the real repo -> check git identity
  -> copy skill tree (hygiene-filtered) -> load + validate pack (in worktree)
  -> stage diff, show it -> commit
  -> [direct] fast-forward push to the real repo
  -> [--pr]   feature branch push + gh pr create
  -> remove worktree (always, even on failure)
```

1. **Discover the draft.** `discover_skill_source(name, from_dir, cwd)`: if
   `--from <dir>` is given, that directory must contain `SKILL.md` or promote
   refuses. Otherwise it searches upward from the current directory, checking
   `.claude/skills/<name>/SKILL.md` before `.agents/skills/<name>/SKILL.md` at
   *every* directory level, before ascending to the parent — so a project's own
   `.claude/skills` wins over a parent directory's `.agents/skills` at the same
   depth, and the search never mixes levels. If neither is found by the
   filesystem root, `PromoteError` names both paths it tried.

2. **Resolve the pack.** `--pack <name>` must resolve to an entry in
   `~/.aoh/config.yaml`'s `packs:` map with a `repo` URL — promote only ever
   targets a git-hosted pack. A `local_path`-only pack entry is rejected
   (`PromoteError`); an unconfigured name is rejected before `promote_skill`
   is even called (CLI prints the exact `aoh config set packs.<name> <repo-url>`
   fix).

3. **Ensure the mirror, then fetch fresh.** `gitops.ensure_mirror` gets (or
   updates) a bare `--mirror` clone of the pack's repo, keyed by a hash of its
   URL under `$AOH_HOME/cache`, serialized by an adjacent `.lock` file.
   `gitops.fetch_default_branch(mirror)` is then called — **every single
   promote, no exceptions** — and re-fetches (`git remote update --prune`)
   before resolving the default branch, re-deriving `origin/HEAD` fresh rather
   than trusting whatever it was set to at clone time (a `--mirror` clone sets
   `origin/HEAD` once; `remote update` does not refresh it). This is the basis
   of the conflict model below.

4. **Cut a throwaway worktree.** `gitops.create_worktree(mirror, branch,
   worktrees_dir)` creates a brand-new directory (name includes a uuid, never
   reused) and checks out the default branch into it via `git worktree add`.
   The worktree's `origin` remote — inherited from the mirror's `--mirror`
   clone config — is then repointed at the pack's *real* remote URL
   (`gitops.set_remote_url`), once, immediately after creation. From this
   point every push from this worktree goes to the real repo, never back to
   the mirror.

5. **Verify git identity.** `gitops.check_identity(worktree)` checks that
   `user.name` and `user.email` resolve (worktree-local or global config)
   *before* anything is copied or committed — fails fast with a clear error
   naming which key is missing.

6. **Copy the skill tree through the hygiene filter.** The draft is copied to
   `skills/<name>/` inside the worktree via `skillcopy.copy_skill_tree` — see
   [Hygiene rules](#hygiene-rules) below. If the destination already exists
   (re-promoting the same skill), it's removed first — safe, because the
   worktree is throwaway and gets deleted regardless of outcome.

7. **Validate the whole pack, in the worktree.** `load_pack` + `validate_pack`
   run against the worktree root — the same referential-integrity validation
   `aoh validate` runs, not a narrower "does the skill look okay" check. A
   validation failure (e.g. the draft's `SKILL.md` frontmatter `name` doesn't
   match its directory name) raises before anything is staged or committed —
   the real repo's `HEAD` is left untouched.

8. **Stage the diff and show it.** `gitops.staged_diff(worktree)` runs
   `git add -A` then `git diff --cached` and returns the text. The CLI prints
   this **before** announcing success or pushing anything — the design intent
   is that a human reads it and can still object, even though nothing here
   currently pauses for confirmation.

9. **Commit — or detect a no-op.** `gitops.commit_all(worktree, message)`
   commits with message `feat(skill): add <name> (promoted from local draft)`.
   If the skill tree is byte-identical to what's already on the target branch,
   git itself refuses with "nothing to commit"; `promote_skill` catches that
   specific case and returns `PromoteResult(status="noop", sha=<current HEAD>,
   staged_diff="")` rather than erroring or creating a duplicate commit.

10. **Push.**
    - **Direct commit (default):** `gitops.push_fast_forward(mirror, worktree,
      branch)` pushes to the real repo (via the repointed `origin`),
      fast-forward-only. See [Conflict model](#conflict-model) for what
      happens on rejection. On success, `push_branch` is also called to make
      sure the real remote (not just the mirror's view) has advanced.
    - **`--pr`:** a feature branch `skill/<name>` is created
      (`gitops.create_branch`), pushed to the real repo by URL
      (`gitops.push_branch`), and `gitops.open_pr` shells out to
      `gh pr create --repo <repo> --head <branch> --base <default> --title ...
      --body ... --json url -q .url`. The `--pr` path can never hit the
      fast-forward conflict case — it always creates a new branch.

11. **Clean up, always.** `gitops.remove_worktree(mirror, worktree)` runs in a
    `finally` block — the worktree is removed whether promote succeeded or
    raised. Cleanup itself is best-effort and never raises, so it can't mask
    whatever error caused it to run.

## Hygiene rules

`skillcopy.copy_skill_tree(src, dest)` walks the draft directory in a single
pre-scan pass **before copying anything**, so any violation leaves `dest`
completely untouched — no partial copy:

- a directory named `.git` anywhere in the tree → refused
- a symlink anywhere (file or directory) → refused
- a device, socket, or fifo → refused
- a regular file over `MAX_FILE_BYTES` (10 MiB) → refused
- more than `MAX_FILE_COUNT` (500) files total → refused
- total tree size over `MAX_TOTAL_BYTES` (50 MiB) → refused

Everything else is copied with `shutil.copy2` (preserves mode, including the
executable bit on scripts) into destination paths validated through
`paths.safe_join` — defense in depth even though the source walk isn't
attacker-controlled globbing.

None of this is a secrets scanner. **AOH does not intentionally manage
secrets** — the staged diff shown in step 8 is the actual review point; nothing
in this pipeline claims to detect a credential accidentally left in a draft
file.

## Conflict model

There is no persisted "last known base" for a skill across promote runs.
Instead, conflict detection is structural: `fetch_default_branch` is called
fresh at the *start* of every promote, the worktree is cut from that exact
tip, and the fast-forward push in step 10 only succeeds if the real repo's
default branch is **still at that tip** when the push happens. If someone else
promoted (or pushed) in between, `push_fast_forward` fails with a
non-fast-forward rejection, and `promote_skill` turns that specific failure
into:

> `upstream has moved since this promotion started — re-run with --pr`

Promote never auto-retries and never force-pushes. This is a deliberate
design choice (recorded in `.planning/PROJECT.md`, 2026-07-19): a persisted
cross-session base ledger would be more moving parts for no real benefit at
single-operator scale — the fresh-fetch-then-fast-forward-push sequence gives
the same guarantee (nobody else changed the target branch underneath you)
without storing anything. A stored multi-skill base ledger is deferred to a
later phase if concurrent multi-operator promotion turns out to need it.

## Operator-facing note: the URL-not-name push gotcha

If you extend `gitops.py` with a new push path, this is worth knowing before
you hit it the hard way: a worktree created from a `--mirror` clone inherits
an `origin` remote with `remote.origin.mirror = true` in its git config. That
setting forbids pushing an explicit refspec (`branch:branch`) through that
remote **by name** — it errors even after `set_remote_url` has repointed
`origin`'s URL at the real repo, because the `mirror` flag on that remote
entry is still set.

Two ways around it, both already used in this codebase:

- **Override the flag inline, per push**, when you deliberately want to push
  to the mirror's own `origin` name — `push_fast_forward` does this:
  `git -c remote.origin.mirror=false push origin <branch>:<branch>`.
- **Push by URL, not by remote name**, when the target is the real repo —
  `push_branch(worktree, remote_url, local_branch, remote_branch)` always
  takes an explicit URL argument rather than assuming `origin` is safe to use
  by name, even though `origin`'s URL has already been repointed at that same
  real repo via `set_remote_url`.

If a future change pushes through the worktree's `origin` **by name** without
either of these, expect a confusing rejection that looks like a permissions
or fast-forward problem but is actually the inherited mirror flag.

## See also

- `docs/spec.md` — Commands section, one-paragraph summary
- `docs/demos/promote-validation-2026-07-19.md` — live proof against a real,
  throwaway GitHub repo (direct commit, no-op, `--pr`)
- `collections/core/aoh-authoring/skills/author-and-promote-skill/SKILL.md` —
  the agent-facing process that wraps this command
- docs-site: [Authoring & Promoting a
  Skill](https://agenticdevops.github.io/aoh/tutorials/authoring-and-promoting) —
  worked tutorial, and `docs/reference/cli.md` for the full flag table
