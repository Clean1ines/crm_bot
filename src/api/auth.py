import jwt
import hashlib
import hmac
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict # ConfigDict для гибкости

from src.core.config import settings
from src.core.logging import get_logger
from src.database.repositories.project_repository import ProjectRepository
from src.api.dependencies import get_project_repo

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
    repo: ProjectRepository = Depends(get_project_repo),
):
    # Универсальный способ получить словарь из Pydantic (v1 и v2)
    auth_data = data.model_dump(exclude_none=True) if hasattr(data, "model_dump") else data.dict(exclude_none=True)

    if not verify(auth_data, settings.ADMIN_BOT_TOKEN):
        logger.error(f"AUTH_FAILED for user {auth_data.get('id')}")
        raise HTTPException(status_code=401, detail="Invalid Telegram signature")

    chat_id = auth_data["id"]
    projects = await repo.get_projects_by_owner(chat_id)

    # Если проектов нет, возвращаем 403, но с данными юзера, чтобы фронт знал, кто зашел
    if not projects:
        logger.warning(f"USER_HAS_NO_PROJECTS: {chat_id}")
        # Можно кинуть 403, а можно выдать токен, но ограничить доступ — на твой вкус
        raise HTTPException(status_code=403, detail="Access denied: No projects found")

    payload = {
        "sub": str(chat_id),
        "username": auth_data.get("username"), # Сохраняем username в токене
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(hours=24)).timestamp()),
    }

    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    
    # Возвращаем и токен, и username
    return {
        "access_token": token,
        "username": auth_data.get("username")
    }