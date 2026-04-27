"""
Inline keyboard factories for the platform control-plane bot.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LoginUrl

from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def make_web_panel_button() -> InlineKeyboardButton:
    base_url = settings.FRONTEND_URL
    if not base_url:
        logger.error("FRONTEND_URL or RENDER_EXTERNAL_URL is not set!")
    login_url = f"{base_url.rstrip('/')}/login" if base_url else ""
    logger.debug("Web panel button URL prepared", extra={"login_url": login_url})
    return InlineKeyboardButton(
        text="Открыть Web-панель",
        login_url=LoginUrl(
            url=login_url,
            forward_text="Войти в MRAK-OS",
            request_write_access=True,
        ),
    )


def make_main_menu_keyboard() -> InlineKeyboardMarkup:
    logger.debug("Building main menu keyboard")
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Создать проект", callback_data="newproject")],
            [InlineKeyboardButton("Мои проекты", callback_data="listprojects")],
            [make_web_panel_button()],
        ]
    )


def make_projects_list_keyboard(
    projects: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    buttons = []
    for pid, name in projects:
        buttons.append([InlineKeyboardButton(name, callback_data=f"project:{pid}")])
    buttons.append([InlineKeyboardButton("Назад", callback_data="back_to_main")])
    logger.debug("Built projects list keyboard", extra={"count": len(projects)})
    return InlineKeyboardMarkup(buttons)


def make_project_dynamic_keyboard(
    project_id: str, has_client_bot: bool, has_manager_bot: bool
) -> InlineKeyboardMarkup:
    buttons = []
    if not has_client_bot:
        buttons.append(
            [
                InlineKeyboardButton(
                    "Создать клиентского бота",
                    callback_data=f"create_client_bot:{project_id}",
                )
            ]
        )
    if not has_manager_bot:
        buttons.append(
            [
                InlineKeyboardButton(
                    "Создать менеджерского бота",
                    callback_data=f"create_manager_bot:{project_id}",
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(
                "Загрузить знания", callback_data=f"knowledge:{project_id}"
            )
        ]
    )
    if has_client_bot or has_manager_bot:
        buttons.append(
            [InlineKeyboardButton("Менеджеры", callback_data=f"managers:{project_id}")]
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    "Открепить бота", callback_data=f"detach_bot:{project_id}"
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton("Удалить проект", callback_data=f"delete:{project_id}")]
    )
    buttons.append([InlineKeyboardButton("Назад", callback_data="back_to_main")])
    logger.debug(
        "Built dynamic keyboard",
        extra={
            "project_id": project_id,
            "has_client_bot": has_client_bot,
            "has_manager_bot": has_manager_bot,
        },
    )
    return InlineKeyboardMarkup(buttons)


def make_token_help_keyboard() -> InlineKeyboardMarkup:
    logger.debug("Building token help keyboard")
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Как получить токен?", callback_data="help_token")]]
    )


def make_back_keyboard(target_callback: str = "back_to_main") -> InlineKeyboardMarkup:
    logger.debug("Building back keyboard", extra={"target_callback": target_callback})
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Назад", callback_data=target_callback)]]
    )


def make_detach_choice_keyboard(project_id: str) -> InlineKeyboardMarkup:
    logger.debug("Building detach choice keyboard", extra={"project_id": project_id})
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Клиентского", callback_data=f"detach_client:{project_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "Менеджерского", callback_data=f"detach_manager:{project_id}"
                )
            ],
            [InlineKeyboardButton("Назад", callback_data=f"project:{project_id}")],
        ]
    )
