# 0007. Redis caching scope and "session management" for Phase 4

- **Status:** Accepted
- **Date:** 2026-08-11

## Context

The project brief's Phase 4 is "Redis, Caching, Session management." Phase
0's architecture doc elaborates the CACHE section with embedding cache,
retrieval cache, prompt-template cache, and LLM-response cache — none of
which exist yet (they belong to Phases 8, 11, 12, 13). Building cache
wiring for features that don't exist yet would be speculative,
unverifiable code — exactly what the project's "no placeholder code" rule
exists to prevent. "Session management" is not elaborated anywhere in the
brief.

## Decision

**Scope Phase 4 to what's genuinely buildable and testable today:**

1. Generic Redis infrastructure — `core/cache.py` (`build_redis_client`,
   `CacheService`), a process-wide singleton (unlike the per-request DB
   session; see `core/cache.py`'s module docstring for why that's safe).
2. One concrete cache-aside consumer:
   `CachedRefreshTokenStore`, wrapping `PostgresRefreshTokenStore` behind
   the same `RefreshTokenStorePort`, caching `get()` lookups with a short
   TTL (`Settings.refresh_token_cache_ttl_seconds`, default 60s) and
   invalidating on every mutation (`store`, `revoke`, `revoke_all_for_user`).
   Postgres remains the source of truth throughout.
3. **"Session management" interpreted as literal, user-facing session
   control** — the only concept resembling "sessions" this application has
   is refresh tokens, so:
   - `GET /users/me/sessions` — list active sessions
   - `DELETE /users/me/sessions/{session_id}` — revoke one ("log out this
     device")
   - `POST /users/me/sessions/revoke-all` — revoke all ("log out
     everywhere")

   This required one new port method, `RefreshTokenStorePort.list_active_for_user`,
   implemented in all three adapters (in-memory, Postgres, and passed
   through unchanged by the cache wrapper — listing isn't cached, see
   below).
4. `/health/ready` gains a Redis `PING` check, alongside the existing
   Postgres check from Phase 3.

**Not built:** any cache for embeddings, retrieval, prompt templates, or
LLM responses — those get built, and their own ADRs if warranted, in the
phases that introduce the thing being cached.

## An honest note on the caching benefit

Refresh tokens in this application are single-use: `AuthenticationService.refresh()`
and `.revoke_session()` both call `get()` immediately followed by `revoke()`
on the same jti, in the same request. A *sequential* repeat read of an
already-used token essentially never happens — it's revoked before anyone
could read it again. So this isn't the "avoid N redundant DB hits per
token" story a naive reading of "cache-aside" might suggest. What it
actually provides:

1. Concurrent/duplicate requests on the same still-valid token (a client
   retrying a flaky `/auth/refresh` call, a double-click) can have their
   `get()` served from cache rather than racing each other against
   Postgres.
2. The reusable pattern itself. `CacheService` and this cache-aside shape
   (check cache → fall through on miss → cache the result → invalidate on
   mutation) is exactly what Phase 0's planned caching consumers will reuse
   in later phases. This is the first concrete, tested example of that
   pattern in the codebase.

Recorded here rather than only in code comments so the actual value
proposition is visible without reading the implementation.

## Consequences

- `docker-compose.yml` gains a `redis` service; `.github/workflows/ci.yml`'s
  test job provisions its own disposable Redis alongside its existing
  disposable Postgres.
- `list_active_for_user` is **not** cached — it's a low-frequency,
  per-user operation (viewing your own session list), not a per-request hot
  path, so the complexity of keeping a cached list in sync through every
  mutation isn't worth it. `CachedRefreshTokenStore` delegates it straight
  through to the wrapped store.
- `revoke_all_for_user` must invalidate every cached entry for that user,
  not just whichever jti triggered the call — implemented by listing the
  user's active sessions *before* revoking, then deleting each one's cache
  key. Getting this wrong would leave an already-revoked session reading as
  valid from cache for up to the TTL after "log out everywhere" — a real
  security gap, not just a staleness inconvenience.
