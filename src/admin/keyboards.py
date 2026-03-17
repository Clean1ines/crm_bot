"""
Inline keyboard factories for the Admin Bot.
Provides reusable UI components for wizard steps and menus.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def make_main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Create the main menu inline keyboard for /start command.
    
    Returns:
        InlineKeyboardMarkup with buttons: Create Bot, My Projects, Settings, Help.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Создать бота", callback_data="newproject")],
        [InlineKeyboardButton("📦 Мои проекты", callback_data="listprojects")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
    ])


def make_project_keyboard(project_id: str) -> InlineKeyboardMarkup:
    """
    Create project management keyboard for a specific project.
    
    Args:
        project_id: UUID of the project.
    
    Returns:
        InlineKeyboardMarkup with project-specific actions.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Установить токен", callback_data=f"settoken:{project_id}")],
        [InlineKeyboardButton("👥 Менеджеры", callback_data=f"managers:{project_id}")],
        [InlineKeyboardButton("📚 Загрузить знания", callback_data=f"knowledge:{project_id}")],
        [InlineKeyboardButton("🎨 Конструктор (Pro)", callback_data=f"promode:{project_id}")],
        [InlineKeyboardButton("🗑️ Удалить проект", callback_data=f"delete:{project_id}")],
    ])


def make_template_keyboard() -> InlineKeyboardMarkup:
    """
    Create template selection keyboard for new project flow.
    
    Returns:
        InlineKeyboardMarkup with template options + skip button.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Поддержка", callback_data="tpl:support")],
        [InlineKeyboardButton("🎯 Лиды", callback_data="tpl:leads")],
        [InlineKeyboardButton("🛒 Заказы", callback_data="tpl:orders")],
        [InlineKeyboardButton("⚙️ Свой (Pro)", callback_data="tpl:custom")],
        [InlineKeyboardButton("⏭️ Пропустить", callback_data="tpl:skip")],
    ])


def make_token_help_keyboard() -> InlineKeyboardMarkup:
    """
    Create helper keyboard with token instructions link.
    
    Returns:
        InlineKeyboardMarkup with single help button.
    """
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 Как получить токен?", callback_data="help_token")
    ]])


def make_token_input_hint() -> str:
    """
    Return formatted hint text for token input step.
    
    Returns:
        Markdown-formatted instruction text.
    """
    return (
        "📌 **Как получить токен бота?**\n"
        "1. Напишите @BotFather → /newbot\n"
        "2. Скопируйте токен (вида `123456:ABCdef...`)\n"
        "3. Отправьте его мне следующим сообщением"
    )
