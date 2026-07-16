---
title: Building AOH's docs the way AOH builds packs
authors: [gourav]
tags: [meta, docs]
date: 2026-07-16
---

Last one in this run of Field Notes (see [#1](https://agenticops.tv) for where this all started) — and it's about the site you're reading right now.

<!-- truncate -->

I didn't want the docs to be a bolt-on written in a single pass at the end. AOH's whole pitch is that good agentic work follows a loop — brainstorm the shape, write the plan down, execute in reviewable slices, check the result against reality — so I built the docs site the same way I build a pack.

It started as a brainstorm, not a docs outline: what does someone actually need in the first sixty seconds, what's a concept versus a tutorial versus a reference page, which claims in the existing markdown are real versus roadmap. That turned into a written plan — sections, deck filenames, which pages get interactive components, a hard build gate (`onBrokenLinks: 'throw'`, zero tolerance) — before any content got written.

Then it went to subagent-driven execution: one task per slice (scaffold, concepts, decks, getting-started, tutorials, reference, this landing-and-blog task), each one reviewed on its own before the next started. A concept page couldn't claim a feature that wasn't in the code — the drift model, the eval runner, non-Hermes adapters are all marked "planned" rather than described as if they were shipped. And the whole thing closes with a full-branch review before it's called done, the same review discipline that gates a pack going into `collections/core/`.

It's a small thing, maybe, but it's the same conviction the harness itself is built on: process worth having for code is process worth having for the words describing that code, too.

If you want to see where it landed, the repo's right there — [github.com/agenticdevops/aoh](https://github.com/agenticdevops/aoh). Try it: clone it, run `uv run aoh validate` against one of the example packs, and see if the docs actually got you there without detours.
