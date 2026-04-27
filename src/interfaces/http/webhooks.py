"""
Telegram webhook gateway.
"""

from fastapi import APIRouter, Request, HTTPException, Depends

from src.application.errors import ApplicationError
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.config.settings import settings
from src.interfaces.http.dependencies import get_pool, get_orchestrator, get_project_member_repo, get_project_token_repo
from src.interfaces.telegram.platform_bot import process_admin_update
from src.interfaces.telegram.client_bot import process_client_update
from src.interfaces.telegram.manager_bot import process_manager_update
from src.application.services.webhook_dispatcher import WebhookDispatcher

logger = get_logger(__name__)
router = APIRouter()


def _get_dispatcher() -> WebhookDispatcher:
    return WebhookDispatcher(settings.ADMIN_BOT_TOKEN, settings.PLATFORM_WEBHOOK_SECRET)


@router.post("/webhooks/platform")
async def platform_webhook(request: Request, pool=Depends(get_pool)):
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    update = await request.json()
    return await _get_dispatcher().handle_platform_surface(
        update,
        secret_token,
        pool=pool,
        process_admin_update=process_admin_update,
        logger=logger,
    )


@router.post("/webhooks/projects/{project_id}/client")
async def client_webhook(
    project_id: str,
    request: Request,
    orchestrator=Depends(get_orchestrator),
    project_tokens=Depends(get_project_token_repo),
):
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    update = await request.json()
    return await _get_dispatcher().handle_client_surface(
        project_id,
        update,
        secret_token,
        orchestrator=orchestrator,
        project_tokens=project_tokens,
        process_client_update=process_client_update,
        logger=logger,
    )


@router.post("/webhooks/projects/{project_id}/manager")
async def project_manager_webhook(
    project_id: str,
    request: Request,
    orchestrator=Depends(get_orchestrator),
    project_tokens=Depends(get_project_token_repo),
    project_members=Depends(get_project_member_repo),
):
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    result = await _get_dispatcher().handle_manager_surface(
        project_id,
        update=await request.json(),
        secret_token=secret_token,
        orchestrator=orchestrator,
        project_tokens=project_tokens,
        project_members=project_members,
        process_manager_update=process_manager_update,
        logger=logger,
    )
    return result.to_dict() if hasattr(result, "to_dict") else result


@router.post("/webhook/{project_id}")
async def telegram_webhook(
    project_id: str,
    request: Request,
    orchestrator=Depends(get_orchestrator),
    project_tokens=Depends(get_project_token_repo),
):
    try:
        secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if not secret_token:
            raise HTTPException(status_code=401, detail="Missing secret token")

        bot_token = await project_tokens.get_bot_token(project_id)
        if not bot_token:
            raise HTTPException(status_code=404, detail="Project not found")
        if settings.ADMIN_BOT_TOKEN and bot_token.strip() == settings.ADMIN_BOT_TOKEN.strip():
            raise HTTPException(status_code=409, detail="Platform bot must use /webhooks/platform")

        result = await _get_dispatcher().handle_client_surface(
            project_id,
            await request.json(),
            secret_token,
            orchestrator=orchestrator,
            project_tokens=project_tokens,
            process_client_update=process_client_update,
            logger=logger,
        )
        return result.to_dict() if hasattr(result, "to_dict") else result

    except (HTTPException, ApplicationError):
        raise
    except Exception as exc:
        logger.exception(
            "Error processing webhook",
            extra={
                "project_id": project_id,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "policy": "propagate_to_safe_500_handler",
            },
        )
        raise


@router.post("/manager/webhook")
async def manager_webhook(
    request: Request,
    orchestrator=Depends(get_orchestrator),
    project_tokens=Depends(get_project_token_repo),
    project_members=Depends(get_project_member_repo),
):
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not secret_token:
        raise HTTPException(status_code=401, detail="Missing secret token")

    project_id = await project_tokens.find_project_by_manager_webhook_secret(secret_token)
    if not project_id:
        logger.warning("Invalid manager webhook secret")
        raise HTTPException(status_code=401, detail="Invalid secret token")

    result = await _get_dispatcher().handle_manager_surface(
        project_id,
        await request.json(),
        secret_token,
        orchestrator=orchestrator,
        project_tokens=project_tokens,
        project_members=project_members,
        process_manager_update=process_manager_update,
        logger=logger,
        skip_secret_validation=True,
    )
    return result.to_dict() if hasattr(result, "to_dict") else result
