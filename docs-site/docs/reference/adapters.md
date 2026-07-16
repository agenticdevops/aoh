---
title: Runtime Adapters
---

# Runtime Adapters

An adapter compiles an engine-neutral AOH pack into a runtime-native profile. AOH
never executes anything itself — see [Engine-Neutral by Design](../concepts/engine-neutral)
for the full rule. Three adapters are **shipped** today: Hermes, Claude Code, and
Codex. This page documents what each one actually generates, the shared threat
model across all three, and where each runtime's guardrail does and doesn't hold.

## What an adapter does

Every adapter implements the same `RuntimeAdapter` protocol
(`src/aoh/adapters/base.py`): one `materialize(request)` method taking a validated
`Pack` plus optional `output_dir`, `role_name`, `binding`, `profile`, and
`model_hint`, and returning an `AdapterResult` (`runtime`, `output_dir`,
`generated_files`, `diagnostics`). `diagnostics` is how an adapter tells you "I
generated this, but I cannot fully enforce that requirement" instead of silently
claiming a guarantee it can't back up — both the Claude Code and Codex adapters emit
one for `access: inherit` bindings (no RBAC boundary), and the Codex adapter always
emits one explaining its guardrail's bypass gaps.

Given a validated `Pack`, an adapter:

1. Materializes skills into the runtime's skill format.
2. Generates one invokable command per skill under the `ops-<skill>` namespace,
   translated to the runtime's own command convention.
3. Maps `Role` / `Team` structure onto whatever grouping concept the runtime has
   (a Hermes profile, a Claude Code subagent, a Codex `AGENTS.md`).
4. Maps each declared `RuntimeRequirement` onto a native guardrail, or documents
   the gap if the runtime can't enforce it.
5. For a `Binding`, renders the access-mode-appropriate provisioning script via the
   shared, runtime-agnostic `src/aoh/adapters/_k8s.py` helpers — so the RBAC surface
   an agent gets never depends on which runtime it runs under.

Materialize any pack for any shipped runtime with one runtime-neutral entrypoint:

```bash
uv run aoh install --runtime <hermes|claude-code|codex> <pack> --output <dir> \
  [--binding <file>] [--role <name>] [--profile <name>] [--model <hint>]
```

Source: [`src/aoh/adapters/hermes.py`](https://github.com/agenticdevops/aoh/blob/main/src/aoh/adapters/hermes.py),
[`src/aoh/adapters/claude_code.py`](https://github.com/agenticdevops/aoh/blob/main/src/aoh/adapters/claude_code.py),
[`src/aoh/adapters/codex.py`](https://github.com/agenticdevops/aoh/blob/main/src/aoh/adapters/codex.py).

## Workspace layouts

Each adapter materializes a **self-contained workspace directory**. None of them
touch `~/.claude`, `~/.codex`, or any global runtime state — everything an install
needs lives under `--output <dir>`, non-invasively.

### Hermes

```text
<output>/
  skills/<skill-name>/SKILL.md
  commands/ops-<skill-name>.md
  aoh-hermes.json
```

`install-hermes-agent` additionally produces a launchable profile
(`config.yaml`, `SOUL.md`, profile-local skills, `launch.sh`) under a Hermes profiles
directory — see [Hermes adapter, in detail](#hermes-adapter-detail) below for the
full mapping. Hermes ships **no** kubectl-aware guardrail: it was verified from
source to have a hardcoded pattern list with zero kubectl awareness and no
subcommand allow/deny config.

### Claude Code

```text
<output>/
  .claude/skills/<skill>/SKILL.md (+scripts)
  .claude/commands/ops/<skill>.md          → /ops:<skill>
  .claude/agents/<role>.md
  .claude/settings.json                    permissions deny/allow + env.KUBECONFIG
  .claude/hooks/kubectl-guard.sh           PreToolUse hook (0755)
  CLAUDE.md                                role, posture, walls explained honestly
  kubeconfig | kubeconfig-overlay          per access mode
  provision.sh | prepare-overlay.sh        per access mode (0755)
  launch.sh                                exports KUBECONFIG, execs claude
```

### Codex

```text
<output>/
  .agents/skills/ops-<skill>/SKILL.md (+scripts)   wrapper-named to keep the `ops`
                                                    namespace; frontmatter `name:` is
                                                    REWRITTEN to ops-<skill> — a
                                                    directory rename alone does not
                                                    change the invocation name
  .codex/rules/kubectl-readonly.rules              best-effort deny: kubectl/helm
                                                    mutation verbs → forbidden; header
                                                    comment documents the known gaps
  AGENTS.md                                        role, posture, "RBAC is the
                                                    boundary"
  .codex/config.toml                               model, approval_policy=
                                                    "on-request", sandbox_mode=
                                                    "workspace-write",
                                                    [sandbox_workspace_write]
                                                    network_access=true
  kubeconfig | kubeconfig-overlay, provision.sh    per access mode
  launch.sh                                        exports KUBECONFIG, execs codex
```

Codex's project-scoped custom prompts (`prompts/`) are **deprecated** on the 0.144.x
line and are not used by this adapter — the wrapper-named skill itself is both the
capability and the invokable command (`$ops-<skill>`). Project-local config, hooks,
and rules all require a **trusted project**; the adapter's generated files assume the
workspace directory will be trusted before `codex` is launched against it.

## Access modes

`Binding.access` is `scoped` (default) or `inherit` — the loader rejects any other
value. This choice is orthogonal to the runtime; every adapter renders both modes the
same way via the shared `_k8s.py` helpers.

- **`scoped`**: `provision.sh` creates a dedicated ServiceAccount bound to an explicit
  resource allowlist (see below), then writes a scoped `kubeconfig` (0600) next to
  the script. This is a **hard enforcement boundary**: the cluster API server itself
  rejects mutating requests from this identity, independent of anything the runtime
  or its guardrails do.
- **`inherit`**: `prepare-overlay.sh` writes **no credentials at all**. It resolves
  the target context's cluster/user entry *names* from the operator's own merged
  kubeconfig via a redacted `kubectl config view` (never `--raw`, which would print
  embedded credential material), verifies the result resolves via
  `kubectl config view --minify`, and self-checks its own output for credential-shaped
  content before declaring success. It writes a minimal `kubeconfig-overlay` pinning
  `current-context` + namespace. `launch.sh` exports
  `KUBECONFIG=<overlay>:${KUBECONFIG:-$HOME/.kube/config}` — kubeconfig merge rules
  mean the overlay wins for `current-context`, but the cluster/user names it
  references still resolve against the operator's own file, so exec-plugin auth (e.g.
  `gke-gcloud-auth-plugin`) keeps working. There is **no hard enforcement boundary**
  in this mode: the agent acts as the operator, and whatever the operator's
  credentials can do, the agent can do. Every adapter's CLAUDE.md/AGENTS.md states
  this plainly, and both the Claude Code and Codex adapters emit a diagnostic
  (`access=inherit: no RBAC boundary — agent acts with the user's credentials,
  context-pinned only`).

## Threat model: hard boundary vs. best-effort guardrail

The honest framing, stated the same way everywhere in the docs and in the generated
CLAUDE.md/AGENTS.md files:

| Runtime | Hard enforcement boundary | Best-effort runtime guardrail | Required assumptions |
|---|---|---|---|
| Claude Code | cluster RBAC via scoped identity | `permissions.deny` + PreToolUse hook | agent uses the workspace kubeconfig; host credentials are not isolated unless the operator sandboxes the session |
| Codex | cluster RBAC via scoped identity | execpolicy rules (prefix-based, documented gaps) + `approval_policy` | same |
| Hermes | cluster RBAC via scoped identity | none | same |

The scoped kubeconfig is the workspace's **default identity**, not containment — a
hostile or sufficiently motivated agent could still read other credentials present on
the host. Containment (an isolated `HOME`, or running inside a container) is out of
scope for all three adapters today and is stated as an assumption, not a guarantee.
RBAC bounds whatever *authenticates as* the scoped identity; that authentication
boundary is the one thing here that actually holds regardless of runtime behavior.

The scoped RBAC allowlist itself (`ClusterRole aoh-readonly`, rendered by
`_k8s.py::render_provision_script`, shared by every adapter) is an **explicit
resource allowlist**, not a wildcard:

- included (get/list/watch only): core `nodes`, `pods`, `pods/log`, `events`,
  `endpoints`, `services`, `persistentvolumeclaims`, `persistentvolumes`,
  `namespaces`, `replicationcontrollers`, `resourcequotas`, `limitranges`; `apps`
  `deployments`, `replicasets`, `daemonsets`, `statefulsets`; `batch` `jobs`,
  `cronjobs`; `metrics.k8s.io` `nodes`/`pods`; `events.k8s.io` `events`.
- explicitly **excluded**: `secrets`, `configmaps`, `nodes/proxy`, `pods/exec`,
  `pods/attach`, `pods/portforward`, `serviceaccounts/token`, RBAC objects,
  `certificatesigningrequests`.

Live proof that this allowlist actually holds against a real cluster — including the
`get secrets` flip from `yes` (old wildcard role) to `no` (new allowlist) — is in
[`docs/demos/adapter-validation-2026-07-16.md`](https://github.com/agenticdevops/aoh/blob/main/docs/demos/adapter-validation-2026-07-16.md).

## Guardrail mapping, per runtime

### Claude Code: deny list + PreToolUse hook

`.claude/settings.json` sets `permissions.deny` for kubectl/helm mutation verbs
(`delete, apply, edit, patch, replace, create, drain, cordon, uncordon, taint, scale,
rollout, set, annotate, label, expose, run, debug, autoscale, exec, attach,
port-forward, cp, certificate`, plus `helm upgrade/install/uninstall/rollback`) and
`permissions.allow` for the read verbs plus the pack's own skill scripts.
`defaultMode` stays `default` (anything unlisted prompts the operator), and
`.claude/hooks/kubectl-guard.sh` is wired as a `PreToolUse` hook on the Bash tool as a
parser-level backstop: it receives the tool-call JSON, extracts the command, strips
wrapper tokens (`sudo`, `env`, `time`), unwraps `sh -c`/`bash -c`, strips a leading
absolute path off the kubectl/helm binary, tokenizes past flags to find the verb (and
sub-verb, for `auth`) tuple, and denies anything not in the read allowlist.
**Fail-closed** throughout: missing `jq`, a JSON parse failure, empty/absent stdin, or
any shell metacharacter (`| ; & > < $( ) `` \`) anywhere in the command all exit 2
(block) — the hook never falls through to allow on ambiguity.

This hook is why, in the live validation run, Claude Code catches all three of the
adversarial forms that slip past Codex's execpolicy rules (`--context`-first, absolute
binary path, `sh -c` wrapper) — real command normalization beats literal prefix
matching. It is still a **guardrail, not a boundary**: it only covers commands routed
through Claude Code's own Bash tool.

**Critical caveat — compound commands are blocked outright.** The hook's shell
metacharacter check is unconditional: it rejects `|`, `;`, `&`, `>`, `<`, `$(...)`,
backticks, and backslashes in **any** Bash tool call, regardless of whether kubectl or
helm is even mentioned. This means the Claude Code workspace hook blocks **all**
compound Bash commands — pipes, chained commands, redirects, command substitution —
not just kubectl mutations. A bare `kubectl get pods | grep Pending` is blocked exactly
like `kubectl delete pod x`. Bare `bash script.sh` invocations (i.e. `bash` with no
`-c`) are also blocked, because the hook only knows how to safely unwrap the
`sh -c '<command>'` / `bash -c "<command>"` form — a script-file invocation doesn't
match that shape and fails closed. Agents working in a Claude Code AOH workspace must
either call the pack's skill scripts directly (as `./script.sh args`, which the
`permissions.allow` list already covers) or split multi-stage shell work into separate
single-command tool calls instead of chaining them. This is a deliberate fail-closed
trade-off, not a bug: the hook cannot safely tokenize a command that contains shell
constructs it doesn't parse, so it blocks first and lets the operator (or the agent,
by restructuring the call) work around it.

### Codex: execpolicy rules with documented bypass gaps

`.codex/rules/kubectl-readonly.rules` uses codex-cli's `execpolicy` feature:
`prefix_rule(pattern=[...], decision="forbidden")` for every kubectl/helm mutation
verb, and `decision="allow"` entries for the read verbs. `approval_policy =
"on-request"` in `config.toml` adds a second, coarser layer.

The rules match on a **literal leading token-sequence prefix only** — there is no
normalization step like Claude Code's hook performs. Verified against the real
`codex execpolicy check` CLI (codex-cli 0.144.5), three forms provably bypass the
rules file entirely (all return `{"matchedRules":[]}`, no `"decision"` key at all):

1. `--context`-first invocations — `kubectl --context prod delete pod x`
2. absolute binary paths — `/usr/bin/kubectl delete pod x`
3. shell-wrapped invocations — `sh -c "kubectl delete pod x"`

These three forms are documented verbatim in the generated rules file's own header
comment, in `AGENTS.md`, and in the adapter's `diagnostics` output. Unlike Claude
Code, Codex has **no** hook that can actually block a tool call — Codex's lifecycle
hooks are notifications only (`continue: false` is not supported), so there is no
equivalent normalizing blocker available to close these gaps. RBAC is what actually
stops a mutation from succeeding for the Codex adapter; the rules file is a
convenience layer that catches the common, unadorned case and nothing more.

Live `codex execpolicy check` proofs for both the caught cases and the three gap forms
are in [`docs/demos/adapter-validation-2026-07-16.md`](https://github.com/agenticdevops/aoh/blob/main/docs/demos/adapter-validation-2026-07-16.md) §6.

### Hermes: no guardrail

The Hermes adapter ships no kubectl-aware guardrail at all — Hermes itself was
verified from source to have a hardcoded Bash pattern list with zero kubectl
awareness and no subcommand allow/deny configuration surface. RBAC is the entire
enforcement story for a Hermes-materialized workspace.

## Validation evidence

Everything above that makes a live-behavior claim (the `secrets` allowlist flip, the
`codex execpolicy check` proofs including the three gap forms, and the Claude Code
hook's adversarial-input proofs including the fail-closed cases) is backed by a real
run against a live cluster, not just unit test expectations — see
[`docs/demos/adapter-validation-2026-07-16.md`](https://github.com/agenticdevops/aoh/blob/main/docs/demos/adapter-validation-2026-07-16.md)
for the full transcript.

## Hermes adapter, in detail {#hermes-adapter-detail}

The original AOH runtime adapter, and still the most layered one. Four entry points,
each backing a CLI command (see [CLI Reference](./cli) for exact flags):

### `adapt-hermes` — generate files only

Writes files to `--output`; does not touch `~/.hermes/` or any live profile.
`aoh-hermes.json` records the pack name, skills, generated commands, roles, model
profiles, runtime requirements, and evals.

### `install-hermes` — install skills into a live skills directory

```text
~/.hermes/profiles/<profile>/skills/<category>/<skill-name>/SKILL.md
~/.hermes/profiles/<profile>/skills/<category>/<skill-name>/references/aoh-pack.md
~/.hermes/profiles/<profile>/skills/<category>/<pack-name>.aoh-hermes.json
```

Each installed skill also gets a generated `references/aoh-pack.md` describing the
owning pack's roles/models/requirements/evals, so Hermes has that context alongside
the skill.

### `install-hermes-agent` — a launchable custom Hermes profile

```text
<profiles-dir>/<profile>/
  config.yaml       # model/provider/tool settings
  SOUL.md            # AOH role instructions
  skills/            # profile-local AOH skills, scoped to the role if --role given
  aoh-agent.json     # manifest
  launch.sh          # preloads the associated skills, chmod 755
  provision.sh       # only if --binding given, chmod 755
```

`SOUL.md` is generated differently depending on whether `--role` is given: a
role-scoped profile gets the role's purpose, scope, skills, runtime requirements, and
responsibilities; a pack-level profile gets the pack's skills and runtime
requirements directly. If `--binding` is given, `SOUL.md` also gets a `## Binding`
section naming the bound kube context and default namespace, and stating that
mutation attempts are denied by the API server (a denial is the guardrail working,
not an error to work around).

`launch.sh` execs `hermes --profile <profile> --skills <skill,list> chat "$@"`; when
a binding is present it also exports `KUBECONFIG` to the profile-local
`kubeconfig` file that `provision.sh` writes.

This is a separate, still-supported operation from `aoh install --runtime hermes` —
it produces a launchable *profile* (`config.yaml`/`SOUL.md`/`launch.sh`), not just
the skills/commands file view `install --runtime hermes` writes. Running it now also
prints a stderr hint pointing at the newer entrypoint:
`hint: prefer 'aoh install --runtime hermes'` — the command's behavior itself is
unchanged, not deprecated.

### `install-hermes-team` — one profile per team role

Calls `install-hermes-agent` once per role in the team, with profile names
`<profile-prefix>-<role-name>`, then writes a team manifest
`<profile-prefix>-<team-name>.aoh-team.json` listing the generated profiles.

### Mapping summary

- AOH `skills/` copy directly into Hermes-compatible skills, each also getting a
  generated `commands/ops-<skill>.md`.
- AOH `teams/` become groups of role-scoped Hermes profiles.
- AOH `roles/` become role guidance in `SOUL.md` and role-scoped profile skills.
- AOH `models/` are referenced as model intent until deeper Hermes profile
  installation is added.
- AOH `runtime-requirements/` are surfaced as runtime expectations.
- AOH `evals/` are listed in the adapter manifest for future test runners.

## Out of scope today

Sandbox/container isolation of host credentials, live claude/codex session automation
beyond the scripted probes above, Goose/OpenCode adapters, binding groups, and
identity-change confirmation on re-provisioning are all explicitly out of scope for
the current adapters — see the design doc
(`.planning/design/2026-07-16-claude-codex-adapters-design.md`) for the full list.

## The `ops-<skill>` command namespace across runtimes

The canonical command name is `ops:<skill>`; each adapter maps the separator to its
runtime's convention:

| Runtime | Surface | Command | Status |
|---|---|---|---|
| Hermes | `commands/ops-<skill>.md` | `ops-<skill>` | shipped |
| Claude Code | `.claude/commands/ops/<skill>.md` (subdir → namespace) | `/ops:<skill>` | shipped |
| Codex | `.agents/skills/ops-<skill>/SKILL.md` (frontmatter `name` rewritten, no separate command file) | `$ops-<skill>` | shipped |
| OpenCode | `command/ops-<skill>.md` | `/ops-<skill>` | planned |

The prefix lives in the spec; separator mapping lives in each adapter.

## Adapter status

| Runtime | Status |
|---|---|
| Hermes | Shipped — `src/aoh/adapters/hermes.py` |
| Claude Code | Shipped — `src/aoh/adapters/claude_code.py` |
| Codex | Shipped — `src/aoh/adapters/codex.py` |
| Goose | Planned |

Runtime-specific knowledge belongs only inside `src/aoh/adapters/<runtime>.py` for
that runtime — the pack spec and `pack.py` model stay engine-neutral so a future
adapter compiles the same pack without the pack author changing a line.
