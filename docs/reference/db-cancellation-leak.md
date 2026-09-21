# DB connection orphaned on client disconnect (known issue)

**Status:** known, accepted, not fixed. Decision 2026-09-21 (brain folder). No behaviour change shipped.
Regression marker: `backend/tests/test_db_cancel_release.py` (strict xfail).

## Symptom
Stage logs `ERROR Exception terminating connection ... CancelledError: Cancelled via cancel scope ...`
followed ~0.4s later by `The garbage collector is trying to clean up non-checked-in connection`
(sqlalchemy/asyncpg). Triggered when a client disconnects mid `/api/v1/query/stream` — e.g. ElevenLabs'
speculative-turn fan-out restarting a turn. Seen once on stage 05:49:25Z 2026-09-21; 0 hits on prod in 5 days.

## Mechanism
A disconnect cancels the request inside an anyio cancel scope. anyio re-delivers the cancellation at
EVERY await in that scope. If the cancel lands inside `db.execute`, SQLAlchemy's own (awaited) terminate of
the invalidated connection is cancelled too, so the asyncpg socket — still running the query — is orphaned
until GC. `pool.checkedout()` reads 0 throughout: pool bookkeeping lies; only the server's
`pg_stat_activity` shows it. Impact: a ~0.4s orphaned backend; on the 2-socket stage pool, a burst of
these can briefly starve it (shared 15-connection Supavisor ceiling with prod).

## Tried, does NOT fix (reproduced locally, GC disabled)
- (a) shield/await `session.close()` in `get_db`; (b) shielded rollback on CancelledError (re-raised) —
  the connection is orphaned earlier, inside the failing `execute`, before `get_db` cleanup runs.
- (c) pure-ASGI replacement for `CorrelationMiddleware` — removing the middleware entirely leaks
  identically; Starlette's `StreamingResponse` disconnect handling uses the same cancel scope.
- Pool `invalidate` hook calling asyncpg's synchronous `Connection.terminate()` — still leaked in the
  harness (not understood; possibly not reached on this path).

## Options
1. **Decouple the turn from the response cancel scope** (own asyncio task + queue; disconnect just stops
   reading). Correct shape; biggest change; abandoned turns still spend LLM tokens.
2. **`asyncio.shield` the DB calls on the clinic path.** Targeted, but whack-a-mole — every future
   `db.execute` must remember it, and it regresses silently.
3. **Accept** (chosen): transient, GC-recovered, 0 prod hits.

## Decision
Option 3 for now; attack the trigger instead (ElevenLabs Speculative-turn setting, gateway restart
behaviour). Revisit option 1 if fan-out can't be suppressed.

## Reproducing
See the recipe in the test docstring (docker Postgres + `TEST_DATABASE_URL`).
