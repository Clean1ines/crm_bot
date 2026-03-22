import httpx
from fastapi import APIRouter, HTTPException
from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/bot", tags=["bot"])


@router.get("/username")
async def get_bot_username():
    logger.info("BOT_USERNAME_REQUEST")

    token = settings.ADMIN_BOT_TOKEN
    logger.info(f"TOKEN_EXISTS={bool(token)}")

    if not token:
        logger.error("NO_BOT_TOKEN")
        raise HTTPException(status_code=500)

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")

        logger.info(f"STATUS={resp.status_code}")

        data = resp.json()

        logger.info(f"RESPONSE={data}")

        if not data.get("ok"):
            logger.error("TELEGRAM_ERROR")
            raise HTTPException(status_code=500)

        result = {
            "username": data["result"]["username"],
            "id": data["result"]["id"],
        }

        logger.info(f"RETURN={result}")

        return result