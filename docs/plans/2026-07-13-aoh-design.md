# AOH Design

## Goal

Build AOH as an engine-neutral Agentic Ops Harness: "Superpowers for Ops" packaged as reusable skills, workflows, agent roles, model profiles, runtime requirements, evals, and runtime adapters.

## Architecture

AOH has a portable pack format and runtime-specific adapters. The pack format is the product contract. Adapters map that contract into Hermes, Goose, Codex, Claude Code, OpenCode, or other agent runtimes.

Hermes is the first adapter because its Python core, skill system, delegation, cron, memory, terminal backends, model routing, and dashboard surface give us a fast validation path.

## MVP Boundary

The MVP does not build a standalone ops runner. It builds:

- an AOH pack schema by convention
- a Python validation and adapter helper
- one vertical slice pack
- a Hermes-native output generator
- one authoring skill for generating more packs

## V0 Commands

- `aoh init-pack`: create a starter engine-neutral AOH pack.
- `aoh validate`: validate pack structure and cross references.
- `aoh adapt-hermes`: materialize a Hermes-native view.

## Safety

AOH v0 declares runtime requirements and risk metadata. Mechanical enforcement belongs to the adapter/runtime. If a runtime cannot enforce a requirement, the adapter should warn rather than pretend it can.
