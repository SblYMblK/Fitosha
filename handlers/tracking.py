# handlers/tracking.py

import datetime
import logging
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes
from database import Session
from models import DailyLog, User
from openai_utils import analyze_food_image, analyze_food_text
from handlers.common import build_system_prompt

logger = logging.getLogger(__name__)

async def start_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start_day — загружает профиль пользователя и начинает новый день трекинга.
    """
    session = Session()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    session.close()

    if not user or 'daily_goals' not in user.user_info:
        await update.message.reply_text("❗ Сначала пройдите опрос командой /start")
        return

    ui = user.user_info
    h, w, a = ui['height'], ui['weight'], ui['age']
    g, goal = ui['gender'], ui['goal']
    dg = ui['daily_goals']
    calories, protein, fat, carbs = dg['calories'], dg['protein'], dg['fat'], dg['carbs']

    # Перегенерируем актуальный системный промпт
    system_prompt = build_system_prompt(h, w, a, g, goal, calories, protein, fat, carbs)
    context.user_data['system_prompt'] = system_prompt
    context.user_data['daily_goals'] = dg

    today = datetime.date.today()
    context.user_data['date'] = today
    context.user_data['logs'] = []

    await update.message.reply_text(f"📅 День {today.strftime('%d.%m.%Y')} начат!")

async def end_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /end_day — завершает день и очищает контекст.
    """
    if 'date' not in context.user_data:
        await update.message.reply_text("❗ День ещё не начат. Используйте /start_day")
        return

    await update.message.reply_text(
        "✅ День завершён! Для истории используйте /history, для анализа периода — /analyze_period"
    )
    for key in ('date', 'logs', 'system_prompt', 'daily_goals'):
        context.user_data.pop(key, None)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработка фото еды: анализ и вывод результата как обычного текста.
    """
    if 'date' not in context.user_data:
        await update.message.reply_text("❗ Сначала начните день командой /start_day")
        return

    await update.message.reply_text("🔍 Анализирую фото, подождите…")
    photo_file = await update.message.photo[-1].get_file()
    image_path = f"temp_{update.effective_user.id}.jpg"
    await photo_file.download_to_drive(image_path)

    sp = context.user_data['system_prompt']
    analysis = analyze_food_image(image_path, sp)

    # Сохраняем запись в базу
    session = Session()
    session.add(DailyLog(
        telegram_id=update.effective_user.id,
        date=context.user_data['date'],
        data={'type': 'meal', 'analysis': analysis}
    ))
    session.commit()
    session.close()

    context.user_data['logs'].append(analysis)
    logger.debug("Current logs: %s", context.user_data['logs'])

    # Отправляем plain text
    await update.message.reply_text(f"🍽 Анализ блюда:\n{analysis}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработка текстового описания еды: анализ и вывод обычного текста.
    """
    if 'date' not in context.user_data:
        await update.message.reply_text("❗ Сначала начните день командой /start_day")
        return

    user_text = update.message.text
    await update.message.reply_text("🔍 Обрабатываю описание, подождите…")

    sp = context.user_data['system_prompt']
    analysis = analyze_food_text(user_text, sp)

    session = Session()
    session.add(DailyLog(
        telegram_id=update.effective_user.id,
        date=context.user_data['date'],
        data={'type': 'meal', 'text': user_text, 'analysis': analysis}
    ))
    session.commit()
    session.close()

    context.user_data['logs'].append(analysis)
    logger.debug("Current logs: %s", context.user_data['logs'])

    await update.message.reply_text(f"🍽 Анализ блюда:\n{analysis}")

def register_tracking_handlers(app):
    """Регистрирует handlers для трекинга питания и активности."""
    app.add_handler(CommandHandler('start_day', start_day))
    app.add_handler(CommandHandler('end_day', end_day))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
