from __future__ import annotations

import argparse
import sys
from pathlib import Path

import aoh.adapters
from aoh.adapters.base import ADAPTERS, MaterializeRequest
from aoh.adapters.hermes import (
    generate_hermes_adapter,
    install_hermes_agent,
    install_hermes_pack,
    install_hermes_team,
)
from aoh.authoring import create_pack
from aoh.pack import PackError, load_binding, load_pack, validate_pack


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aoh")
    subcommands = parser.add_subparsers(dest="command", required=True)

    validate = subcommands.add_parser("validate", help="Validate an AOH pack")
    validate.add_argument("pack", type=Path)

    init_pack = subcommands.add_parser("init-pack", help="Create a starter AOH pack")
    init_pack.add_argument("name")
    init_pack.add_argument("--output", type=Path, required=True)
    init_pack.add_argument("--description", required=True)

    install = subcommands.add_parser(
        "install", help="Install an AOH pack for a runtime (hermes, claude-code, codex)"
    )
    install.add_argument("pack", type=Path)
    install.add_argument(
        "--runtime",
        required=True,
        choices=["hermes", "claude-code", "codex"],
        help="Target runtime",
    )
    install.add_argument("--output", type=Path, required=True, help="Output directory")
    install.add_argument("--binding", type=Path, help="Optional binding file")
    install.add_argument("--role", help="Role name")
    install.add_argument("--profile", help="Profile name")
    install.add_argument("--model", help="Model hint")

    hermes = subcommands.add_parser("adapt-hermes", help="Generate a Hermes-native view")
    hermes.add_argument("pack", type=Path)
    hermes.add_argument("--output", type=Path, required=True)

    install_hermes = subcommands.add_parser(
        "install-hermes", help="Install AOH pack skills into a Hermes skills directory"
    )
    install_hermes.add_argument("pack", type=Path)
    install_hermes.add_argument("--skills-dir", type=Path, required=True)
    install_hermes.add_argument("--category", default="aoh")

    agent_hermes = subcommands.add_parser(
        "install-hermes-agent", help="Create a launchable Hermes profile for an AOH pack"
    )
    agent_hermes.add_argument("pack", type=Path)
    agent_hermes.add_argument("--profiles-dir", type=Path, default=Path("~/.hermes/profiles"))
    agent_hermes.add_argument("--profile", required=True)
    agent_hermes.add_argument("--provider", default="openai-codex")
    agent_hermes.add_argument("--model", default="gpt-5.4")
    agent_hermes.add_argument("--cwd", default=str(Path.cwd()))
    agent_hermes.add_argument("--category", default="aoh")
    agent_hermes.add_argument("--role")
    agent_hermes.add_argument("--binding", type=Path)

    team_hermes = subcommands.add_parser(
        "install-hermes-team", help="Create Hermes profiles for every role in an AOH team"
    )
    team_hermes.add_argument("pack", type=Path)
    team_hermes.add_argument("--profiles-dir", type=Path, default=Path("~/.hermes/profiles"))
    team_hermes.add_argument("--team", required=True)
    team_hermes.add_argument("--profile-prefix", required=True)
    team_hermes.add_argument("--provider", default="openai-codex")
    team_hermes.add_argument("--model", default="gpt-5.4")
    team_hermes.add_argument("--cwd", default=str(Path.cwd()))
    team_hermes.add_argument("--category", default="aoh")

    args = parser.parse_args(argv)

    try:
        if args.command == "init-pack":
            target = create_pack(args.name, args.output, args.description)
            print(f"created AOH pack: {target}")
            return 0

        pack = load_pack(args.pack)
        if args.command == "validate":
            validate_pack(pack)
            print(f"valid AOH pack: {pack.name}")
            return 0
        if args.command == "install":
            validate_pack(pack)
            binding = load_binding(args.binding) if args.binding else None
            req = MaterializeRequest(
                pack=pack,
                output_dir=args.output,
                role_name=args.role,
                binding=binding,
                profile=args.profile,
                model_hint=args.model,
            )
            result = ADAPTERS[args.runtime].materialize(req)
            for diagnostic in result.diagnostics:
                print(f"warning: {diagnostic}", file=sys.stderr)
            print(f"installed {args.runtime} workspace in {result.output_dir}")
            return 0
        if args.command == "adapt-hermes":
            validate_pack(pack)
            result = generate_hermes_adapter(pack, args.output)
            print(f"generated {len(result.generated_files)} Hermes files in {result.output_dir}")
            return 0
        if args.command == "install-hermes":
            validate_pack(pack)
            result = install_hermes_pack(pack, args.skills_dir, category=args.category)
            print(f"installed {len(result.generated_files)} Hermes files in {result.output_dir}")
            return 0
        if args.command == "install-hermes-agent":
            validate_pack(pack)
            binding = load_binding(args.binding) if args.binding else None
            result = install_hermes_agent(
                pack,
                args.profiles_dir,
                profile_name=args.profile,
                provider=args.provider,
                model=args.model,
                cwd=args.cwd,
                category=args.category,
                role_name=args.role,
                binding=binding,
            )
            print(f"installed Hermes agent profile in {result.output_dir}")
            print("hint: prefer 'aoh install --runtime hermes'", file=sys.stderr)
            return 0
        if args.command == "install-hermes-team":
            validate_pack(pack)
            result = install_hermes_team(
                pack,
                args.profiles_dir,
                team_name=args.team,
                profile_prefix=args.profile_prefix,
                provider=args.provider,
                model=args.model,
                cwd=args.cwd,
                category=args.category,
            )
            print(f"installed Hermes team profiles in {result.output_dir}")
            return 0
    except PackError as exc:
        print(f"invalid AOH pack: {exc}")
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
