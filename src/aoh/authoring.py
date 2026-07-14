from __future__ import annotations

from pathlib import Path


def create_pack(name: str, output: Path | str, description: str) -> Path:
    target = Path(output)
    target.mkdir(parents=True, exist_ok=False)

    _write(
        target / "AOH.yaml",
        f"""
        apiVersion: openagentix.io/v1alpha2
        kind: Pack
        metadata:
          name: {name}
          displayName: {name.replace("-", " ").title()}
          description: {description}
        """,
    )
    _write(
        target / f"skills/{name}/SKILL.md",
        f"""
        ---
        name: {name}
        description: Use when performing the {name.replace("-", " ")} ops process.
        ---

        # {name.replace("-", " ").title()}

        ## Overview

        Describe the reusable operational technique, required context, and safe first steps.

        ## Process

        1. Inspect current state.
        2. Explain findings.
        3. Recommend the smallest safe next action.
        """,
    )
    _write(
        target / "roles/ops-triage-lead.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Role
        metadata:
          name: ops-triage-lead
        spec:
          purpose: Coordinate safe operational diagnosis and concise remediation guidance.
        """,
    )
    _write(
        target / "models/local-worker.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: ModelProfile
        metadata:
          name: local-worker
        spec:
          intent: Execute known operational operations with a local or low-cost worker model.
        """,
    )
    _write(
        target / "runtime-requirements/shell-readonly.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: RuntimeRequirement
        metadata:
          name: shell-readonly
        spec:
          capabilities:
            - shell.read
        """,
    )
    _write(
        target / f"evals/{name}.yaml",
        f"""
        apiVersion: openagentix.io/v1alpha2
        kind: Eval
        metadata:
          name: {name}-basic
        spec:
          skill: {name}
          prompt: Run the {name.replace("-", " ")} process and explain the safest next action.
        """,
    )
    return target


def _write(path: Path, content: str) -> None:
    import textwrap

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
