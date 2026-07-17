---
title: "Inventory — the Ansible idea AOH needed"
authors: [gourav]
tags: [fleet, ansible]
date: 2026-07-17
---

The pack/binding split has always leaned on an Ansible comparison — packs are
roles, bindings are inventory entries. What I hadn't built yet was the actual
inventory file. Every binding install was still one binding, one command, one
workspace. This week that changed: `site.yaml` plus a `bindingsDir` of binding
files, and `aoh install --site` fans out across all of them in one shot.

<!-- truncate -->

The part I spent the most time on wasn't the fan-out loop itself — that's a
straightforward per-binding install with failure isolation, so one bad binding
doesn't take the rest of the fleet down. It was `site.lock.yaml`. A site's pack
source points at a git ref like `main`, and `main` moves. Once a site fans out to
a dozen workspaces, "what commit is actually running" stops being a question you
can answer by eyeballing a YAML file — you need a pin, and you need the install
path to refuse to guess.

So `aoh install --site` won't run without a lock that agrees with `site.yaml`. It
resolves every pack through the lock's `resolvedCommit`, never by re-resolving the
ref itself. `aoh lock` only writes entries that don't exist yet; `aoh lock
--update` is the only thing that moves a pin forward, and it demands `--yes` if
the *source* changed, not just the commit. I proved this end to end with a real
git fixture: lock a pack, push a new commit upstream, re-install without
updating — the old commit is still what lands. Only after `aoh lock --update` does
the new one show up, and a commit that deletes a file actually removes it from
every workspace, not just adds the new ones.

That last part — convergence, not just fan-out — is what makes this feel like
inventory rather than a batch script. Ansible's inventory never made you think
about drift because the module system handled convergence per-host. AOH's install
path now does the same per-workspace, and the lock is what makes "per-workspace"
mean something across an entire fleet instead of one binding at a time.
