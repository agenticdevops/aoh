# AOH MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a fast AOH vertical slice for an engine-neutral ops pack with a Hermes adapter.

**Architecture:** AOH packs are portable artifacts. The first helper validates a pack and materializes Hermes-ready skills and commands.

**Tech Stack:** Python, PyYAML, pytest.

---

## Task 1: Pack Discovery

- Add failing tests for loading an AOH pack.
- Implement `aoh.pack.load_pack`.
- Verify tests pass.

## Task 2: Hermes Adapter

- Add failing tests for generating Hermes output.
- Implement `aoh.adapters.hermes.generate_hermes_adapter`.
- Verify tests pass.

## Task 3: Core Vertical Slice

- Add failing test for checked-in `docker-disk-cleanup` pack.
- Add the pack under `collections/core/docker-disk-cleanup`.
- Verify tests pass.

## Task 4: Docs and Authoring

- Add README and design notes.
- Add `authoring-skills/create-aoh-pack/SKILL.md`.
- Run full test suite.
