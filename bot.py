# bot.py

import logging
from telegram.ext import ApplicationBuilder

from config import TELEGRAM_TOKEN
from handlers.survey import register_survey_handlers
from handlers.tracking import register_tracking_handlers
from handlers.history import register_history_handlers

# Включаем подробное логирование для отладки запросов к OpenAI
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    register_survey_handlers(app)
    register_tracking_handlers(app)
    register_history_handlers(app)

    app.run_polling()

if __name__ == '__main__':
    main()
