"""
Telegram Webhook Gateway with manager access control.

CRITICAL RULES:
- Admin bot (ADMIN_BOT_TOKEN) -> admin handlers.
- Client bots (any other token in projects) -> client handlers.
- Manager bots -> manager handlers, but only if sender chat_id is in project managers list.
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
from src.database.repositories.project_repository import ProjectRepository

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
    Gateway for Client and Admin bots.
    Routes based on token comparison with ADMIN_BOT_TOKEN.
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
        update["_bot_token"] = bot_token

        logger.debug("Received update", extra={"project_id": project_id})

        # 4. Routing Decision
        if bot_token.strip() == settings.ADMIN_BOT_TOKEN.strip():
            logger.info("Routing to Admin Bot handler")
            return await process_admin_update(update, pool)
        else:
            logger.info("Routing to Client Bot handler")
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
    Gateway for Manager Bots with access control.
    """
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not secret_token:
        raise HTTPException(status_code=401, detail="Missing secret token")

    # Find project by manager_bot_token (secret_token is the token itself, unencrypted)
    # Note: manager_bot_token is stored encrypted, but we compare with the raw token from Telegram.
    # We need to decrypt all manager tokens and compare.
    # Simpler: we fetch all projects and decrypt tokens in memory (but could be heavy).
    # Alternative: use a separate secret for manager webhooks. But spec uses the token itself.
    # We'll use a repository method to find project by manager token (decrypting in SQL).
    # For now, we'll use raw SQL with decryption (assuming pgcrypto or similar).
    # Since we don't have that, we'll iterate in Python (acceptable for small number of projects).

    project_repo = ProjectRepository(pool)
    project_id = await project_repo.find_project_by_manager_token(secret_token)
    if not project_id:
        raise HTTPException(status_code=401, detail="Invalid secret token")

    # Get decrypted manager token for sending messages
    manager_bot_token = await project_repo.get_manager_bot_token(project_id)
    if not manager_bot_token:
        logger.error("Manager token not found after project match", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Manager token error")

    # Parse update
    update = await request.json()
    # Extract sender chat_id
    chat_id = None
    if "message" in update:
        chat_id = update["message"].get("from", {}).get("id")
    elif "callback_query" in update:
        chat_id = update["callback_query"].get("from", {}).get("id")

    if not chat_id:
        logger.warning("No chat_id in update", extra={"update": update})
        # Still pass to handler? Probably not, but we'll return 200 to avoid retries.
        return {"ok": True}

    # Check if chat_id is in project managers
    managers = await project_repo.get_managers(project_id)
    if str(chat_id) not in [str(m) for m in managers]:
        logger.info("Unauthorized access attempt", extra={"chat_id": chat_id, "project_id": project_id})
        # Send access denied message
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{manager_bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": "⛔ Доступ запрещён. Вы не являетесь менеджером этого проекта."}
            )
        return {"ok": True}

    # Authorized - proceed
    update["_bot_token"] = manager_bot_token
    logger.debug("Authorized manager update", extra={"project_id": project_id, "chat_id": chat_id})
    return await process_manager_update(update, project_id, orchestrator, manager_bot_token)
