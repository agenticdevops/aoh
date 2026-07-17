# v0.3 — Fleet Lifecycle: Milestone Design

Date: 2026-07-17. Approved in brainstorming (conversation-driven across 2026-07-16/17).
Status: draft pending cross-AI review (codex).

## Vision

Close the loop that makes AOH a fleet system rather than a pack compiler:

```
draft skill locally (in Claude, wherever you work)
  → use it immediately (Layer 0, plain agentskills)
  → promote to the org pack repo (git = truth)
  → publish via registry index (git-hosted)
  → pin in the site repo (inventory: WHAT version × WHERE)
  → materialize the fleet (adapters, one command, N workspaces)
  → operate from inside a session (fleet console)
  → improve during incidents → capture back  → loop
```

Ansible is the reference frame throughout: role⇄skill, collection⇄pack,
inventory⇄site repo, galaxy⇄registry index, control node⇄fleet console,
ad-hoc→role ladder ⇄ draft→promote ladder. Deliberate difference: AOH has no
templating engine — the agent (or a deterministic script) renders; AOH never executes.

## Roadmap restructure

- v0.2 CLOSES with phases 1, 2, 2.5, 3, 5 done (validator simplification, v1alpha2,
  kubeops+Binding, adapter interface, Claude Code + Codex adapters).
- v0.2 phases 4 (drift), 7 (full inventory), 8 (import-runbook) MOVE into v0.3 —
  they converged into one story. Phase 6 (eval runner) stays parked (v0.4 candidate).
- v0.3 = five phases, order A→B→C→D→E (decided): each independently shippable.

## Decisions (2026-07-17)

| Decision | Choice | Why |
|---|---|---|
| Sequencing | A foundation → B authoring → C registry → D drift/sync → E console | Config+site substrate everything; authoring = hottest user need; sync needs version resolution; console consumes all |
| Promote flow | Direct commit to the pack repo by default; `--pr` flag for review-gated repos | User decision — fastest solo loop; teams opt into PR gate |
| Registry home | New repo `agenticdevops/aoh-registry` with `index.yaml`; orgs mirror privately | Clean separation; private = private index repo; resolution order explicit URL > org registry > public |
| User config | `~/.aoh/config.yaml` (+ `~/.aoh/repos/` clone cache, `~/.aoh/manifests/`) | git/ansible.cfg analog; names resolve from any cwd |
| Skills born local | Draft in the runtime's native local dir (`.claude/skills/`, `.agents/skills/`) — usable instantly, zero AOH | Layer 0 already is the draft area; no new draft mechanism |
| No templating engine | Skill dirs may carry `templates/`/`assets/` — copied verbatim; agent or script renders | Engine-neutral rule; AOH never executes |
| cwd stability | Every command takes NAMES, config supplies locations, git ops happen in `~/.aoh/repos/` cache | User requirement: never leave the project dir |

## Phase A — Foundation: config, site inventory, fan-out, list

### ~/.aoh/config.yaml
```yaml
apiVersion: openagentix.io/v1alpha2
kind: UserConfig
packs:                      # name → source (short name resolved via registry later)
  kubeops: https://github.com/agenticdevops/aoh//collections/core/kubeops
  myorg-ops: git@github.com:myorg/ops-pack.git
site: git@github.com:myorg/ops-site.git      # or a local path
defaults:
  runtime: claude-code
  workspace_root: ~/agents
```
Loaded by every command; `aoh config init|get|set` helpers. Local paths and git URLs
both legal everywhere (git URLs cached under `~/.aoh/repos/<slug>/`, `git pull` on use;
`//subdir` suffix = pack path inside a repo, ansible-galaxy style).

### site.yaml (in the site repo — the inventory)
```yaml
apiVersion: openagentix.io/v1alpha2
kind: Site
metadata: {name: myorg-ops-site}
spec:
  workspace_root: ~/agents            # default materialization root (user-overridable)
  defaults: {runtime: claude-code, model: gpt-5.4}
  packs:                              # requirements.yml analog — pins
    kubeops: {source: https://github.com/agenticdevops/aoh//collections/core/kubeops, version: main}
  groups:
    prod: {vars: {namespace: platform}}       # group_vars analog
    staging: {}
  bindings: bindings/                 # dir of Binding yamls; each MAY add:
                                      #   spec.groups: [prod]
                                      #   spec.pack: kubeops   (which pinned pack)
                                      #   spec.runtime: codex  (override default)
```
Binding var precedence: binding.target > group vars > site defaults. Binding gains two
OPTIONAL spec fields (`pack`, `groups`, `runtime`) — loader tolerates absence
(standalone bindings keep working; site-less flow untouched).

### CLI
- `aoh install --site <path|name> [--group g] [--binding name]` — fan-out: for each
  selected binding, resolve pack pin → materialize via the runtime adapter into
  `workspace_root/<binding-name>/`. Idempotent; prints per-workspace result + diagnostics.
- `aoh list [--site …]` — table: binding, role, pack@version, runtime, cluster/ns,
  access, workspace path, provisioned? (kubeconfig present).
- Existing single-shot `aoh install --runtime … --binding …` unchanged.

## Phase B — Authoring loop: draft local, promote central

- **Authoring skill** (new pack `collections/core/aoh-authoring`, installable to
  user-global skills): teaches the session to (1) draft a skill into the local runtime
  skills dir from "capture what we just did", agentskills-valid, with scripts/ +
  templates/ as needed; (2) run validation; (3) run promote on request.
- **`aoh skill promote <name> [--from <dir>] --pack <name> [--pr] [--sign-off]`**
  - `--from` defaults to the runtime-local skills dir discovered upward from cwd
    (`.claude/skills/`, `.agents/skills/`), explicit for odd layouts.
  - Validates the skill standalone (frontmatter name/description, scripts executable).
  - Resolves `--pack` via ~/.aoh config → cache clone → DEFAULT: commit to default
    branch + push. `--pr`: branch `skill/<name>` + `gh pr create`.
  - Commit message conventional: `feat(skill): add <name> (promoted from local draft)`.
  - Idempotent re-promote = update (diff-aware; refuses silently identical).
  - Never touches cwd. Prints the commit/PR URL.
- Promote is the same machinery later reused by capture (Phase D) with a different
  source (installed workspace instead of project dir).

## Phase C — Registry: index + version pinning

- New repo `agenticdevops/aoh-registry`, single `index.yaml`:
```yaml
apiVersion: openagentix.io/v1alpha2
kind: Registry
packs:
  kubeops:
    source: https://github.com/agenticdevops/aoh//collections/core/kubeops
    description: Kubernetes triage and health skills
    versions: [v0.2.0, main]          # git tags/branches; semver tags preferred
```
- `~/.aoh/config.yaml` gains `registries: [https://github.com/myorg/aoh-registry, https://github.com/agenticdevops/aoh-registry]` (ordered).
- Resolution: explicit URL in site/config > first registry hit by name. `aoh search <term>`
  greps registry descriptions. `aoh install kubeops@v0.2.0 --runtime …` works standalone.
- Site pins gain registry names: `packs: {kubeops: {version: v0.2.0}}` (source optional
  when resolvable via registry).
- Publishing = PR to the registry repo (manual for now; `aoh pack publish` = later).

## Phase D — Drift: status, sync, capture

- Materialization writes `aoh-manifest.json` into every workspace: pack name+source,
  resolved git sha, per-skill content hash (sha256 of file tree), binding name, adapter,
  timestamp. (Extends the existing aoh-agent.json/aoh-provision.json family.)
- `aoh status [--site …]` — three-way compare: pack repo (cache pull) vs manifest vs
  workspace files → UP-TO-DATE / BEHIND (pack moved) / MODIFIED (workspace edited) /
  BOTH (conflict).
- `aoh sync [--site --group]` — re-materialize BEHIND workspaces; refuses MODIFIED
  unless `--force` (or after capture).
- `aoh capture <binding> [--skill name] [--pr]` — lift MODIFIED skill dirs from a
  workspace back to the pack repo (promote machinery, workspace source). The incident
  loop: agent improves skill mid-incident → capture → (review) → merge → `sync --group`
  fans the improvement to the fleet.

## Phase E — Fleet console

- `aoh console --site … [--group g] --runtime claude-code --output <dir>` generates ONE
  control-node workspace:
  - per-binding scoped kubeconfig materialization (provision-all.sh runs each binding's
    provisioning; kubeconfigs/<binding>.yaml)
  - `.claude/agents/<binding>.md` — subagent per binding, instructions pin its
    kubeconfig path + read-only contract (codex runtime: skill per binding instead)
  - fleet skill: name→identity map, "operate <binding>" semantics
  - generalized kubectl-guard hook: read verbs only AND `--kubeconfig` value must be
    one of the fleet identity paths (deny otherwise, fail closed)
  - CLAUDE.md/AGENTS.md = rendered inventory (the site, humanized)
- Honest threat language carries over: per-identity RBAC boundaries; console session
  mixes identities → per-binding audit trails still distinct; inherit-mode bindings
  flagged loudly in the console inventory.

## Cross-cutting

- Docs per phase: docs-site tutorial/reference updates + a field note each; ansible
  analogy table extended as features land (inventory → site.yaml, galaxy → registry…).
- Tests: TDD per phase; site/registry loaders in pack.py stay engine-neutral; git
  operations isolated in a `src/aoh/gitops.py` (mockable; tests use local bare repos,
  never the network).
- Security: promote/capture/publish never handle secrets; registry sources are https/ssh
  git only; `gh` used for PR paths; clone cache is per-user (0700).
- Out of scope v0.3: eval runner (v0.4), hosted registry service, pack dependency
  resolution (index lists packs; packs don't require packs yet), Goose adapter,
  multi-user site locking.

## Open questions for review

- site.yaml: bindings as dir-of-yamls (chosen) vs inline list — right call at 20+?
- Version pinning on `main` allowed (chosen: yes, with sync semantics = follow branch)?
- Console at 20 subagents: context-size impact of 20 agent defs in one workspace?
- Manifest hash granularity: per-skill tree hash enough, or per-file?
