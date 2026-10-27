# Admizz pilot ingestion: runbook (tenant `admizz-test`)

**Status: the command is built and tested on fakes. It has NOT been run against the real database or search index.** Nothing in this runbook happens
unless a person types the commands and signs the approval file.

## What it does
Puts the **source-backed, ready** Admizz pages (today 9 pages, about 23 chunks, about 8,400 embedding tokens, roughly $0.001) into the `admizz-test`
knowledge base so the chatbot can answer from them instead of saying "I don't have that detail yet". Public website text stays **unverified**: ingesting
a page does not make its claims verified.

- Writes: one `ingestion_jobs` row per page, its `document_chunks` rows (Postgres) and its vectors (Pinecone namespace `admizz-test`). The database and
  index are shared by staging and production, but only the test tenant's data is written.
- Never: retires, replaces or deletes old chunks (that is a separate, later step), touches any other tenant, changes a migration or a dependency.
- Targets only `admizz-test`. Executing needs an approval file tied to the exact manifest and page list.

## Steps (from `backend/`, with the project venv and the real `.env`)
1. **Fresh manifest** (read-only, polite: robots.txt, 1 request/second, ~40 s):
   `python -m scripts.ingest_education_sources --manifest /tmp/pilot_manifest.json`
2. **Plan** (no website, no database, no index):
   `python -m scripts.ingest_education_pilot plan --manifest /tmp/pilot_manifest.json`
   It lists the pilot pages, the volume and cost, any page with no probe question, and the **approval template** with the manifest hash.
3. **Read the pilot pages** on the website. Someone at Admizz should agree the bot may quote them.
4. **Preflight** (reads the real store, writes nothing; needs the real `.env`):
   `python -m scripts.ingest_education_pilot preflight --manifest /tmp/pilot_manifest.json`
   Expect every page `would_add`. `needs_review` (a job for the same url with different content) or `needs_recovery` must be understood before going on.
5. **Approval file**, kept outside the repo, e.g. `/tmp/pilot_approval.json`: copy the template, replace `approved_by` with the person's name. Leave
   `confirmed_retire_job_ids` out. If any page changes, the approval stops matching and the run is refused.
6. **Execute**:
   `python -m scripts.ingest_education_pilot execute --manifest /tmp/pilot_manifest.json --approval-file /tmp/pilot_approval.json --report /tmp/pilot_run.json`
   Each page is written through the existing chunk pipeline and verified in BOTH stores; then every probe question is put to the real retrieval and the
   page passes when its own url is among the top 3 results. Keep `/tmp/pilot_run.json`: rollback needs it.
7. **Read the answers.** Ask the chatbot the probe questions (`app/data/education_sources/admizz-test.probes.json`) in the local widget or on staging and
   judge whether the answers are correct and useful. The check proves the pages are *found*, not that the answers are *right*.
8. **Rollback, if needed** (removes only the jobs that run added, vectors first, then the job): write `/tmp/rollback_approval.json` with the run's
   `manifest_sha256`, the approver, `page_ids`, and the exact job ids to remove in `confirmed_retire_job_ids` (they are in the report), then
   `python -m scripts.ingest_education_pilot rollback --report /tmp/pilot_run.json --approval-file /tmp/rollback_approval.json`

## Exit codes
| code | meaning |
|---|---|
| 0 | done (execute: stored, verified and found by retrieval) |
| 1 | refused or bad input (nothing was written) |
| 2 | plan/preflight problems, or the pages changed since the manifest (nothing was written) |
| 3 | ingestion or rollback stopped or failed (a half-written page is cleaned up; rerun the same command to resume) |
| 4 | stored and verified, but retrieval did not find every page: do NOT retire anything; read the report and fix |

## Safety properties (all tested against fakes)
Allow-listed tenant, customer and namespace must agree; approval tied to the manifest hash, tenant and page ids; only `ready` + `source_backed` pages;
each page must still match its manifest entry (size and content hash) and its canonical url; the website is read with robots.txt, 1 request/second,
bounded size and the approved host only; deterministic job ids make a rerun a no-op; a failed page is cleaned up and the batch stops; the real
services are built in one function, after every refusal check.

## Not covered here
Retiring the four old thin guide jobs (UK, USA, Australia, Canada), the 8 pages that need review, and ingestion for any other tenant. Each is a
separate, separately approved step.
