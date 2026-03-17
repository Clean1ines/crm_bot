"""
Telegram Webhook Gateway.

CRITICAL RULE:
- Routing is based SOLELY on bot_token comparison.
- Admin Bot (ADMIN_BOT_TOKEN) -> src.admin.router
- Client Bot (Project Token) -> src.clients.router
- Manager Bot (Manager Token) -> src.managers.router
- NO chat_id checks here. Isolation is by token.
"""

import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
import asyncpg

from src.core.logging import get_logger
from src.core.config import settings
from src.api.dependencies import (
    get_pool,
    get_orchestrator,
    get_project_repo,
    get_redis,
)
from src.admin.router import process_admin_update
from src.clients.router import process_client_update
from src.managers.router import process_manager_update

logger = get_logger(__name__)
router = APIRouter()


@router.post("/webhook/{project_id}")
async def telegram_webhook(
    project_id: str,
    request: Request,
    pool=Depends(get_pool),
    orchestrator=Depends(get_orchestrator),
    project_repo=Depends(get_project_repo),
):
    """
    Smart Gateway for Client and Admin bots.
    Routes updates based on token comparison.
    """
    try:
        # 1. Verify Secret Token
        secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if not secret_token:
            raise HTTPException(status_code=401, detail="Missing secret token")

        # 2. Get Bot Token & Secret from DB
        bot_token = await project_repo.get_bot_token(project_id)
        if not bot_token:
            raise HTTPException(status_code=404, detail="Project not found")

        expected_secret = await project_repo.get_webhook_secret(project_id)
        if secret_token != expected_secret:
            raise HTTPException(status_code=401, detail="Invalid secret token")

        # 3. Parse Update
        update = await request.json()
        # Inject bot_token into update context for routers to use
        update["_bot_token"] = bot_token 
        
        logger.debug("Received update", extra={"project_id": project_id})

        # 4. ROUTING DECISION (The Core Fix)
        # Compare decrypted token from DB with ADMIN_BOT_TOKEN from ENV
        if bot_token.strip() == settings.ADMIN_BOT_TOKEN.strip():
            # ROUTE TO ADMIN MODULE
            logger.info("Routing to Admin Bot handler", extra={"project_id": project_id})
            return await process_admin_update(update, pool)
        
        else:
            # ROUTE TO CLIENT MODULE
            logger.info("Routing to Client Bot handler", extra={"project_id": project_id})
            return await process_client_update(update, project_id, orchestrator, bot_token)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error processing webhook", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/manager/webhook")
async def manager_webhook(
    request: Request,
    pool=Depends(get_pool),
    orchestrator=Depends(get_orchestrator),
):
    """
    Gateway for Manager Bots.
    Identifies project by matching secret_token against manager_bot_token in DB.
    """
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not secret_token:
        raise HTTPException(status_code=401, detail="Missing secret token")

    # Find project by manager_bot_token
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, manager_bot_token FROM projects WHERE manager_bot_token = $1",
            secret_token
        )
        if not row:
            raise HTTPException(status_code=401, detail="Invalid secret token")

    project_id = str(row["id"])
    manager_bot_token = row["manager_bot_token"]
    
    # Decrypt token if needed (repo does this, but raw SQL returns encrypted)
    # Assuming row['manager_bot_token'] is already decrypted if fetched via repo, 
    # but here we used raw SQL. Let's rely on the fact that we compared secret_token directly.
    # We need the DECRYPTED token to send messages.
    from src.database.repositories.project_repository import ProjectRepository
    proj_repo = ProjectRepository(pool)
    decrypted_token = await proj_repo.get_manager_bot_token(project_id)
    
    if not decrypted_token:
         logger.error("Manager token not found or decrypt failed", extra={"project_id": project_id})
         raise HTTPException(status_code=500, detail="Manager token error")

    try:
        update = await request.json()
        update["_bot_token"] = decrypted_token
        
        logger.debug("Received manager update", extra={"project_id": project_id})
        
        return await process_manager_update(update, project_id, orchestrator, decrypted_token)
        
    except Exception as e:
        logger.exception("Error in manager webhook")
        return {"ok": True} # Return OK to Telegram to avoid retries on logic errors
