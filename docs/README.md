# Zunkiree Search Repo Docs

Documentation for the Zunkiree Search code repo. The **session log lives in the brain folder** — this is the single source of truth.

## Where things live

```
docs/
├── README.md                 ← you are here
├── reference/                ← stable reference docs (read for context; don't edit per-task)
│   ├── architecture.md
│   ├── api-spec.md
│   ├── database-schema.md
│   ├── widget-spec.md
│   ├── widget-style-guide.md  (1198 lines — the canonical widget style ref)
│   ├── llm-abstraction.md
│   ├── developer-workflow.md
│   └── deployment-plan.md
├── briefs/                   ← ACTIVE feature briefs (currently empty — none in flight here)
└── archive/                  ← shipped/historical material
    ├── TODO.md               (Dec 28 2024)
    ├── project-roadmap.md    (Dec 26 2024)
    ├── implementation-plan.md (Jan 2025)
    ├── swap-commerce-analysis.md (April 2026 competitive research)
    ├── main-session-log.md   (pre-brain-folder repo log, frozen May 2026)
    └── session-log/          (Dec 2024 – Jan 2025 dated daily logs, originally at repo root)
```

## Session log — read this

The cross-product session log is in the brain folder:

```
~/Projects/sadin-stark-brain/docs/stella+zunkireesearch/SESSION-LOG.md
```

Header line = most recent milestone. The `🟢 NEXT SESSION — RESUME HERE` block at the top tells you exactly where to pick up. **Do not start a new session log in this repo.**

This repo's `docs/archive/main-session-log.md` and `docs/archive/session-log/*` are historical (pre-brain-folder era, frozen). They stay for paper trail.

## Brief filing convention

When the brain folder hands off work to the Zunkiree repo Window, the canonical brief lives in the brain folder:

```
~/Projects/sadin-stark-brain/docs/stella+zunkireesearch/<CONTEXT>-BRIEF.md
```

In-flight briefs specific to a multi-PR feature in this repo may live here under `docs/briefs/<feature>/`. When the feature ships → `git mv` to `docs/archive/<feature>/`.

## See also

- Repo root `CLAUDE.md` — operator's guide for this Window (env vars, deploy lifecycle, hard rules)
- Brain folder `CLAUDE.md` — cross-product control hub
- Brain folder `MEMORY.md` — persistent cross-session memory index
