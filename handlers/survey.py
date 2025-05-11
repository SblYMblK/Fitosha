# handlers/survey.py

import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from database import Session
from models import User
from handlers.common import calculate_daily_goals, build_system_prompt

# Уровни логирования (по желанию)
logger = logging.getLogger(__name__)

# Состояния опроса
ASK_READY, ASK_HEIGHT, ASK_WEIGHT, ASK_AGE, ASK_GENDER, ASK_GOAL = range(6)

async def start_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry point для опроса. Сначала проверяем, заполнял ли уже пользователь профиль.
    """
    session = Session()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    session.close()

    if user and user.user_info.get('system_prompt'):
        await update.message.reply_text(
            "✅ Вы уже заполнили профиль. "
            "Теперь можете сразу начать новый день командой /start_day."
        )
        return ConversationHandler.END

    reply_keyboard = [['Да', 'Нет']]
    await update.message.reply_text(
        "👋 Привет! Готов ответить на несколько вопросов?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return ASK_READY

async def ready_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if text != 'да':
        await update.message.reply_text("Ок, возвращайся, когда будешь готов.")
        return ConversationHandler.END

    await update.message.reply_text("📏 Какой у тебя рост? (в см)")
    return ASK_HEIGHT

async def ask_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # На самом деле сохраняем рост
    context.user_data['height'] = update.message.text
    await update.message.reply_text("⚖️ Твой текущий вес? (в кг)")
    return ASK_WEIGHT

async def ask_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['weight'] = update.message.text
    await update.message.reply_text("🎂 Сколько тебе лет?")
    return ASK_AGE

async def ask_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['age'] = update.message.text
    reply_keyboard = [['Мужской', 'Женский']]
    await update.message.reply_text(
        "🚻 Твой пол?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return ASK_GENDER

async def ask_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gender'] = update.message.text
    reply_keyboard = [['Сбросить вес', 'Набрать массу', 'Поддерживать вес']]
    await update.message.reply_text(
        "🎯 Какая твоя цель?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return ASK_GOAL

async def save_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Сохраняем цель
    context.user_data['goal'] = update.message.text

    # Рассчитаем дневные нормы
    h = context.user_data['height']
    w = context.user_data['weight']
    a = context.user_data['age']
    g = context.user_data['gender']
    goal = context.user_data['goal']
    calories, protein, fat, carbs = calculate_daily_goals(h, w, a, g, goal)
    system_prompt = build_system_prompt(h, w, a, g, goal, calories, protein, fat, carbs)

    # Сохраняем в БД
    session = Session()
    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
    if not user:
        user = User(telegram_id=update.effective_user.id, user_info={})
    # Обновляем данные профиля
    user.user_info.update(context.user_data)
    user.user_info['daily_goals'] = {
        'calories': calories,
        'protein': protein,
        'fat': fat,
        'carbs': carbs,
    }
    user.user_info['system_prompt'] = system_prompt
    session.add(user)
    session.commit()
    session.close()

    # Уведомляем пользователя
    await update.message.reply_text(
        f"🎉 Отлично! Твои цели на день:\n"
        f"• Калории: {calories} ккал\n"
        f"• Белки: {protein} г, Жиры: {fat} г, Углеводы: {carbs} г\n\n"
        "Теперь начни свой день командой /start_day"
    )
    return ConversationHandler.END

async def cancel_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Опрос отменён. Если передумаешь — напиши /start.")
    return ConversationHandler.END

def register_survey_handlers(app):
    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start_survey)],
        states={
            ASK_READY:   [MessageHandler(filters.Regex('^(Да|Нет)$'), ready_response)],
            ASK_HEIGHT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_weight)],
            ASK_WEIGHT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_age)],
            ASK_AGE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_gender)],
            ASK_GENDER:  [MessageHandler(filters.Regex('^(Мужской|Женский)$'), ask_goal)],
            ASK_GOAL:    [MessageHandler(filters.Regex('^(Сбросить вес|Набрать массу|Поддерживать вес)$'), save_survey)],
        },
        fallbacks=[CommandHandler('cancel', cancel_survey)],
        per_user=True,
    )
    app.add_handler(conv)
