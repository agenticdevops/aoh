# AOH Docs Site — Design

Date: 2026-07-16. Approved in brainstorming. Deliverable: a Docusaurus docs +
field-notes site for AOH users, published to GitHub Pages via GH Actions.

## Goal

A product/concept documentation site (not a graded course) that explains what AOH is,
why it exists, how to use it — with hand-drawn slide decks, mermaid diagrams,
DevOps-tool analogies (ansible/terraform), tutorials, and a "Field Notes" build-in-public
blog.

## Decisions (approved 2026-07-16)

| Decision | Choice | Why |
|---|---|---|
| Scaffold | Hand-build Docusaurus, reuse CourseSmith components (Slides/Quiz/Embed, custom.css, reveal deck pattern) | AOH is a tool to document, not a lab course; CourseSmith scaffold requires lab/spine machinery that doesn't fit |
| Location | `experiments/aoh/docs-site/` | Sibling-project convention in the monorepo |
| Deploy | GH Actions → GH Pages | User decision; matches project norm |
| IA | Concepts + Getting Started + Tutorials + Reference + Field Notes | User selected all |
| Analogies | Woven inline everywhere + dedicated `for-devops-engineers` page | User: anchors newcomers fast |
| Decks/quizzes | 3 hand-drawn decks on concept pages; `<Quiz>` at end of each tutorial | Visual punch where it teaches most |
| Field Notes | Docusaurus blog plugin, seeded from real history in author's voice | User: build-in-public log; voice grounded in agenticops.tv field note #1 |

## Tech scaffold

- Base: `create-docusaurus classic --typescript`, then copy from
  `~/work/apps/learning/coursesmith/templates/docusaurus-starter/`:
  `src/components/{Slides,Quiz,Embed}/`, `src/css/custom.css`, the reveal.js deck
  pattern for `static/decks/*.html`.
- Mermaid: `@docusaurus/theme-mermaid` (`markdown.mermaid: true`).
- Blog: built-in `@docusaurus/plugin-content-blog`, route `/field-notes`, nav "Field Notes".
- `onBrokenLinks: 'throw'` — dead links fail the build (quality gate).
- `docusaurus.config.ts`: `url: https://agenticdevops.github.io`, `baseUrl: /aoh/`,
  `organizationName: agenticdevops`, `projectName: aoh`, editUrl to the repo.

## Information architecture

```
Intro (docs landing)      hand-drawn "What is AOH" deck + 60-sec pitch + where-to-next
Concepts/
  what-is-aoh             why: install-drift, copy=fork, cheap-model trust; the wedge
  core-model              pack→skill→role→binding→adapter (mermaid) + core-model deck
  engine-neutral          AOH organizes/packages/validates/adapts; runtimes execute
  safe-agents             declared intent → native guardrail (RBAC); + safe-agents deck
  for-devops-engineers    analogy mapping table (ansible/terraform) + mermaid
Getting-Started/
  install                 uv, five-minutes-to-value, progressive disclosure
  first-pack              validate + adapt-hermes on collections/core/kubeops
  first-agent             install-hermes-agent, launch, read-only posture
Tutorials/
  build-a-pack            runbook → skills → role → eval, from scratch     [Quiz]
  kubeops-readonly        RBAC binding showcase vs kind cluster (mirrors demo doc) [Quiz]
  bindings-inventory      role × target, the site-repo/inventory pattern   [Quiz]
Reference/
  pack-spec               v1alpha2, mirrors docs/spec.md
  cli                     every aoh command + flags
  artifact-kinds          Pack/Skill/Role/Team/ModelProfile/RuntimeRequirement/Eval/Binding
  adapters                Hermes today; neutral interface; separator mapping table
Field Notes (blog)        dated build-in-public posts
```

Analogies woven inline in every concept page PLUS the dedicated page.

## Content sourcing (ground truth — no invented features)

- `.planning/PROJECT.md` — vision, core model, killer feature, decisions
- `docs/spec.md` — pack spec v1alpha2 (Reference/pack-spec mirrors it)
- `docs/demos/kubeops-readonly.md` — Tutorials/kubeops-readonly
- `docs/authoring.md`, `docs/hermes-adapter.md` — adapter + authoring reference
- `CHANGELOG.md` — what shipped
- `collections/core/*`, `examples/*` — real pack examples in code snippets
- Every CLI command verified against `src/aoh/cli.py`

## Hand-drawn decks (3, reveal.js, self-contained)

Sketch/excalidraw theme, each a standalone HTML in `static/decks/`, embedded via
`<Slides src="decks/<name>.html" title="..."/>`:

- `what-is-aoh.html` — the problem + the one-line pitch + the wedge
- `core-model.html` — the five nouns and how they compose
- `safe-agents.html` — declared intent → RBAC wall → Forbidden demo

## Field Notes seed posts (author's voice: first-person, thinking-out-loud, humble,
ends on "try it"; concise)

- `2026-07-14-killing-the-workflow-kind.md` — why Workflow collapsed into process
  skills; the `ops` prefix; simpler concept count before the spec hardened
- `2026-07-15-a-read-only-kubernetes-agent.md` — the kubeops RBAC binding; live
  `kubectl delete` → Forbidden; the shell-injection bug the final review caught
- `2026-07-16-building-aoh-docs-like-aoh-packs.md` — meta: the brainstorm→plan→
  subagent-driven loop building this very site

Author: Gourav Shah — Founder, Initcron AI / OpsFlow LLC / School of DevOps. RSS/Atom
on. Existing field note #1 (agenticops.tv) referenced as the origin post.

## Build + quality gate

- `npm --prefix docs-site run build` exits 0 (mermaid renders, decks load, quizzes
  valid, zero broken links)
- `.github/workflows/docs-deploy.yml`: on push to main touching `docs-site/**`, build +
  deploy to Pages (workflow-scope token note in the setup doc)

## Out of scope

Live labs / CourseSmith lab-spine machinery, versioned docs, Algolia search, i18n,
custom domain (uses `agenticdevops.github.io/aoh/`).
