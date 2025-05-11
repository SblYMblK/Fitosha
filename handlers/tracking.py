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
    session = Session()
    user = session.query(User).filter_by(
        telegram_id=update.effective_user.id
    ).first()
    session.close()

    if not user or 'daily_goals' not in user.user_info:
        await update.message.reply_text("❗ Сначала пройдите опрос командой /start")
        return

    ui = user.user_info
    h, w, a = ui['height'], ui['weight'], ui['age']
    g, goal = ui['gender'], ui['goal']
    dg = ui['daily_goals']
    calories, protein, fat, carbs = (
        dg['calories'], dg['protein'], dg['fat'], dg['carbs']
    )

    system_prompt = build_system_prompt(
        h, w, a, g, goal, calories, protein, fat, carbs
    )
    context.user_data['system_prompt'] = system_prompt
    context.user_data['logs'] = []
    context.user_data['date'] = datetime.date.today()

    await update.message.reply_text(
        f"📅 День {context.user_data['date'].strftime('%d.%m.%Y')} начат!"
    )

async def end_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'date' not in context.user_data:
        await update.message.reply_text("❗ День ещё не начат. Используйте /start_day")
        return

    await update.message.reply_text(
        "✅ День завершён! Для истории используйте /history, "
        "для анализа периода — /analyze_period"
    )
    for k in ('date','logs','system_prompt','daily_goals'):
        context.user_data.pop(k, None)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'date' not in context.user_data:
        await update.message.reply_text("❗ Сначала начните день командой /start_day")
        return

    await update.message.reply_text("🔍 Анализирую фото, подождите…")

    # получаем объект File из photo или document
    file_obj = None
    if update.message.photo:
        file_obj = await update.message.photo[-1].get_file()
    elif (
        update.message.document
        and update.message.document.mime_type.startswith("image/")
    ):
        file_obj = await update.message.document.get_file()
    else:
        await update.message.reply_text("❗ Не вижу изображения в сообщении.")
        return

    # используем file_obj.file_path как готовый публичный URL
    image_url = file_obj.file_path
    logger.debug("📥 Фото URL: %s", image_url)

    caption = update.message.caption or ""
    system_prompt = context.user_data['system_prompt']
    history = context.user_data['logs']

    logger.debug(
        "Вызов analyze_food_image(url=%s, history_len=%d, caption=%r)",
        image_url, len(history), caption
    )

    analysis = await analyze_food_image(
        image_url=image_url,
        system_prompt=system_prompt,
        history=history,
        user_caption=caption
    )

    # сохраняем текст в БД
    session = Session()
    session.add(DailyLog(
        telegram_id=update.effective_user.id,
        date=context.user_data['date'],
        data={'type':'meal','analysis':analysis}
    ))
    session.commit()
    session.close()

    context.user_data['logs'].append(analysis)
    logger.debug("📖 История теперь содержит %d записей", len(context.user_data['logs']))
    await update.message.reply_text(f"🍽 Анализ блюда:\n{analysis}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'date' not in context.user_data:
        await update.message.reply_text("❗ Сначала начните день командой /start_day")
        return

    user_text = update.message.text
    await update.message.reply_text("🔍 Обрабатываю описание, подождите…")

    system_prompt = context.user_data['system_prompt']
    history = context.user_data['logs']

    logger.debug("Вызов analyze_food_text(text=%r, history_len=%d)", user_text, len(history))
    analysis = await analyze_food_text(
        text=user_text,
        system_prompt=system_prompt,
        history=history
    )

    session = Session()
    session.add(DailyLog(
        telegram_id=update.effective_user.id,
        date=context.user_data['date'],
        data={'type':'meal','text':user_text,'analysis':analysis}
    ))
    session.commit()
    session.close()

    context.user_data['logs'].append(analysis)
    logger.debug("📖 История теперь содержит %d записей", len(context.user_data['logs']))
    await update.message.reply_text(f"🍽 Анализ блюда:\n{analysis}")

def register_tracking_handlers(app):
    app.add_handler(CommandHandler('start_day', start_day))
    app.add_handler(CommandHandler('end_day',   end_day))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
