import jwt
import hashlib
import hmac
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from src.core.config import settings
from src.core.logging import get_logger
from src.database.repositories.user_repository import UserRepository
from src.api.dependencies import get_user_repository

logger = get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

class TelegramAuthData(BaseModel):
    id: int
    first_name: str
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str
    # Позволяет принимать любые доп. поля от ТГ (типа last_name), не ломая валидацию
    model_config = ConfigDict(extra='allow')

def verify(data: dict, token: str | None):
    if not token:
        logger.error("ADMIN_BOT_TOKEN is missing in settings!")
        return False
    
    data_to_check = data.copy()
    received_hash = data_to_check.pop("hash", None)
    if not received_hash:
        return False

    # Собираем строку: ключ=значение, отсортировано, через \n
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data_to_check.items()))
    
    # Секретный ключ — это SHA256 от токена бота
    secret = hashlib.sha256(token.encode()).digest()
    computed_hash = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()

    return hmac.compare_digest(computed_hash, received_hash)

@router.post("/telegram")
async def telegram_auth(
    data: TelegramAuthData,
    user_repo: UserRepository = Depends(get_user_repository),
):
    # Универсальный способ получить словарь из Pydantic
    auth_data = data.model_dump(exclude_none=True) if hasattr(data, "model_dump") else data.dict(exclude_none=True)

    if not verify(auth_data, settings.ADMIN_BOT_TOKEN):
        logger.error(f"AUTH_FAILED for user {auth_data.get('id')}")
        raise HTTPException(status_code=401, detail="Invalid Telegram signature")

    telegram_id = auth_data["id"]
    first_name = auth_data["first_name"]
    username = auth_data.get("username")

    # Create or get user
    user_id, created = await user_repo.get_or_create_by_telegram(
        telegram_id, first_name, username
    )
    logger.info(
        "User authenticated",
        extra={"user_id": user_id, "telegram_id": telegram_id, "created": created}
    )

    # Generate JWT with user_id
    payload = {
        "sub": user_id,
        "username": username,
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(hours=24)).timestamp()),
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    
    # Return token and user info
    return {
        "access_token": token,
        "user_id": user_id,
        "username": username,
        "full_name": first_name,
    }
