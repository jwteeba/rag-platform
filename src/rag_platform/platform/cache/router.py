"""Admin-only cache layer statistics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from rag_platform.identity_access.api.v1.dependencies import CurrentUser, require_permission
from rag_platform.identity_access.domain.roles import Permission

router = APIRouter(prefix="/admin/cache", tags=["admin", "cache"])


@router.get(
    "/stats",
    dependencies=[Depends(require_permission(Permission.CACHE_STATS_READ))],
    summary="Get cache hit rates and Redis memory statistics",
)
async def cache_stats(_user: CurrentUser, request: Request) -> dict[str, object]:
    client = request.app.state.container.redis_client
    layers = {
        "embedding": "rag:cache:embedding:*",
        "retrieval": "rag:cache:retrieval:*",
        "llm": "rag:cache:llm:*",
    }
    layer_stats: dict[str, dict[str, float | int]] = {}
    for layer, pattern in layers.items():
        keys = 0
        async for _key in client.scan_iter(match=pattern, count=500):
            keys += 1
        hits = int(await client.get(f"rag:cache:metrics:{layer}:hits") or 0)
        misses = int(await client.get(f"rag:cache:metrics:{layer}:misses") or 0)
        total = hits + misses
        layer_stats[layer] = {
            "hits": hits,
            "misses": misses,
            "hit_rate": hits / total if total else 0.0,
            "key_count": keys,
        }

    memory = await client.info("memory")
    return {
        "layers": layer_stats,
        "redis_memory_used_bytes": int(memory.get("used_memory", 0)),
    }
