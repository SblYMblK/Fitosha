# handlers/survey.py

import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
ASK_READY, ASK_HEIGHT, ASK_WEIGHT, ASK_AGE, ASK_GENDER, ASK_ACTIVITY_LEVEL, ASK_TRAINING_EXPERIENCE, ASK_GOAL = range(8)

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
        "👋 Привет! Я Фитоша – твой личный помощник в достижении фитнес-целей! 🌟\n\n"
        "Я помогу тебе:\n"
        "🎯 Достичь идеального веса\n"
        "💪 Оптимизировать питание\n"
        "📊 Отслеживать прогресс\n"
        "🏃‍♂️ Поддерживать активный образ жизни\n\n"
        "Чтобы составить индивидуальный план, мне нужно задать тебе несколько вопросов. Готов начать путь к лучшей версии себя? 😊",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return ASK_READY

async def ready_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if text != 'да':
        await update.message.reply_text(
            "Ок, возвращайся, когда будешь готов.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📏 Какой у тебя рост? (в см)",
        reply_markup=ReplyKeyboardRemove()
    )
    return ASK_HEIGHT

async def validate_number(text: str, min_value: float, max_value: float) -> tuple[bool, float]:
    """Проверяет, является ли текст допустимым числом в заданном диапазоне"""
    try:
        value = float(text)
        if min_value <= value <= max_value:
            return True, value
        return False, value
    except ValueError:
        return False, 0.0

async def ask_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Валидация роста (от 100 до 250 см)
    is_valid, height = await validate_number(update.message.text, 100, 250)
    if not is_valid:
        await update.message.reply_text(
            "⚠️ Пожалуйста, введите корректный рост в сантиметрах (от 100 до 250).\n"
            "Например: 175"
        )
        return ASK_HEIGHT

    context.user_data['height'] = height
    await update.message.reply_text("⚖️ Твой текущий вес? (в кг)")
    return ASK_WEIGHT

async def ask_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Валидация веса (от 30 до 250 кг)
    is_valid, weight = await validate_number(update.message.text, 30, 250)
    if not is_valid:
        await update.message.reply_text(
            "⚠️ Пожалуйста, введите корректный вес в килограммах (от 30 до 250).\n"
            "Например: 70"
        )
        return ASK_WEIGHT

    context.user_data['weight'] = weight
    await update.message.reply_text("🎂 Сколько тебе лет?")
    return ASK_AGE

async def ask_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Валидация возраста (от 14 до 100 лет)
    is_valid, age = await validate_number(update.message.text, 14, 100)
    if not is_valid:
        await update.message.reply_text(
            "⚠️ Пожалуйста, введите корректный возраст (от 14 до 100).\n"
            "Например: 25"
        )
        return ASK_AGE

    context.user_data['age'] = age
    reply_keyboard = [['Мужской', 'Женский']]
    await update.message.reply_text(
        "🚻 Твой пол?",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard,
            one_time_keyboard=True,
            resize_keyboard=True
        ),
    )
    return ASK_GENDER

async def ask_activity_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gender = update.message.text
    if gender not in ['Мужской', 'Женский']:
        await update.message.reply_text(
            "⚠️ Пожалуйста, выберите пол, используя кнопки.",
            reply_markup=ReplyKeyboardMarkup(
                [['Мужской', 'Женский']],
                one_time_keyboard=True,
                resize_keyboard=True
            ),
        )
        return ASK_GENDER

    context.user_data['gender'] = gender
    reply_keyboard = [
        ['Сидячий образ жизни'],
        ['Легкая активность (1-2 тренировки в неделю)'],
        ['Средняя активность (3-4 тренировки в неделю)'],
        ['Высокая активность (5+ тренировок в неделю)'],
        ['Профессиональный спортсмен']
    ]
    await update.message.reply_text(
        "🏃‍♂️ Какой у вас уровень физической активности?",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard,
            one_time_keyboard=True,
            resize_keyboard=True
        ),
    )
    return ASK_ACTIVITY_LEVEL

async def ask_training_experience(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activity_level = update.message.text
    valid_activity_levels = {
        'Сидячий образ жизни',
        'Легкая активность (1-2 тренировки в неделю)',
        'Средняя активность (3-4 тренировки в неделю)',
        'Высокая активность (5+ тренировок в неделю)',
        'Профессиональный спортсмен'
    }
    
    if activity_level not in valid_activity_levels:
        reply_keyboard = [
            ['Сидячий образ жизни'],
            ['Легкая активность (1-2 тренировки в неделю)'],
            ['Средняя активность (3-4 тренировки в неделю)'],
            ['Высокая активность (5+ тренировок в неделю)'],
            ['Профессиональный спортсмен']
        ]
        await update.message.reply_text(
            "⚠️ Пожалуйста, выберите уровень активности, используя кнопки.",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard,
                one_time_keyboard=True,
                resize_keyboard=True
            ),
        )
        return ASK_ACTIVITY_LEVEL

    context.user_data['activity_level'] = activity_level
    reply_keyboard = [['Новичок'], ['Средний уровень'], ['Продвинутый']]
    await update.message.reply_text(
        "💪 Какой у вас опыт тренировок?",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard,
            one_time_keyboard=True,
            resize_keyboard=True
        ),
    )
    return ASK_TRAINING_EXPERIENCE

async def ask_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    training_exp = update.message.text
    valid_experience_levels = {'Новичок', 'Средний уровень', 'Продвинутый'}
    
    if training_exp not in valid_experience_levels:
        reply_keyboard = [['Новичок'], ['Средний уровень'], ['Продвинутый']]
        await update.message.reply_text(
            "⚠️ Пожалуйста, выберите уровень опыта, используя кнопки.",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard,
                one_time_keyboard=True,
                resize_keyboard=True
            ),
        )
        return ASK_TRAINING_EXPERIENCE

    context.user_data['training_experience'] = training_exp
    reply_keyboard = [['Сбросить вес', 'Набрать массу', 'Поддерживать вес']]
    await update.message.reply_text(
        "🎯 Какая твоя цель?",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard,
            one_time_keyboard=True,
            resize_keyboard=True
        ),
    )
    return ASK_GOAL

async def save_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    goal = update.message.text
    valid_goals = {'Сбросить вес', 'Набрать массу', 'Поддерживать вес'}
    
    if goal not in valid_goals:
        reply_keyboard = [['Сбросить вес', 'Набрать массу', 'Поддерживать вес']]
        await update.message.reply_text(
            "⚠️ Пожалуйста, выберите цель, используя кнопки.",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard,
                one_time_keyboard=True,
                resize_keyboard=True
            ),
        )
        return ASK_GOAL

    # Сохраняем цель
    context.user_data['goal'] = goal

    # Рассчитаем дневные нормы с учетом уровня активности
    h = context.user_data['height']
    w = context.user_data['weight']
    a = context.user_data['age']
    g = context.user_data['gender']
    goal = context.user_data['goal']
    activity_level = context.user_data['activity_level']
    training_exp = context.user_data['training_experience']

    # Применяем множитель активности к базовому обмену
    activity_multipliers = {
        'Сидячий образ жизни': 1.2,
        'Легкая активность (1-2 тренировки в неделю)': 1.375,
        'Средняя активность (3-4 тренировки в неделю)': 1.55,
        'Высокая активность (5+ тренировок в неделю)': 1.725,
        'Профессиональный спортсмен': 1.9
    }
    activity_multiplier = activity_multipliers.get(activity_level, 1.2)

    calories, protein, fat, carbs = calculate_daily_goals(h, w, a, g, goal, activity_multiplier)
    system_prompt = build_system_prompt(h, w, a, g, goal, calories, protein, fat, carbs, 
                                      activity_level, training_exp)

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

    # Формируем мотивирующее сообщение в зависимости от цели
    goal_messages = {
        'Сбросить вес': (
            "🎯 На основе ваших ответов я подготовил план для здорового и устойчивого снижения веса. "
            "Умеренный дефицит калорий поможет вам достичь результата без стресса для организма."
        ),
        'Набрать массу': (
            "🎯 Судя по вашим ответам, для набора качественной мышечной массы "
            "я рассчитал оптимальный профицит калорий с акцентом на белок."
        ),
        'Поддерживать вес': (
            "🎯 Исходя из ваших данных, я подобрал сбалансированный план питания, "
            "который поможет вам поддерживать вес и улучшать композицию тела."
        )
    }

    goal_message = goal_messages.get(goal, "")

    # Уведомляем пользователя
    await update.message.reply_text(
        f"🌟 Спасибо за ваши ответы! Я, Фитоша, буду вашим персональным помощником на пути к цели.\n\n"
        f"{goal_message}\n\n"
        f"📊 Ваш индивидуальный план на день:\n"
        f"• Калории: {calories} ккал\n"
        f"• Белки: {protein}г (для поддержания и роста мышц)\n"
        f"• Жиры: {fat}г (для здоровья гормональной системы)\n"
        f"• Углеводы: {carbs}г (для энергии)\n\n"
        f"💪 Вместе мы обязательно достигнем вашей цели! "
        f"Начнем прямо сейчас?\n\n"
        f"Используйте команду /start_day чтобы начать свой первый день! 🚀",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def cancel_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Опрос отменён. Если передумаешь — напиши /start.",
        reply_markup=ReplyKeyboardRemove()  # Убираем клавиатуру
    )
    return ConversationHandler.END

def register_survey_handlers(app):
    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start_survey)],
        states={
            ASK_READY:   [MessageHandler(filters.Regex('^(Да|Нет)$'), ready_response)],
            ASK_HEIGHT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_weight)],
            ASK_WEIGHT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_age)],
            ASK_AGE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_gender)],
            ASK_GENDER:  [MessageHandler(filters.Regex('^(Мужской|Женский)$'), ask_activity_level)],
            ASK_ACTIVITY_LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_training_experience)],
            ASK_TRAINING_EXPERIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_goal)],
            ASK_GOAL:    [MessageHandler(filters.Regex('^(Сбросить вес|Набрать массу|Поддерживать вес)$'), save_survey)],
        },
        fallbacks=[CommandHandler('cancel', cancel_survey)],
        per_user=True,
    )
    app.add_handler(conv)
