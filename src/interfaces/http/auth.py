import jwt
import hashlib
import hmac
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.interfaces.http.dependencies import get_user_repository, get_current_user_id
from src.domain.identity.user_views import UserProfileView
from src.application.services.auth_service import AuthConfig, AuthService
from src.infrastructure.identity.google_verifier import HttpGoogleIdentityVerifier

logger = get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def build_auth_service(user_repo: UserRepository) -> AuthService:
    config = AuthConfig(
        jwt_secret_key=settings.JWT_SECRET_KEY,
        frontend_url=settings.FRONTEND_URL,
        public_url=settings.PUBLIC_URL,
        render_external_url=settings.RENDER_EXTERNAL_URL,
        google_client_id=settings.GOOGLE_CLIENT_ID,
    )
    return AuthService(
        user_repo,
        config=config,
        google_verifier=HttpGoogleIdentityVerifier(google_client_id=settings.GOOGLE_CLIENT_ID),
    )


class TelegramAuthData(BaseModel):
    id: int
    first_name: str
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str
    # Позволяет принимать любые доп. поля от ТГ (типа last_name), не ломая валидацию
    model_config = ConfigDict(extra='allow')


class AuthMethodsResponse(BaseModel):
    user_id: str
    methods: list[dict]
    has_password: bool
    verified_email: str | None = None


class EmailRegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None


class EmailLoginRequest(BaseModel):
    email: str
    password: str


class LinkEmailRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    new_password: str
    current_password: str | None = None


class TokenActionRequest(BaseModel):
    token: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str


class GoogleAuthRequest(BaseModel):
    provider_subject: str
    email: str | None = None
    full_name: str | None = None


class GoogleIdTokenRequest(BaseModel):
    id_token: str


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
    auth_service = build_auth_service(user_repo)
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

    return auth_service.build_auth_session(
        user_id,
        UserProfileView(
            id=user_id,
            telegram_id=telegram_id,
            username=username,
            full_name=first_name,
        ),
    ).to_dict()


@router.post("/email/register")
async def email_register(
    data: EmailRegisterRequest,
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.email_register(data.email, data.password, data.full_name)).to_dict()


@router.post("/email/login")
async def email_login(
    data: EmailLoginRequest,
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.email_login(data.email, data.password)).to_dict()


@router.post("/link/email")
async def link_email(
    data: LinkEmailRequest,
    current_user_id: str = Depends(get_current_user_id),
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.link_email(current_user_id, data.email, data.password)).to_dict()


@router.post("/email/verification/request")
async def request_email_verification(
    current_user_id: str = Depends(get_current_user_id),
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.request_email_verification(current_user_id)).to_dict()


@router.post("/email/verification/confirm", response_model=AuthMethodsResponse)
async def confirm_email_verification(
    data: TokenActionRequest,
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.confirm_email_verification(data.token)).to_dict()


@router.post("/google/login")
async def google_login(
    data: GoogleAuthRequest,
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.google_login(data.provider_subject, data.email, data.full_name)).to_dict()


@router.post("/google/login/id-token")
async def google_login_id_token(
    data: GoogleIdTokenRequest,
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.google_login_with_id_token(data.id_token)).to_dict()


@router.post("/link/google")
async def link_google(
    data: GoogleAuthRequest,
    current_user_id: str = Depends(get_current_user_id),
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.link_google(current_user_id, data.provider_subject, data.email)).to_dict()


@router.post("/link/google/id-token")
async def link_google_id_token(
    data: GoogleIdTokenRequest,
    current_user_id: str = Depends(get_current_user_id),
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.link_google_with_id_token(current_user_id, data.id_token)).to_dict()


@router.get("/me")
async def get_me(
    current_user_id: str = Depends(get_current_user_id),
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.get_current_user(current_user_id)).to_dict()


@router.get("/methods", response_model=AuthMethodsResponse)
async def get_auth_methods(
    current_user_id: str = Depends(get_current_user_id),
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.get_auth_methods(current_user_id)).to_dict()


@router.post("/password/change", response_model=AuthMethodsResponse)
async def change_password(
    data: ChangePasswordRequest,
    current_user_id: str = Depends(get_current_user_id),
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.change_password(
        current_user_id,
        data.new_password,
        current_password=data.current_password,
    )).to_dict()


@router.post("/password/reset/request")
async def request_password_reset(
    data: PasswordResetRequest,
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.request_password_reset(data.email)).to_dict()


@router.post("/password/reset/confirm")
async def confirm_password_reset(
    data: PasswordResetConfirmRequest,
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.confirm_password_reset(data.token, data.new_password)).to_dict()


@router.delete("/methods/{provider}", response_model=AuthMethodsResponse)
async def unlink_auth_method(
    provider: str,
    current_user_id: str = Depends(get_current_user_id),
    user_repo: UserRepository = Depends(get_user_repository),
):
    auth_service = build_auth_service(user_repo)
    return (await auth_service.unlink_auth_method(current_user_id, provider)).to_dict()
