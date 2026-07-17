"""Codex runtime adapter.

Materializes a self-contained workspace directory that Codex CLI can be
launched against: `ops-`-wrapped skills under `.agents/skills/`, `AGENTS.md`
project memory, a `.codex/config.toml` (model + sandbox posture), a
best-effort `execpolicy` rules file, and — for scoped bindings — a
provisioned read-only kubeconfig.

Threat model (see .planning/design/2026-07-16-claude-codex-adapters-design.md
§threat model, §"Codex read-only" row): the HARD enforcement boundary is the
scoped RBAC identity provisioned by `provision.sh` (shared with the Hermes
and Claude Code adapters via `aoh.adapters._k8s`). `.codex/rules/*.rules`
(execpolicy `forbidden`/`allow` prefix rules) plus `approval_policy` are a
BEST-EFFORT runtime guardrail layered on top — not a security boundary.

Codex's execpolicy rules match on a literal token PREFIX only, so they are
provably bypassable by at least three forms verified against the real
`codex execpolicy check` CLI (codex-cli 0.144.5): a `--context`-first
invocation (`kubectl --context prod delete ...`), an absolute path to the
binary (`/usr/bin/kubectl delete ...`), and a shell-wrapped invocation
(`sh -c "kubectl delete ..."`) — none of these match the prefix rule for
`kubectl delete`, so all three would fall through to "no matched rule"
(effectively allowed) if execpolicy were the only control. Unlike Claude
Code, Codex has no PreToolUse-style hook that can set `continue: false` to
block a tool call at the parser level — Codex hooks are lifecycle
notifications only, not gates — so there is no equivalent normalizing
blocker to close these gaps. RBAC therefore does all the real work; the
rules file and `approval_policy` are a convenience backstop that can warn or
require confirmation for some commands, not a boundary. AGENTS.md and the
adapter's diagnostics both state this honestly so operators do not mistake
the guardrail for containment.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from shutil import copytree

from aoh.adapters._k8s import (
    INHERIT_DIAGNOSTIC as _INHERIT_DIAGNOSTIC,
)
from aoh.adapters._k8s import (
    KUBECTL_MUTATION_COMMANDS,
    KUBECTL_READ_COMMANDS,
    kubeconfig_merge_shell_expr,
    render_overlay_prepare_script,
    render_provision_script,
    validate_binding_fields,
)
from aoh.adapters.base import ADAPTERS, AdapterResult, MaterializeRequest
from aoh.pack import Binding, Pack, PackError, Role, load_role

__all__ = ["CodexAdapter"]


_HELM_MUTATION_COMMANDS = ("install", "upgrade", "uninstall", "rollback")

_DEFAULT_MODEL = "gpt-5.4"

_DIAGNOSTIC = (
    "Codex has no complete Claude-style kubectl guardrail — execpolicy rules "
    "are best-effort prefix matches with known bypass gaps (--context-first, "
    "absolute path, shell wrappers); network access enabled for kubectl; "
    "RBAC is the enforcement boundary."
)


def _rewrite_skill_frontmatter_name(skill_md: Path, *, wrapped_name: str) -> None:
    """Rewrite the copied SKILL.md's frontmatter `name:` line in place.

    Parses the YAML frontmatter (between the two `---` delimiters), replaces
    only the `name:` line, and leaves `description:` and everything else —
    including the body — untouched. A directory rename alone does not change
    the skill's invocation name; Codex reads it from frontmatter.
    """

    text = skill_md.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise PackError(f"{skill_md} must contain YAML frontmatter")

    _, frontmatter, body = parts
    lines = frontmatter.splitlines()
    rewritten = []
    replaced = False
    for line in lines:
        if line.strip().startswith("name:"):
            rewritten.append(f"name: {wrapped_name}")
            replaced = True
        else:
            rewritten.append(line)
    if not replaced:
        raise PackError(f"{skill_md} frontmatter is missing a name: line")

    # splitlines() drops the frontmatter segment's trailing newline; restore
    # it so the closing `---` delimiter stands on its own line instead of
    # being glued to the last frontmatter line (regression: malformed
    # frontmatter that corrupted the description value).
    new_frontmatter = "\n".join(rewritten) + "\n"
    skill_md.write_text(f"---{new_frontmatter}---{body}", encoding="utf-8")


def _render_agents_md(
    pack: Pack, *, role: Role | None, skills: list[str], binding: Binding | None = None
) -> str:
    title = role.display_name if role else pack.name
    responsibilities = "\n".join(f"- {item}" for item in role.responsibilities) if role else ""
    purpose = role.purpose if role else pack.name

    invocations = "\n".join(f"- `$ops-{skill}`" for skill in skills)

    if binding is not None and binding.access == "inherit":
        contract = (
            "## Access mode: inherit — no hard enforcement boundary\n\n"
            "This binding uses `access: inherit`. You are acting with YOUR "
            "CREDENTIALS — the user's own kubeconfig identity, context-pinned "
            "to this cluster and namespace via a kubeconfig overlay. There is "
            "NO scoped RBAC identity and NO hard enforcement boundary in this "
            "mode: whatever the user's identity is permitted to do, this "
            "session can do. The `.codex/rules/kubectl-readonly.rules` file "
            "below is still a best-effort convenience guardrail, but with no "
            "RBAC backing it, treat every mutating command with the same "
            "caution you would if the user typed it themselves.\n\n"
            "This workspace also ships `.codex/rules/kubectl-readonly.rules`, "
            "a best-effort execpolicy guardrail that flags kubectl/helm "
            "mutation verbs. The rules match on a literal command prefix and "
            "are known to miss `--context`-first invocations, absolute "
            "binary paths, and shell-wrapped (`sh -c`) commands.\n"
        )
    else:
        contract = (
            "## Read-only contract\n\n"
            "You operate under a scoped, read-only Kubernetes identity. Prefer "
            "read-only inspection; report denials as the system working as "
            "intended, not as errors to work around. This holds when you start "
            "the agent via `./launch.sh` (which exports the workspace "
            "`KUBECONFIG`); launching codex directly in this directory uses "
            "your own kubeconfig instead.\n\n"
            "This workspace also ships `.codex/rules/kubectl-readonly.rules`, "
            "a best-effort execpolicy guardrail that flags kubectl/helm "
            "mutation verbs. Be honest about what this is: cluster RBAC is the "
            "enforcement boundary; the rules file is best-effort. The rules "
            "match on a literal command prefix and are known to miss "
            "`--context`-first invocations, absolute binary paths, and "
            "shell-wrapped (`sh -c`) commands — RBAC is what actually stops a "
            "mutation from succeeding.\n"
        )

    return (
        f"# AOH Codex workspace: {title}\n\n"
        "You are an Agentic Ops Harness runtime agent running under Codex. "
        "Stay focused on your assigned role and prefer the installed AOH "
        "skills over generic troubleshooting.\n\n"
        f"- Pack: {pack.name}\n"
        f"- Role: {role.name if role else '(none)'}\n"
        f"- Purpose: {purpose}\n\n"
        + (f"## Responsibilities\n\n{responsibilities}\n\n" if responsibilities else "")
        + "## Skills\n\n"
        f"{invocations}\n\n"
        f"{contract}"
    )


def _render_config_toml(*, model: str) -> str:
    return (
        f'model = "{model}"\n'
        'model_reasoning_effort = "medium"\n'
        'approval_policy = "on-request"\n'
        'sandbox_mode = "workspace-write"\n'
        "\n"
        "[sandbox_workspace_write]\n"
        "network_access = true\n"
    )


def _render_rules_file() -> str:
    lines = [
        "# Generated by AOH. Best-effort execpolicy guardrail for kubectl/helm.",
        "#",
        "# THIS IS NOT A SECURITY BOUNDARY. Cluster RBAC is the enforcement",
        "# boundary; this rules file is a best-effort convenience layer on top",
        "# of it. `prefix_rule` matches a literal leading token sequence only,",
        "# so it does NOT catch every way a mutation command can be spelled.",
        "# Verified bypass gaps against codex-cli 0.144.5 `codex execpolicy",
        "# check` (all three fall through to no matched rule):",
        "#   - --context-first invocations, e.g.",
        '#       kubectl --context prod delete pod x',
        "#   - absolute binary paths, e.g.",
        '#       /usr/bin/kubectl delete pod x',
        "#   - shell-wrapped invocations, e.g.",
        '#       sh -c "kubectl delete pod x"',
        "# See AGENTS.md and the AOH design doc for the full threat model.",
        "",
    ]

    for verb in KUBECTL_MUTATION_COMMANDS:
        lines.append(f'prefix_rule(pattern=["kubectl", "{verb}"], decision="forbidden")')
    for helm_verb in _HELM_MUTATION_COMMANDS:
        lines.append(f'prefix_rule(pattern=["helm", "{helm_verb}"], decision="forbidden")')

    lines.append("")

    for verb in KUBECTL_READ_COMMANDS:
        tokens = verb.split()
        pattern = ", ".join(f'"{t}"' for t in ["kubectl", *tokens])
        lines.append(f'prefix_rule(pattern=[{pattern}], decision="allow")')

    return "\n".join(lines) + "\n"


def _render_launch_script(*, with_kubeconfig: bool, inherit: bool = False) -> str:
    if not with_kubeconfig:
        kubeconfig_line = ""
    elif inherit:
        kubeconfig_line = f'export KUBECONFIG="{kubeconfig_merge_shell_expr("${DIR}")}"\n'
    else:
        kubeconfig_line = 'export KUBECONFIG="${DIR}/kubeconfig"\n'
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        'cd "${DIR}"\n'
        f"{kubeconfig_line}"
        'exec codex "$@"\n'
    )


class CodexAdapter:
    """RuntimeAdapter that materializes a Codex CLI workspace directory."""

    name = "codex"

    def materialize(self, request: MaterializeRequest) -> AdapterResult:
        pack = request.pack
        binding = request.binding
        role_name = request.role_name

        if binding is not None:
            if binding.role not in pack.roles:
                raise PackError(
                    f"Binding `{binding.name}` references missing role `{binding.role}`"
                )
            if role_name is not None and role_name != binding.role:
                raise PackError(
                    f"Binding `{binding.name}` role `{binding.role}` conflicts with --role `{role_name}`"
                )
            if not binding.target.get("kubeContext"):
                raise PackError(
                    f"Binding `{binding.name}` target.kubeContext is required for kubernetes targets"
                )
            validate_binding_fields(binding)
            role_name = binding.role

        workspace = Path(request.output_dir)
        agents_skills_dir = workspace / ".agents" / "skills"
        codex_dir = workspace / ".codex"
        rules_dir = codex_dir / "rules"

        for d in (agents_skills_dir, codex_dir, rules_dir):
            d.mkdir(parents=True, exist_ok=True)

        role = load_role(pack, role_name) if role_name else None
        selected_skills = role.skills if role and role.skills else pack.skills

        generated: list[Path] = []
        artifact_map: dict[str, str] = {}

        for skill in selected_skills:
            source = pack.root / "skills" / skill
            wrapped_name = f"ops-{skill}"
            destination = agents_skills_dir / wrapped_name
            copytree(source, destination, dirs_exist_ok=True)

            skill_md = destination / "SKILL.md"
            _rewrite_skill_frontmatter_name(skill_md, wrapped_name=wrapped_name)
            generated.append(skill_md)

            for source_path in sorted(source.rglob("*")):
                if not source_path.is_file():
                    continue
                rel = source_path.relative_to(source).as_posix()
                artifact_map[f"skills/{skill}/{rel}"] = (
                    f".agents/skills/{wrapped_name}/{rel}"
                )

        inherit = binding is not None and binding.access == "inherit"

        agents_md_file = workspace / "AGENTS.md"
        agents_md_file.write_text(
            _render_agents_md(pack, role=role, skills=selected_skills, binding=binding),
            encoding="utf-8",
        )
        generated.append(agents_md_file)

        model = request.model_hint or _DEFAULT_MODEL
        config_file = codex_dir / "config.toml"
        config_file.write_text(_render_config_toml(model=model), encoding="utf-8")
        generated.append(config_file)

        rules_file = rules_dir / "kubectl-readonly.rules"
        rules_file.write_text(_render_rules_file(), encoding="utf-8")
        generated.append(rules_file)

        launch_file = workspace / "launch.sh"
        launch_file.write_text(
            _render_launch_script(with_kubeconfig=binding is not None, inherit=inherit),
            encoding="utf-8",
        )
        os.chmod(launch_file, 0o755)
        generated.append(launch_file)

        diagnostics = [_DIAGNOSTIC]

        if binding is not None:
            if inherit:
                overlay_file = workspace / "prepare-overlay.sh"
                overlay_file.write_text(
                    render_overlay_prepare_script(binding), encoding="utf-8"
                )
                os.chmod(overlay_file, 0o755)
                generated.append(overlay_file)
                diagnostics.append(_INHERIT_DIAGNOSTIC)
            else:
                provision_file = workspace / "provision.sh"
                provision_file.write_text(render_provision_script(binding), encoding="utf-8")
                os.chmod(provision_file, 0o755)
                generated.append(provision_file)

        generated_files = sorted(p for p in workspace.rglob("*") if p.is_file())

        return AdapterResult(
            runtime="codex",
            output_dir=workspace,
            generated_files=generated_files,
            diagnostics=diagnostics,
            artifact_map=artifact_map,
            transform_id="codex-ops-rename-v1",
        )


ADAPTERS["codex"] = CodexAdapter()
