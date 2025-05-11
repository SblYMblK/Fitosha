# handlers/history.py

import datetime
from telegram import Update
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)
from database import Session
from models import DailyLog
from openai_utils import summarize_daily_intake

# Состояния для ConversationHandler
HISTORY_DATE = 0
ANALYZE_START, ANALYZE_END = range(2)

async def history_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Введите дату для просмотра истории в формате ДД.MM.ГГГГ (например, 10.05.2025) или /cancel для отмены."
    )
    return HISTORY_DATE

async def history_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        date = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text(
            "❗ Неверный формат. Введите дату ещё раз (ДД.MM.ГГГГ) или /cancel."
        )
        return HISTORY_DATE

    session = Session()
    logs = session.query(DailyLog).filter_by(
        telegram_id=update.effective_user.id,
        date=date
    ).all()
    session.close()

    if not logs:
        await update.message.reply_text(f"📭 Нет данных за {date.strftime('%d.%m.%Y')}.")
    else:
        parts = []
        for idx, log in enumerate(logs, 1):
            data = log.data
            # выводим только записи с анализом еды
            if data.get("analysis"):
                parts.append(f"{idx}. {data['analysis']}")
        report = "\n\n".join(parts)
        await update.message.reply_text(
            f"📖 История за {date.strftime('%d.%m.%Y')}:\n\n{report}"
        )

    return ConversationHandler.END

async def analyze_period_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Введите начальную дату периода (ДД.MM.ГГГГ) или /cancel."
    )
    return ANALYZE_START

async def analyze_period_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        start_date = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text(
            "❗ Неверный формат. Введите начальную дату ещё раз (ДД.MM.ГГГГ)."
        )
        return ANALYZE_START

    context.user_data['analyze_start'] = start_date
    await update.message.reply_text("Теперь введите конечную дату периода (ДД.MM.ГГГГ).")
    return ANALYZE_END

async def analyze_period_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        end_date = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text(
            "❗ Неверный формат. Введите конечную дату ещё раз (ДД.MM.ГГГГ)."
        )
        return ANALYZE_END

    start_date = context.user_data.get('analyze_start')
    if end_date < start_date:
        await update.message.reply_text(
            "❗ Конечная дата раньше начальной. Введите конечную дату заново."
        )
        return ANALYZE_END

    session = Session()
    logs = session.query(DailyLog).filter(
        DailyLog.telegram_id == update.effective_user.id,
        DailyLog.date >= start_date,
        DailyLog.date <= end_date
    ).all()
    session.close()

    if not logs:
        await update.message.reply_text(
            f"📭 Нет данных за период {start_date.strftime('%d.%m.%Y')}–{end_date.strftime('%d.%m.%Y')}."
        )
        return ConversationHandler.END

    # Собираем все тексты анализа для передачи в LLM
    analyses = [log.data.get("analysis") for log in logs if log.data.get("analysis")]
    summary = summarize_daily_intake(analyses)

    await update.message.reply_text(
        f"📊 Комплексный анализ за период {start_date.strftime('%d.%m.%Y')}–"
        f"{end_date.strftime('%d.%m.%Y')}:\n\n{summary}"
    )
    return ConversationHandler.END

async def cancel_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отмена.")
    return ConversationHandler.END

def register_history_handlers(app):
    # Конверсация для /history
    conv_hist = ConversationHandler(
        entry_points=[CommandHandler('history', history_start)],
        states={
            HISTORY_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, history_date)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_history)],
        per_user=True,
    )
    # Конверсация для /analyze_period
    conv_an = ConversationHandler(
        entry_points=[CommandHandler('analyze_period', analyze_period_start)],
        states={
            ANALYZE_START: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_period_start_date)
            ],
            ANALYZE_END: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_period_end_date)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_history)],
        per_user=True,
    )
    app.add_handler(conv_hist)
    app.add_handler(conv_an)
