---
title: Killing the Workflow kind
authors: [gourav]
tags: [spec, design]
date: 2026-07-14
---

Continuing the build-in-public thread from [Field Note #1](https://agenticops.tv) — this one's about deleting a kind I'd only just shipped.

<!-- truncate -->

AOH's spec started with a `Workflow` kind: a YAML file that named a sequence of skills a role should run in order. It felt obvious at the time — Ansible has playbooks, so AOH should have something that chains steps. I wrote it, wired the validator to it, had the Hermes adapter emit commands for it.

Then I actually looked at what was in one. A workflow file was a name, a list of skill references, and maybe a note on ordering. Every field in it either duplicated something already declared on the role, or restated the skill's own name back at me. It carried zero logic of its own — it was a reference bundle wearing a kind's clothing.

Around the same time I was reading through how Superpowers structures its own skills, and the pattern clicked: a multi-step process isn't a different *kind* of thing from a skill — it's a skill whose body happens to orchestrate other skills by name. `platform-sre-triage` doesn't need a `Workflow` wrapper; it needs a `SKILL.md` that says "run X, then branch on the result, then run Y." That's still a skill. The runtime doesn't care that it's "a workflow" — it just executes what the `SKILL.md` tells it to.

So `Workflow` came out. The multi-skill workflows in the example packs became process skills — same content, one fewer kind to validate, reference, and keep in sync with the role. While I was in there breaking things, I also renamed `agents/` to `roles/` (role is the real-world word; "agent" was doing double duty with the runtime concept) and picked `ops:` as the canonical command prefix Hermes emits, instead of `aoh:`.

Fewer kinds, same expressiveness, less to keep consistent. If you want the current shape of the spec — what's mandatory, what's opt-in, and where process skills fit — the [pack spec reference](/docs/reference/pack-spec) has the whole thing. Try it: run `aoh validate` against a skills-only pack and watch how little ceremony it actually takes to get to a valid one.
