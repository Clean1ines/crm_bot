from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/api/rag-eval", tags=["rag-eval"])

_RAG_EVAL_NOT_CONNECTED_DETAIL = (
    "RAG eval is preserved as a domain capability, but the old execution_queue "
    "integration is retired. It will be reconnected later through the current "
    "knowledge extraction / retrieval-surface vertical."
)


@router.api_route("", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
async def rag_eval_not_connected_yet() -> dict[str, object]:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=_RAG_EVAL_NOT_CONNECTED_DETAIL,
    )


@router.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
async def rag_eval_path_not_connected_yet(path: str) -> dict[str, object]:
    del path
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=_RAG_EVAL_NOT_CONNECTED_DETAIL,
    )
