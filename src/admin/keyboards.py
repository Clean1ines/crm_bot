"""
Inline keyboard factories for the Admin Bot.
Provides reusable UI components for the new flow.
"""

from typing import List, Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LoginUrl  # Добавлен LoginUrl
from src.core.config import settings


def make_web_panel_button() -> InlineKeyboardButton:
    """
    Создает кнопку для автоматического входа в Web-панель.
    """
    # Убедись, что в settings.PUBLIC_URL или RENDER_EXTERNAL_URL лежит адрес фронта
    base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
    login_url = f"{base_url.rstrip('/')}/login"
    
    return InlineKeyboardButton(
        text="🌐 Открыть Web-панель",
        login_url=LoginUrl(
            url=login_url,
            forward_text="Войти в MRAK-OS",
            request_write_access=True
        )
    )

def make_main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Main menu: 
    1. Создать проект
    2. Мои проекты
    3. Web-панель (авто-логин)
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Создать проект", callback_data="newproject")],
        [InlineKeyboardButton("📦 Мои проекты", callback_data="listprojects")],
        [make_web_panel_button()], # Та самая третья кнопка
    ])


def make_projects_list_keyboard(projects: List[Tuple[str, str]]) -> InlineKeyboardMarkup:
    """
    Create a keyboard with project buttons and a back button.

    Args:
        projects: List of (project_id, project_name)
    """
    buttons = []
    for pid, name in projects:
        buttons.append([InlineKeyboardButton(name, callback_data=f"project:{pid}")])
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(buttons)


def make_project_dynamic_keyboard(
    project_id: str,
    has_client_bot: bool,
    has_manager_bot: bool
) -> InlineKeyboardMarkup:
    """
    Create project management keyboard based on current bot configuration.

    Args:
        project_id: UUID of the project.
        has_client_bot: Whether client bot token is set.
        has_manager_bot: Whether manager bot token is set.
    """
    buttons = []

    # Create bot buttons if missing
    if not has_client_bot:
        buttons.append([InlineKeyboardButton("🤖 Создать клиентского бота", callback_data=f"create_client_bot:{project_id}")])
    if not has_manager_bot:
        buttons.append([InlineKeyboardButton("👥 Создать менеджерского бота", callback_data=f"create_manager_bot:{project_id}")])

    # Always show knowledge base upload button
    buttons.append([InlineKeyboardButton("📚 Загрузить знания", callback_data=f"knowledge:{project_id}")])

    # Managers and detach are shown if at least one bot exists
    if has_client_bot or has_manager_bot:
        buttons.append([InlineKeyboardButton("👥 Менеджеры", callback_data=f"managers:{project_id}")])
        buttons.append([InlineKeyboardButton("🔗 Открепить бота", callback_data=f"detach_bot:{project_id}")])

    # Always show delete and back
    buttons.append([InlineKeyboardButton("🗑️ Удалить проект", callback_data=f"delete:{project_id}")])
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])

    return InlineKeyboardMarkup(buttons)


def make_template_keyboard() -> InlineKeyboardMarkup:
    """
    Create template selection keyboard.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Support", callback_data="tpl:support")],
        [InlineKeyboardButton("🎯 Leads", callback_data="tpl:leads")],
        [InlineKeyboardButton("🛒 Orders", callback_data="tpl:orders")],
        [InlineKeyboardButton("⚙️ Custom", callback_data="tpl:custom")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_project")],  # will be overridden with actual project in handler
    ])


def make_token_help_keyboard() -> InlineKeyboardMarkup:
    """
    Keyboard with help button for token input.
    """
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 Как получить токен?", callback_data="help_token")
    ]])


def make_back_keyboard(target_callback: str = "back_to_main") -> InlineKeyboardMarkup:
    """
    Simple back button keyboard.
    """
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Назад", callback_data=target_callback)
    ]])


def make_detach_choice_keyboard(project_id: str) -> InlineKeyboardMarkup:
    """
    Keyboard for choosing which bot to detach.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Клиентского", callback_data=f"detach_client:{project_id}")],
        [InlineKeyboardButton("👥 Менеджерского", callback_data=f"detach_manager:{project_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"project:{project_id}")],
    ])
