# bot.py

import logging
from telegram.ext import Application, ContextTypes
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

def main() -> None:
    # 3) Создаём приложение Telegram
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()

    # 4) Регистрируем глобальный error handler
    app.add_error_handler(global_error_handler)

    # 5) Регистрируем ваши handlers
    register_survey_handlers(app)
    register_tracking_handlers(app)
    register_history_handlers(app)

    logger.info("Bot started")
    # 6) Запуск polling
    app.run_polling()

if __name__ == "__main__":
    main()
