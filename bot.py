# bot.py

import logging
import asyncio
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
import config
from handlers.survey import register_survey_handlers
from handlers.tracking import register_tracking_handlers
from handlers.history import register_history_handlers

# 1) Включаем глобальное DEBUG-логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# 2) Глобальный обработчик ошибок
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling update:", exc_info=context.error)
    if update and hasattr(update, 'effective_message'):
        await update.effective_message.reply_text(
            "Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение с помощью при команде /help"""
    help_text = (
        "🤖 *Основные команды бота:*\n\n"
        "🔹 /start - Начать работу с ботом\n"
        "🔹 /start\_day - Начать новый день\n"
        "🔹 /history - Просмотр истории питания\n"
        "🔹 /analyze\_period - Анализ за период\n"
        "🔹 /help - Показать это сообщение\n\n"
        "📝 *Во время активного дня доступно:*\n\n"
        "• Добавление приемов пищи\n"
        "• Запись физической активности\n"
        "• Получение рекомендаций\n"
        "• Просмотр статистики\n"
        "• Открытые вопросы к ассистенту\n\n"
        "ℹ️ Используйте кнопки меню для удобной навигации"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def setup_commands(application: Application) -> None:
    """Устанавливает команды бота в меню"""
    commands = [
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("start_day", "Начать новый день"),
        BotCommand("history", "Просмотр истории питания"),
        BotCommand("analyze_period", "Анализ за период"),
        BotCommand("help", "Показать помощь")
    ]
    await application.bot.set_my_commands(commands)

def run_bot():
    """Запускает бота"""
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    
    # Регистрируем глобальный error handler
    app.add_error_handler(global_error_handler)
    
    # Добавляем команду help
    app.add_handler(CommandHandler("help", help_command))
    
    # Регистрируем handlers
    register_survey_handlers(app)
    register_tracking_handlers(app)
    register_history_handlers(app)
    
    # Устанавливаем команды бота при запуске
    async def post_init(application: Application) -> None:
        await setup_commands(application)
    
    app.post_init = post_init
    
    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    run_bot()
