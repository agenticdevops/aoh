# v0.3 Phase B — Authoring/Promote Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `aoh skill promote <name> [--from dir] --pack <name> [--pr]` — draft a skill locally (in any Claude/Codex session), promote it into an org pack repo via a hardened git write-path (bare-mirror → fresh temp worktree → validate → commit → fast-forward push or PR). Plus `collections/core/aoh-authoring`, the skill pack that teaches an agent to draft + invoke promote from wherever it's working.

**Architecture:** Design (authoritative — Phase B section + Git-cache-discipline/Secrets-language decision rows): `.planning/design/2026-07-17-v03-fleet-lifecycle-design.md`. Extends `src/aoh/gitops.py` (read-only in Phase A) with WRITE operations: `fetch_default_branch`, `create_worktree`, `commit_in_worktree`, `push_fast_forward`. New `src/aoh/promote.py` (orchestration: discover draft → copy-hygiene → worktree → validate → commit → push/PR). New `src/aoh/skillcopy.py` (the hygiene-filtered copy, reused later by capture in Phase D). New pack `collections/core/aoh-authoring`. CLI gains `aoh skill promote`.

**Tech Stack:** Python 3 + uv, pytest, git CLI (subprocess), `gh` CLI (subprocess, PR path only).

## Global Constraints

- Tests: `rtk proxy uv run pytest -q`; baseline 309 green (Phase A + its final-review fix). NO network in tests — local bare repos only (same pattern as `tests/test_gitops.py`).
- Engine-neutral: `promote.py`/`skillcopy.py` import stdlib + `aoh.pack`/`aoh.paths`/`aoh.gitops`/`aoh.site` only — no adapter/k8s modules.
- Reuse Phase A's `_locked` fcntl pattern (adjacent `.lock`, fd held whole section, `finally`-released) for every new mirror-touching operation. Reuse `paths.safe_join`/`safe_segment` for all path validation — no raw joins of untrusted data (this is exactly the class of bug the Phase A final review caught).
- Design-binding rules (Phase B + decision rows, verbatim):
  - Copy hygiene: regular files only; reject `.git`, symlinks, devices, sockets, path escapes, oversized files; staged diff shown before direct push.
  - Secrets language: "AOH does not intentionally manage secrets" — never claim scanning is complete.
  - Git flow: bare mirror + per-repo lock + fresh temp worktree cut from a **freshly-fetched** default branch + fast-forward-only push; same-skill-upstream-change-since-base → abort with a `--pr` suggestion; identical re-promote → successful no-op printing existing sha; `user.name`/`user.email` verified before commit.
  - Direct-commit default; `--pr` opt-in (branch + `gh pr create`).
  - Full pack validation runs in the worktree **before** commit.
- `gh` is installed and authenticated in this environment (verified: account `initcron`) — the `--pr` path can be exercised live in Task 6 against a throwaway scratch repo, never against the real org pack repo.
- Commit trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: gitops.py — write primitives (fetch, worktree, commit, FF-push)

**Files:** Modify `src/aoh/gitops.py`; Test `tests/test_gitops.py` (extend).

**Interfaces (produced — Task 2 consumes exactly these):**
```python
# gitops.py additions
def fetch_default_branch(mirror: Path) -> tuple[str, str]:
    """Fetch the mirror's remote, return (branch_name, tip_commit_sha) for the
    repo's default branch (origin/HEAD symbolic-ref, falling back to `main`
    then `master` if origin/HEAD is unset — a bare --mirror clone always sets
    origin/HEAD from the remote's default at clone time, but `remote update`
    does not refresh it, so re-resolve via `git symbolic-ref refs/remotes/origin/HEAD`
    and re-derive if that's stale/absent). Runs under the mirror's existing lock."""

def create_worktree(mirror: Path, branch: str, worktrees_dir: Path) -> Path:
    """`git worktree add <fresh-dir> <branch>` cut from `mirror`, into a
    freshly-created dir under `worktrees_dir` (name includes a uuid — never
    reused). Returns the worktree path. Caller owns cleanup via `remove_worktree`."""

def remove_worktree(mirror: Path, worktree: Path) -> None:
    """`git worktree remove --force <worktree>` then `git worktree prune`,
    best-effort (never raises — logs via GitOpsError message if it fails, but
    swallows so cleanup-on-error paths never mask the original error)."""

def check_identity(worktree: Path) -> None:
    """Verify `git config user.name` and `user.email` resolve (worktree or
    global config) — raise GitOpsError naming which is missing, before any
    commit is attempted."""

def commit_all(worktree: Path, message: str) -> str:
    """`git add -A` + `git commit -m <message>` in the worktree; returns the
    new commit sha. Raises GitOpsError if there is nothing to commit (identical
    re-promote path uses this to detect no-op — see promote.py)."""

def push_fast_forward(mirror: Path, worktree: Path, branch: str) -> None:
    """Push `worktree`'s branch to `mirror`'s `origin` remote, fast-forward
    only (`git push --force-with-lease=<branch> ...` is NOT used — plain
    `git push origin <branch>` from the worktree remote config, which is
    already non-FF-safe by default; on rejection raise GitOpsError with the
    real git stderr, distinguishing a non-fast-forward rejection (message
    contains "non-fast-forward" or "fetch first") from other failures so the
    caller can map it to the "abort with --pr suggestion" UX)."""

def push_branch(worktree: Path, remote_url: str, local_branch: str, remote_branch: str) -> None:
    """Push `local_branch` to `remote_url` as `remote_branch` (creates it) —
    used by the --pr path to push a feature branch DIRECTLY to the real
    origin (not the mirror), since `gh pr create` needs the branch on the
    actual remote. Fails loudly (GitOpsError) on any rejection — no force."""
```
- All git subprocess calls go through the existing `_git()` helper (stderr captured into `GitOpsError`).
- `fetch_default_branch` and `create_worktree` both run under `_locked(mirror's .lock)` — reuse the exact lock-path convention from `ensure_mirror`/`source_checkout` (`mirror.parent / (mirror.name + ".lock")`).

- [ ] **Step 1 RED** — extend `tests/test_gitops.py` with a new fixture (bare `origin.git` seeded via a temp work clone, one commit on `main`, a second remote-tracking clone to simulate "someone else pushed"). Tests: `fetch_default_branch` returns `("main", <tip sha>)`; after a second commit lands on `main` via the tracking clone + push, `fetch_default_branch` again returns the NEW tip (proves it re-fetches, doesn't cache); `create_worktree` produces an isolated dir with the branch checked out, two calls produce two DIFFERENT dirs; `remove_worktree` cleans up and a subsequent `git worktree list` in the mirror doesn't list it; `check_identity` raises GitOpsError when `user.name`/`user.email` are unset in a worktree with no global config (use `GIT_CONFIG_GLOBAL=/dev/null` env override in the test to sandbox global config) and passes when set via worktree-local `git config user.name ...`; `commit_all` creates a commit and returns its sha, raises GitOpsError on an empty worktree with no changes; `push_fast_forward` succeeds on a fast-forward case and raises GitOpsError (message mentions non-fast-forward) when the mirror's origin has diverged (push a conflicting commit via the tracking clone first); `push_branch` creates a new branch on the real (non-mirror) origin.
- [ ] **Step 2 GREEN**; suite green (~309 + ~10). **Step 3** commit `feat: gitops write primitives — fetch, worktree, identity check, FF push (v0.3 B1)`.

---

### Task 2: skillcopy.py — hygiene-filtered copy

**Files:** Create `src/aoh/skillcopy.py`; Test `tests/test_skillcopy.py`.

**Interfaces:**
```python
MAX_FILE_BYTES = 10 * 1024 * 1024       # 10 MiB per file
MAX_TOTAL_BYTES = 50 * 1024 * 1024      # 50 MiB per skill
MAX_FILE_COUNT = 500

class SkillCopyError(ValueError): ...

def copy_skill_tree(src: Path, dest: Path) -> list[str]:
    """Copy `src` (a skill directory) onto `dest` (must not already exist),
    walking `src` and for EVERY entry:
      - directory named `.git` anywhere -> SkillCopyError (refuse the whole copy)
      - symlink -> SkillCopyError (name the path)
      - device/socket/fifo (stat.S_ISBLK/S_ISCHR/S_ISSOCK/S_ISFIFO) -> SkillCopyError
      - regular file exceeding MAX_FILE_BYTES -> SkillCopyError (name the path + size)
      - otherwise: copy2 (preserves mode, incl. the executable bit)
    Enforces MAX_FILE_COUNT and MAX_TOTAL_BYTES across the whole tree (single
    pre-scan pass before copying anything, so a violation aborts with NOTHING
    written to dest — no partial copy). Returns the list of copied relative
    paths (sorted). All destination paths are validated via `paths.safe_join`
    against `dest` before being written (defense in depth — src is walked by
    os.walk so no wildcard expansion, but the destination write path must not
    trust a name it derived from disk without the same containment check
    Phase A applies everywhere else)."""
```

- [ ] **Step 1 RED** — `tests/test_skillcopy.py`: happy path copies a small skill dir (SKILL.md + scripts/foo.sh executable) preserving the executable bit (assert `os.stat(...).st_mode & 0o111`); nested `.git` dir anywhere in the tree → refused, dest never created; symlink anywhere → refused; a fake device/socket (use `os.mkfifo` for a FIFO — creatable without root) → refused; oversized file (write > MAX_FILE_BYTES, or monkeypatch the constant to a tiny value for test speed) → refused, nothing written; file count over MAX_FILE_COUNT (monkeypatch to a small number) → refused; return value = sorted relative paths.
- [ ] **Step 2 GREEN**; suite green. **Step 3** commit `feat: skillcopy — hygiene-filtered skill tree copy (v0.3 B2)`.

---

### Task 3: promote.py — orchestration

**Files:** Create `src/aoh/promote.py`; Test `tests/test_promote.py`.

**Interfaces:**
```python
class PromoteError(ValueError): ...

@dataclass(frozen=True)
class PromoteResult:
    status: str              # "committed" | "pr_opened" | "noop"
    sha: str | None          # the commit sha (committed/noop) or None (pr_opened uses branch instead)
    branch: str | None       # set only for pr_opened
    pr_url: str | None       # set only for pr_opened (gh output)
    staged_diff: str         # `git diff --cached` output shown to the user BEFORE the commit decision;
                             # empty string for the noop case

def discover_skill_source(name: str, from_dir: Path | None, cwd: Path) -> Path:
    """If `from_dir` given, return it (must contain <from_dir>/SKILL.md,
    else PromoteError). Otherwise search upward from `cwd` for the first of
    `.claude/skills/<name>/SKILL.md` or `.agents/skills/<name>/SKILL.md`
    (checked at EVERY directory level, `.claude` before `.agents` at each
    level, before ascending — so a project's own `.claude/skills` wins over
    a parent's `.agents/skills` at the same depth, and the search stops at
    the FIRST match walking upward, never mixing levels). Raises PromoteError
    naming both paths tried if neither is found by the time cwd's filesystem
    root is reached."""

def promote_skill(*, name: str, from_dir: Path | None, pack_source: PackSource,
                  cache_dir: Path, pr: bool = False, cwd: Path | None = None) -> PromoteResult:
    """
    1. source = discover_skill_source(name, from_dir, cwd or Path.cwd())
    2. mirror = gitops.ensure_mirror(cache_dir, pack_source.repo)  # PromoteError if pack_source.local_path set — promote requires a git-backed pack
    3. branch, base_sha = gitops.fetch_default_branch(mirror)      # fresh fetch, always
    4. worktree = gitops.create_worktree(mirror, branch, cache_dir / "worktrees")
       try:
         5. gitops.check_identity(worktree)
         6. dest = paths.safe_join(worktree, "skills", safe_segment("skill", name))
            if dest.exists(): copied = skillcopy overwrite-in-place semantics (rmtree dest first — the
               worktree is throwaway, this is fine) else fresh copy
            skillcopy.copy_skill_tree(source, dest)
         7. pack = load_pack(worktree); validate_pack(pack)          # full validation, worktree root
         8. diff = `git diff --cached` after `git add -A` (reuse in commit_all — expose the staged
            diff via a helper `gitops.staged_diff(worktree)` called BEFORE commit_all commits)
         9. sha = gitops.commit_all(worktree, f"feat(skill): add {name} (promoted from local draft)")
            -> if commit_all raises "nothing to commit": status="noop"; sha = base commit's
               tree-equal ancestor -> actually: re-resolve HEAD sha (no new commit) and return
               PromoteResult(status="noop", sha=<HEAD sha>, ...)
        10. if not pr:
              gitops.push_fast_forward(mirror, worktree, branch)
              # ALSO forward-push the real remote so origin actually advances (the mirror is a
              # cache, not the source of truth): gitops.push_branch(worktree, pack_source.repo,
              # local_branch=branch, remote_branch=branch) using plain (non --mirror) semantics —
              # since worktree's origin remote already points at pack_source.repo (inherited from
              # the --mirror clone's remote config... NO: a --mirror clone's remotes point at the
              # ORIGINAL url already, so `git push` from the worktree, whose origin is the MIRROR
              # not the real repo — this needs the worktree's `origin` remote explicitly repointed
              # to pack_source.repo before any push in step 10/11. Do this once, right after
              # create_worktree, in promote_skill (not inside gitops functions) via
              # `gitops.set_remote_url(worktree, "origin", pack_source.repo)` — ADD THIS FUNCTION
              # to gitops.py in Task 1 (small addition to the interface list above).
              status = "committed"
           else:
              feature_branch = f"skill/{name}"
              # create + checkout feature_branch in the worktree (git checkout -b), same commit
              gitops.push_branch(worktree, pack_source.repo, feature_branch, feature_branch)
              pr_url = gitops.open_pr(pack_source.repo, feature_branch, branch, title, body)  # gh pr create, ADD to gitops.py
              status = "pr_opened"
       finally:
         11. gitops.remove_worktree(mirror, worktree)   # always, even on failure — but the raised
             error from steps 5-10 propagates AFTER cleanup (re-raise pattern, not swallowed)
    12. return PromoteResult(...)

    Same-skill-upstream-change-since-base conflict: detected structurally, not by a stored "base"
    across sessions (YAGNI-cut for v1 — see Task 3 note below) — instead: push_fast_forward's
    non-fast-forward rejection IS the conflict signal. On that specific rejection (direct-commit
    path only; --pr path can never conflict since it always creates a new branch), promote_skill
    catches it and re-raises as PromoteError with the exact text "upstream has moved since this
    promotion started — re-run with --pr" (never auto-retries, never force-pushes).
    """
```

**Design note on "promotion base" (resolves an open design ambiguity for v1):** rather than persisting
a cross-session "last known base" per skill (extra state, more moving parts), Phase B's conflict
detection is the fast-forward push itself: `fetch_default_branch` is called fresh at the START of
every promote, the worktree is cut from that exact tip, and the push only succeeds if the mirror's
`origin` is STILL at that tip when the push happens (i.e., nobody else promoted in between). This
is simpler than a persisted base and gives the same guarantee for the realistic case (one operator,
occasional promotes) — a persisted multi-skill base ledger is deferred to Phase D if concurrent
multi-operator promotion turns out to need it.

- [ ] **Step 1 RED** — `tests/test_promote.py` (fixture: bare origin.git seeded with a minimal valid v1alpha2 pack incl. an empty `skills/` dir + AOH.yaml; a local skill draft dir with SKILL.md + an executable script):
  - `discover_skill_source`: from_dir explicit wins; upward search finds `.claude/skills/<name>` two levels up; `.claude` beats `.agents` at the same level (create both, assert `.claude` wins); neither found → PromoteError naming both.
  - `promote_skill` direct-commit happy path: mirror created, worktree created+removed (assert dir gone after), commit lands, `git log` on a FRESH clone of the bare origin shows the new commit and the skill file present, `PromoteResult.status == "committed"`, `staged_diff` non-empty and mentions the new SKILL.md path.
  - Validation-failure path: draft skill has a broken frontmatter (name mismatch) → `promote_skill` raises PromoteError BEFORE any commit (assert origin's HEAD unchanged via a fresh clone).
  - No-op re-promote: promote the same unchanged skill twice → second call returns `status="noop"`, `sha` equals the first call's sha, origin HEAD unchanged (no new commit).
  - Conflict: after a first successful promote, simulate someone else pushing directly to origin's main (via a separate tracking clone) BEFORE a second promote of a DIFFERENT skill lands its push → second promote's `push_fast_forward` rejects, `promote_skill` raises PromoteError with "re-run with --pr" in the message, and the worktree is still cleaned up (assert via mirror's `git worktree list`).
  - `--pr` path: `promote_skill(..., pr=True)` creates branch `skill/<name>` on a **local bare "GitHub-simulating" remote** — since real `gh pr create` needs an actual GitHub repo, this test asserts UP TO the point of `push_branch` succeeding (branch exists on the real origin with the right commit) and stubs/mocks `gitops.open_pr` (monkeypatch it to return a fake URL) so the test stays network-free; assert `status == "pr_opened"`, `pr_url` is what the stub returned, and NO push happened to the default branch (main unchanged).
  - Secrets-copy-hygiene passthrough: a draft containing a symlink → `promote_skill` surfaces the `SkillCopyError` as a `PromoteError` (wrapped, message preserved), worktree still cleaned up, origin HEAD unchanged.
- [ ] **Step 2 GREEN**; implement `promote.py` PLUS the two small gitops.py additions surfaced by the interface walk above: `set_remote_url(worktree, remote_name, url)` and `open_pr(repo_url, head_branch, base_branch, title, body) -> str` (the latter shells out to `gh pr create --repo <repo> --head <head> --base <base> --title <title> --body <body> --json url -q .url`, wrapped the same way as `_git()` — capture stderr into GitOpsError on failure, including the specific case "gh: command not found" and "gh auth status" failures surfaced verbatim so the user knows to `gh auth login`). Suite green.
- [ ] **Step 3** commit `feat: promote orchestration — worktree-staged validate, commit/PR, fast-forward conflict detection (v0.3 B3)`.

---

### Task 4: CLI — `aoh skill promote`

**Files:** Modify `src/aoh/cli.py`; Test extend `tests/test_cli.py`.

- New `skill` subcommand GROUP with one subcommand `promote` (mirrors argparse
  sub-subparser pattern; dispatch `skill promote` checked in the `list`/`config`/`lock`-first
  dispatch block per Phase A's F10 ordering — pack-loading commands stay after).
- Flags: `aoh skill promote <name> [--from DIR] --pack <pack-name> [--pr]`.
  `--pack` resolves against `UserConfig.packs` (lazy-loaded, same as site fan-out) — PackError
  if the name isn't configured, naming the missing key and suggesting `aoh config set packs.<name> <repo-url>`.
  `--pack` value MUST resolve to a git-backed `PackSource` (repo set); a `local_path`-only pack
  entry is rejected with a clear PromoteError ("promote requires a git-hosted pack; `<name>` is
  configured as a local path").
- Handler prints the `staged_diff` BEFORE announcing success (design: "staged diff shown before
  direct push"), then one final line: for `committed` → `promoted <name> to <pack> @ <sha>`
  (+ pushed confirmation); for `pr_opened` → `opened PR: <pr_url>`; for `noop` → `<name> already
  up to date in <pack> @ <sha> (no-op)`.
- Any `PromoteError`/`GitOpsError`/`SkillCopyError` surfaces via the existing top-level
  `except PackError` pattern — extend that except clause (or add siblings) so all three map to
  the same `invalid AOH pack: <e>` / exit 1 style already used elsewhere, OR give promote its own
  clearly-labeled error prefix (`promote failed: <e>`) — prefer the latter since these aren't pack
  *validation* errors, they're operational git errors; keep `PackError` (validation-in-worktree
  failures) under the existing prefix since those genuinely are pack errors.

- [ ] **Step 1 RED** — CLI tests using a local bare-repo fixture (same pattern as Task 3's tests) + a tmp `AOH_HOME` with `packs: {testpack: {repo: file://<bare>}}` configured via `aoh config set`: `aoh skill promote foo --from <draft-dir> --pack testpack` → exit 0, prints staged diff + "promoted foo to testpack @", a fresh clone of the bare repo has the skill; unconfigured `--pack` name → exit 1, error names the missing config key; `--pack` pointing at a `local_path` pack → exit 1, clear message; re-run same command → exit 0, "(no-op)" message, no new commit (assert via `git log --oneline` count unchanged).
- [ ] **Step 2 GREEN**; suite green; 3 packs validate (unaffected). **Step 3** commit `feat: aoh skill promote CLI (v0.3 B4)`.

---

### Task 5: `collections/core/aoh-authoring` pack

**Files:** Create `collections/core/aoh-authoring/{AOH.yaml,skills/author-and-promote-skill/{SKILL.md,scripts/promote.sh}}`; Test extend an existing collection test file or new `tests/test_aoh_authoring_collection.py`.

- Pack manifest (v1alpha2), one skill: `author-and-promote-skill`.
- **On the engine-neutral question:** a skill instructing an agent to run `aoh skill promote ...`
  from its own shell is NOT a violation — AOH still never executes anything itself; the skill is
  agent-authored guidance consumed by whichever runtime interprets SKILL.md (identical in kind to
  every other AOH skill that tells an agent to run `kubectl`/scripts). The `ops`-prefixed command
  namespace convention doesn't apply here (this isn't a per-pack `ops-<skill>` command; it's a
  standing CLI verb), so the skill's script is a thin, deterministic wrapper
  (`scripts/promote.sh <name> --pack <pack> [--pr]` → `exec aoh skill promote "$@"`) rather than
  the skill hard-coding shell invocations inline — keeps the skill declarative and testable.
- SKILL.md content (frontmatter `name: author-and-promote-skill`, description explaining "use
  when you've drafted or improved a skill locally and want to publish it to a shared pack"):
  process steps — (1) confirm the draft validates standalone (frontmatter name/description,
  scripts executable) (2) identify the target pack by name from `~/.aoh/config.yaml` (3) run
  `scripts/promote.sh <name> --pack <pack-name>` (4) read the staged diff before it's pushed —
  stop and ask the user if anything looks unexpected (5) report the resulting commit/PR link.
  Explicitly states the honesty contract: "AOH does not intentionally manage secrets — review the
  staged diff yourself before this proceeds."

- [ ] **Step 1 RED**: collection test asserting `load_pack` + `validate_pack` succeed on the new
  pack, skill frontmatter matches dir name, script is executable (mode check), `docker-disk-cleanup`
  and `kubeops` unaffected (regression via existing collection tests).
- [ ] **Step 2 GREEN**; suite green; run `uv run aoh validate collections/core/aoh-authoring`
  (now 4 packs validate total — update any "3 packs" assumption in later steps' language, though no
  code enforces that count). **Step 3** commit `feat: aoh-authoring pack — draft-then-promote skill (v0.3 B5)`.

---

### Task 6: live validation — real promote against a scratch GitHub repo

**Files:** Evidence doc `docs/demos/promote-validation-2026-07-19.md`.

Using the authenticated `gh` CLI (account `initcron`, verified available): create a **throwaway
scratch repo** (e.g. `initcron/aoh-promote-scratch-<timestamp>`, private) seeded with a minimal
valid v1alpha2 pack (`AOH.yaml` + one dummy skill), NEVER the real `agenticdevops/aoh` repo.
1. `aoh config set packs.scratch https://github.com/initcron/aoh-promote-scratch-<ts>`
2. Draft a real skill locally (e.g. in `/private/tmp/claude-501/promote-live/.claude/skills/demo-echo/`).
3. `aoh skill promote demo-echo --pack scratch` (direct commit) — verify on GitHub (via `gh repo view`
   or `gh api`) that the commit landed on the default branch with the skill files present.
4. Re-run the identical promote — confirm no-op, no new commit on GitHub.
5. Draft a second skill, `aoh skill promote other-skill --pack scratch --pr` — verify via `gh pr list`
   that a real PR was opened; merge it via `gh pr merge --squash` (cleanup) or leave it and note it.
6. Delete the scratch repo (`gh repo delete --yes`) as final cleanup — do NOT leave a scratch repo
   under the `initcron` account.
Paste real command outputs (repo URLs, commit shas, PR URL) into the evidence doc. If `gh` auth or
network is unavailable at execution time, mark UNVERIFIED with the exact error and proceed — the
local hermetic tests (Tasks 1-5) are the required gate, this is confirmatory only (mirrors Phase A's
F14 "live smoke optional" precedent).

- [ ] Commit `docs: live promote validation — scratch repo, direct commit + PR path (v0.3 B6)`.

---

### Task 7: docs + roadmap + field note

**Files:** `.planning/ROADMAP.md` (phase B → ✅ done), `.planning/STATE.md` (dated session-log
entry, additions only; Position → phase C next), `.planning/PROJECT.md` (decision rows: promote
conflict-detection-via-fresh-fetch instead of persisted base; skillcopy hygiene limits; aoh-authoring
pack's script-wrapper pattern), `CHANGELOG.md` ([Unreleased] Added: `aoh skill promote`, aoh-authoring
pack, gitops write primitives), `docs/spec.md` (mention promote if it references the CLI command
list), NEW `docs/promote.md` (grounded in promote.py: the flow, the hygiene rules, the conflict
model, the honest secrets language), docs-site: NEW `docs/tutorials/authoring-and-promoting.mdx`
(draft a skill → promote → see it land; quiz), update `docs/reference/cli.md` (`aoh skill promote`
section), field note `blog/2026-07-19-draft-to-promote.md` (first-person, concise, truncate marker,
tags [authoring, ansible]; hook: "the ad-hoc-to-role ladder, but for AOH").

- [ ] Gates: `rtk proxy uv run pytest -q` green; `npm --prefix docs-site run build` exit 0; all
  packs validate (docker-disk-cleanup, kubeops, acme-platform-ops, aoh-authoring). Commit
  `docs: v0.3 phase B shipped — authoring/promote (roadmap, promote reference, field note)`.

## Self-review notes

- Spec coverage: bare-mirror+lock+worktree+FF-only ✓(T1); copy hygiene ✓(T2); orchestration incl.
  no-op/conflict/--pr ✓(T3); CLI ✓(T4); aoh-authoring pack ✓(T5); live proof ✓(T6, using the
  environment's real authenticated `gh`, against a scratch repo only); docs ✓(T7).
- Resolved a real design ambiguity inline (Task 3 note): "promotion base" is the fresh-fetch tip,
  not a persisted ledger — YAGNI for a single-operator v1, documented so it isn't re-litigated.
- `set_remote_url`/`open_pr` surfaced as needed gitops additions during the interface walk in Task 3
  — folded into Task 1/3 rather than left implicit, so a fresh implementer isn't stuck reverse-engineering
  "how does the worktree's origin even point at the real repo instead of the mirror."
- Never touches the real `agenticdevops/aoh` repo in any live/test path — scratch repo only (Task 6),
  local bare repos only (Tasks 1-5 tests).
