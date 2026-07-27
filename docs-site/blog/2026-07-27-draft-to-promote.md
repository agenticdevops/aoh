---
title: "Draft to promote: the ad-hoc-to-role ladder, but for AOH"
authors: [gourav]
tags: [authoring, ansible]
date: 2026-07-27
---

Ansible has a well-worn ladder: run an ad-hoc command, realize you're running it
again, turn it into a playbook task, then — once it's proven itself — promote it
into a role you can reuse and share. AOH didn't have the last rung of that ladder
until this week. You could draft a skill locally, use it in whatever session you
were already in, and then... hand-copy it into a pack repo and hope you got the
git plumbing right. That's not a promotion path, that's a chore.

<!-- truncate -->

`aoh skill promote <name> --pack <pack-name>` is that rung now. It finds your
draft (`.claude/skills/<name>` or `.agents/skills/<name>`, searched upward from
wherever you're standing), copies it through a hygiene filter — no symlinks, no
stray `.git` dirs, no oversized files — into a fresh worktree cut from the pack
repo's actual current tip, validates the whole pack there, shows you the staged
diff, and only then commits and fast-forward-pushes. `--pr` gets you a branch
and a real PR instead, same everything else.

The part I like most is what it deliberately doesn't do: no persisted "last
known state" per skill. Every promote re-fetches the pack's default branch
fresh and the push itself is the conflict check — if the branch moved
underneath you, the push just fails, and the error tells you to re-run with
`--pr`. No retries, no force-push, no state file to get out of sync. I proved
this against a real scratch repo on GitHub, not just local fixtures: a direct
commit, a no-op re-promote that added nothing, and a `--pr` that opened and
merged a real PR — including one honestly-documented bug in the PR-open path
that the live run caught and a unit test hadn't.

Drafted, proven, promoted. That's the whole ladder now.
