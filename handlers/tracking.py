# handlers/tracking.py

import datetime
import logging
import re
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from database import Session
from models import DailyLog, User
from openai_utils import analyze_food_image, analyze_food_text, get_recommendations
from handlers.common import build_system_prompt
from handlers.history import handle_history, handle_analyze_period

logger = logging.getLogger(__name__)

# Состояния для обработки приема пищи
MEAL_TYPE = 0
MEAL_PHOTO = 1
MEAL_TEXT = 2

MEAL_TYPES = ['Завтрак', 'Обед', 'Ужин', 'Перекус', 'Физическая активность']

def format_analysis_for_user(analysis: str) -> str:
    """Форматирует анализ для вывода пользователю"""
    # Извлекаем секции из анализа
    analysis_match = re.search(r'\[АНАЛИЗ\](.*?)\[/АНАЛИЗ\]', analysis, re.DOTALL)
    nutrients_match = re.search(r'\[НУТРИЕНТЫ\](.*?)\[/НУТРИЕНТЫ\]', analysis, re.DOTALL)
    calories_match = re.search(r'\[КАЛОРИИ\](.*?)\[/КАЛОРИИ\]', analysis, re.DOTALL)
    recommendations_match = re.search(r'\[РЕКОМЕНДАЦИИ\](.*?)\[/РЕКОМЕНДАЦИИ\]', analysis, re.DOTALL)

    parts = []
    
    if analysis_match:
        analysis_text = analysis_match.group(1).strip()
        parts.append(f"📝 *Анализ:*\n{analysis_text}")
    
    if nutrients_match:
        nutrients_text = nutrients_match.group(1).strip()
        # Форматируем нутриенты
        nutrients_lines = nutrients_text.split('\n')
        formatted_nutrients = []
        for line in nutrients_lines:
            if 'Калории:' in line:
                formatted_nutrients.append(f"🔥 {line.strip()}")
            elif 'Белки:' in line:
                formatted_nutrients.append(f"🥩 {line.strip()}")
            elif 'Жиры:' in line:
                formatted_nutrients.append(f"🥑 {line.strip()}")
            elif 'Углеводы:' in line:
                formatted_nutrients.append(f"🍚 {line.strip()}")
            else:
                formatted_nutrients.append(line.strip())
        parts.append(f"📊 *Нутриенты:*\n" + "\n".join(formatted_nutrients))
    
    if calories_match:
        calories_text = calories_match.group(1).strip()
        if 'Сожжено:' in calories_text:
            parts.append(f"🏃‍♂️ *Физическая активность:*\n{calories_text}")
    
    if recommendations_match:
        recommendations_text = recommendations_match.group(1).strip()
        parts.append(f"💡 *Рекомендации:*\n{recommendations_text}")
    
    return "\n\n".join(parts)

def get_main_keyboard():
    """Возвращает основную клавиатуру для активного дня"""
    keyboard = [
        [InlineKeyboardButton("🍽 Добавить прием пищи", callback_data='add_meal'),
         InlineKeyboardButton("🏃‍♂️ Добавить активность", callback_data='add_activity')],
        [InlineKeyboardButton("💬 Задать вопрос", callback_data='ask_question'),
         InlineKeyboardButton("📊 Статистика дня", callback_data='day_stats')],
        [InlineKeyboardButton("🏁 Завершить день", callback_data='end_day')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_meal_type_keyboard():
    """Возвращает клавиатуру для выбора типа приема пищи"""
    keyboard = [
        [InlineKeyboardButton("🌅 Завтрак", callback_data='meal_type_breakfast'),
         InlineKeyboardButton("🌞 Обед", callback_data='meal_type_lunch')],
        [InlineKeyboardButton("🌙 Ужин", callback_data='meal_type_dinner'),
         InlineKeyboardButton("🍎 Перекус", callback_data='meal_type_snack')],
        [InlineKeyboardButton("↩️ Назад", callback_data='back_to_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_activity_input_keyboard():
    """Возвращает клавиатуру для ввода физической активности"""
    keyboard = [
        [InlineKeyboardButton("✍️ Написать текстом", callback_data='input_text')],
        [InlineKeyboardButton("↩️ Назад", callback_data='back_to_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_input_method_keyboard():
    """Возвращает клавиатуру для выбора способа ввода"""
    keyboard = [
        [InlineKeyboardButton("📸 Отправить фото", callback_data='input_photo'),
         InlineKeyboardButton("✍️ Написать текстом", callback_data='input_text')],
        [InlineKeyboardButton("↩️ Назад", callback_data='back_to_meal_type')]
    ]
    return InlineKeyboardMarkup(keyboard)

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
    context.user_data['daily_totals'] = {
        'calories': 0,
        'protein': 0,
        'fat': 0,
        'carbs': 0,
        'burned': 0
    }
    context.user_data['daily_goals'] = dg

    await update.message.reply_text(
        f"📅 День {context.user_data['date'].strftime('%d.%m.%Y')} начат!\n\n"
        f"Ваши цели на сегодня:\n"
        f"• Калории: {calories} ккал\n"
        f"• Белки: {protein}г\n"
        f"• Жиры: {fat}г\n"
        f"• Углеводы: {carbs}г",
        reply_markup=get_main_keyboard()
    )

async def end_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'date' not in context.user_data:
        message = update.message or update.callback_query.message
        await message.reply_text("❗ День ещё не начат. Используйте /start_day")
        return

    # Отправляем сообщение о подготовке итогов
    message = update.message or update.callback_query.message
    progress_message = await message.reply_text(
        "🔄 Фитоша анализирует ваш день и готовит подробный отчет...\n"
        "Это займет несколько секунд."
    )

    totals = context.user_data.get('daily_totals', {})
    goals = context.user_data.get('daily_goals', {})
    logs = context.user_data.get('logs', [])
    
    net_calories = totals.get('calories', 0) - totals.get('burned', 0)
    goal_calories = goals.get('calories', 0)
    
    # Группируем логи по типам приемов пищи
    meals_breakdown = {
        'Завтрак': {'calories': 0, 'protein': 0, 'fat': 0, 'carbs': 0, 'items': []},
        'Обед': {'calories': 0, 'protein': 0, 'fat': 0, 'carbs': 0, 'items': []},
        'Ужин': {'calories': 0, 'protein': 0, 'fat': 0, 'carbs': 0, 'items': []},
        'Перекус': {'calories': 0, 'protein': 0, 'fat': 0, 'carbs': 0, 'items': []},
        'Физическая активность': {'burned': 0, 'items': []}
    }
    
    # Анализируем логи
    logger.info(f"Начинаем анализ логов. Всего записей: {len(logs)}")
    for log in logs:
        if '[АНАЛИЗ]' in log:
            meal_type = None
            # Проверяем тип записи
            if isinstance(log, dict):
                meal_type = log.get('meal_type')
                logger.info(f"Найдена запись типа dict с meal_type: {meal_type}")
            else:
                # Если лог является строкой, ищем тип в тексте
                for type_name in meals_breakdown.keys():
                    if type_name in log:
                        meal_type = type_name
                        logger.info(f"Найдена запись типа string с meal_type: {meal_type}")
                        break
            
            if not meal_type:
                logger.warning(f"Не удалось определить тип приема пищи для записи: {log[:100]}...")
                continue

            if meal_type == 'Физическая активность':
                log_text = log if isinstance(log, str) else log.get('analysis', '')
                calories_match = re.search(r'Сожжено: (\d+)', log_text)
                if calories_match:
                    burned = int(calories_match.group(1))
                    meals_breakdown[meal_type]['burned'] += burned
                    logger.info(f"Добавлена физическая активность: {burned} ккал")
                    activity_desc = re.search(r'\[АНАЛИЗ\](.*?)\[', log_text)
                    if activity_desc:
                        meals_breakdown[meal_type]['items'].append(activity_desc.group(1).strip())
            else:
                log_text = log if isinstance(log, str) else log.get('analysis', '')
                nutrients = extract_nutrients(log_text)
                if meal_type and nutrients:
                    meals_breakdown[meal_type]['calories'] += nutrients['calories']
                    meals_breakdown[meal_type]['protein'] += nutrients['protein']
                    meals_breakdown[meal_type]['fat'] += nutrients['fat']
                    meals_breakdown[meal_type]['carbs'] += nutrients['carbs']
                    logger.info(f"Добавлен прием пищи {meal_type}: {nutrients}")
                    food_desc = re.search(r'\[АНАЛИЗ\](.*?)\[', log_text)
                    if food_desc:
                        meals_breakdown[meal_type]['items'].append(food_desc.group(1).strip())
    
    logger.info("Итоговая разбивка по приемам пищи:")
    for meal_type, data in meals_breakdown.items():
        logger.info(f"{meal_type}: {data}")
    
    # Анализируем достижение целей
    calories_diff = net_calories - goal_calories
    protein_diff = totals.get('protein', 0) - goals.get('protein', 0)
    fat_diff = totals.get('fat', 0) - goals.get('fat', 0)
    carbs_diff = totals.get('carbs', 0) - goals.get('carbs', 0)
    
    # Формируем оценку дня
    if abs(calories_diff) <= 100:  # В пределах 100 ккал считаем достижением цели
        calories_status = "✅ Цель по калориям достигнута!"
    elif calories_diff > 0:
        calories_status = f"⚠️ Превышение калорий на {calories_diff} ккал"
    else:
        calories_status = f"⚠️ Недобор калорий на {abs(calories_diff)} ккал"
    
    # Формируем детальный отчет
    summary_parts = [f"📊 *Итоги дня {context.user_data['date'].strftime('%d.%m.%Y')}*"]
    
    # Общие показатели
    summary_parts.append("\n💫 *Общие показатели:*")
    summary_parts.append(f"• Потреблено калорий: {totals.get('calories', 0)} ккал")
    summary_parts.append(f"• Сожжено калорий: {totals.get('burned', 0)} ккал")
    summary_parts.append(f"• Итого калорий: {net_calories} ккал")
    summary_parts.append(f"• Цель: {goal_calories} ккал")
    summary_parts.append(f"• {calories_status}")
    
    # Макронутриенты
    summary_parts.append("\n🔬 *Макронутриенты:*")
    summary_parts.append(f"• Белки: {totals.get('protein', 0)}г / {goals.get('protein', 0)}г")
    summary_parts.append(f"• Жиры: {totals.get('fat', 0)}г / {goals.get('fat', 0)}г")
    summary_parts.append(f"• Углеводы: {totals.get('carbs', 0)}г / {goals.get('carbs', 0)}г")
    
    # Разбивка по приемам пищи
    meals_section = []
    has_meals = False
    for meal_type, data in meals_breakdown.items():
        if meal_type != 'Физическая активность':
            if data['calories'] > 0:
                has_meals = True
                meals_section.append(f"\n*{meal_type}* ({data['calories']} ккал):")
                meals_section.append(f"• Б: {data['protein']}г, Ж: {data['fat']}г, У: {data['carbs']}г")
                if data['items']:
                    meals_section.append("• Состав: " + ", ".join(data['items']))
    
    # Добавляем секцию приемов пищи только если они есть
    if has_meals:
        summary_parts.append("\n🍽 *Приемы пищи:*")
        summary_parts.extend(meals_section)
    
    # Физическая активность
    if meals_breakdown['Физическая активность']['burned'] > 0:
        summary_parts.append("\n🏃‍♂️ *Физическая активность:*")
        summary_parts.append(f"• Всего сожжено: {meals_breakdown['Физическая активность']['burned']} ккал")
        if meals_breakdown['Физическая активность']['items']:
            summary_parts.append("• Активности: " + "\n  ▫️ ".join([''] + meals_breakdown['Физическая активность']['items']))
    
    summary = "\n".join(summary_parts)

    # Получаем рекомендации на основе итогов дня
    formatted_logs = []
    for log in context.user_data.get('logs', []):
        if isinstance(log, dict):
            formatted_logs.append(log.get('analysis', ''))
        else:
            formatted_logs.append(log)

    recommendations = await get_recommendations(
        context.user_data['system_prompt'],
        formatted_logs,
        summary
    )

    formatted_recommendations = format_analysis_for_user(recommendations)

    # Сохраняем итоги дня
    session = Session()
    session.add(DailyLog(
        telegram_id=update.effective_user.id,
        date=context.user_data['date'],
        time=datetime.datetime.now(),
        data={
            'type': 'day_end',
            'summary': summary,
            'recommendations': recommendations,
            'totals': totals,
            'goals': goals,
            'meals_breakdown': meals_breakdown
        }
    ))
    session.commit()
    session.close()

    message = update.message or update.callback_query.message
    await message.reply_text(
        f"{summary}\n\n"
        f"💡 *Рекомендации:*\n{formatted_recommendations}",
        parse_mode='Markdown',
        reply_markup=None
    )

    # Очищаем данные дня
    context.user_data.clear()

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'add_meal':
        await query.message.edit_text(
            "Выберите тип приема пищи:",
            reply_markup=get_meal_type_keyboard()
        )
        return MEAL_TYPE
    elif query.data == 'add_activity':
        context.user_data['meal_type'] = 'Физическая активность'
        context.user_data['expecting_text'] = True
        await query.message.edit_text(
            "✍️ Опишите вашу физическую активность (например: '30 минут бега' или '1 час плавания')"
        )
        return MEAL_TEXT
    elif query.data.startswith('meal_type_'):
        meal_type = query.data.replace('meal_type_', '')
        meal_types = {
            'breakfast': 'Завтрак',
            'lunch': 'Обед',
            'dinner': 'Ужин',
            'snack': 'Перекус'
        }
        context.user_data['meal_type'] = meal_types[meal_type]
        await query.message.edit_text(
            "Как вы хотите добавить запись?",
            reply_markup=get_input_method_keyboard()
        )
        return MEAL_PHOTO
    elif query.data.startswith('input_'):
        input_type = query.data.replace('input_', '')
        if input_type == 'photo':
            await query.message.edit_text(
                "📸 Пожалуйста, отправьте фото блюда"
            )
            context.user_data['expecting_photo'] = True
            return MEAL_PHOTO
        else:  # text
            await query.message.edit_text(
                "✍️ Пожалуйста, опишите блюдо текстом"
            )
            context.user_data['expecting_text'] = True
            return MEAL_TEXT
    elif query.data == 'back_to_main':
        await query.message.edit_text(
            "Выберите действие:",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
    elif query.data == 'back_to_meal_type':
        await query.message.edit_text(
            "Выберите тип приема пищи:",
            reply_markup=get_meal_type_keyboard()
        )
        return MEAL_TYPE
    elif query.data == 'day_stats':
        await show_day_stats(update, context)
    elif query.data == 'ask_question':
        await query.message.edit_text(
            "💬 Задайте ваш вопрос, и я постараюсь помочь"
        )
        context.user_data['expecting_question'] = True
    elif query.data == 'start_day':
        await start_day(update, context)
    elif query.data == 'end_day':
        await end_day(update, context)
    elif query.data == 'get_advice':
        await get_current_advice(update, context)

async def get_current_advice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить рекомендации на основе текущих данных за день"""
    if 'date' not in context.user_data:
        await update.callback_query.message.reply_text(
            "❗ День ещё не начат. Используйте /start_day"
        )
        return

    await update.callback_query.message.reply_text("🤔 Анализирую ваш день...")

    totals = context.user_data.get('daily_totals', {})
    goals = context.user_data.get('daily_goals', {})
    
    current_status = (
        f"Текущие показатели:\n"
        f"Калории: {totals.get('calories', 0)}/{goals.get('calories', 0)} ккал\n"
        f"Белки: {totals.get('protein', 0)}/{goals.get('protein', 0)}г\n"
        f"Жиры: {totals.get('fat', 0)}/{goals.get('fat', 0)}г\n"
        f"Углеводы: {totals.get('carbs', 0)}/{goals.get('carbs', 0)}г\n"
        f"Сожжено калорий: {totals.get('burned', 0)} ккал"
    )

    recommendations = await get_recommendations(
        context.user_data['system_prompt'],
        context.user_data['logs'],
        current_status
    )

    await update.callback_query.message.reply_text(
        f"📊 {current_status}\n\n"
        f"💡 Рекомендации:\n{recommendations}",
        reply_markup=get_main_keyboard()
    )

async def start_meal_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'date' not in context.user_data:
        message = update.message or update.callback_query.message
        await message.reply_text("❗ Сначала начните день командой /start_day")
        return ConversationHandler.END

    reply_keyboard = [[t] for t in MEAL_TYPES]
    message = update.message or update.callback_query.message
    await message.reply_text(
        "Выберите тип записи:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return MEAL_TYPE

async def handle_meal_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора типа приема пищи"""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        meal_type = query.data.replace('meal_type_', '')
        meal_types = {
            'breakfast': 'Завтрак',
            'lunch': 'Обед',
            'dinner': 'Ужин',
            'snack': 'Перекус'
        }
        context.user_data['meal_type'] = meal_types[meal_type]
        await query.message.edit_text(
            "Как вы хотите добавить запись?",
            reply_markup=get_input_method_keyboard()
        )
        return MEAL_PHOTO
    else:
        meal_type = update.message.text
        if meal_type not in MEAL_TYPES:
            await update.message.reply_text(
                "❗ Пожалуйста, выберите тип из предложенных вариантов",
                reply_markup=get_meal_type_keyboard()
            )
            return MEAL_TYPE
        
        context.user_data['meal_type'] = meal_type
        
        if meal_type == 'Физическая активность':
            await update.message.reply_text(
                "Опишите вашу физическую активность:",
                reply_markup=ReplyKeyboardRemove()
            )
            return MEAL_TEXT
        else:
            await update.message.reply_text(
                "Как вы хотите добавить запись?",
                reply_markup=get_input_method_keyboard()
            )
            return MEAL_PHOTO

async def handle_input_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора способа ввода"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'input_photo':
        await query.message.edit_text(
            "📸 Отправьте фото блюда"
        )
        context.user_data['expecting_photo'] = True
        return MEAL_PHOTO
    else:  # input_text
        await query.message.edit_text(
            "✍️ Опишите блюдо текстом"
        )
        context.user_data['expecting_text'] = True
        return MEAL_TEXT

async def show_day_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику текущего дня"""
    if 'date' not in context.user_data:
        await update.callback_query.message.edit_text(
            "❗ День ещё не начат. Используйте /start_day",
            reply_markup=get_main_keyboard()
        )
        return

    totals = context.user_data.get('daily_totals', {})
    goals = context.user_data.get('daily_goals', {})
    
    net_calories = totals.get('calories', 0) - totals.get('burned', 0)
    goal_calories = goals.get('calories', 0)
    
    # Формируем упрощенный отчет
    stats = [f"📊 Статистика на {context.user_data['date'].strftime('%d.%m.%Y')}:"]
    
    # Общие показатели
    stats.append("\n💫 *Общие показатели:*")
    stats.append(f"• Потреблено калорий: {totals.get('calories', 0)} ккал")
    stats.append(f"• Сожжено калорий: {totals.get('burned', 0)} ккал")
    stats.append(f"• Итого калорий: {net_calories} ккал")
    stats.append(f"• Цель: {goal_calories} ккал")
    
    # Макронутриенты
    stats.append("\n🔬 *Макронутриенты:*")
    stats.append(f"• Белки: {totals.get('protein', 0)}г / {goals.get('protein', 0)}г")
    stats.append(f"• Жиры: {totals.get('fat', 0)}г / {goals.get('fat', 0)}г")
    stats.append(f"• Углеводы: {totals.get('carbs', 0)}г / {goals.get('carbs', 0)}г")

    await update.callback_query.message.edit_text(
        "\n".join(stats),
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )

def clear_conversation_state(context: ContextTypes.DEFAULT_TYPE):
    """Очищает все состояния разговора из контекста"""
    keys_to_clear = ['meal_type', 'expecting_photo', 'expecting_text', 'expecting_question']
    for key in keys_to_clear:
        if key in context.user_data:
            del context.user_data[key]

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик фотографий еды"""
    logger.info("Получено фото от пользователя %s", update.effective_user.id)
    
    if 'date' not in context.user_data:
        logger.warning("Пользователь %s пытается отправить фото без начала дня", update.effective_user.id)
        await update.message.reply_text(
            "❗ Сначала начните день командой /start_day",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    if 'meal_type' not in context.user_data:
        logger.warning("Пользователь %s пытается отправить фото без выбора типа приема пищи", update.effective_user.id)
        await update.message.reply_text(
            "❗ Пожалуйста, сначала выберите тип приема пищи",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    # Отправляем сообщение о начале анализа
    progress_message = await update.message.reply_text(
        "🔄 Анализирую фотографию... Это может занять несколько секунд."
    )
    
    try:
        # Получаем файл фото
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        photo_url = photo_file.file_path
        
        logger.info("Начинаем анализ фото для пользователя %s (тип: %s)", 
                   update.effective_user.id, context.user_data.get('meal_type'))
        
        # Получаем анализ фото
        analysis = await analyze_food_image(
            photo_url,
            context.user_data['system_prompt'],
            [log.get('analysis', log) if isinstance(log, dict) else log for log in context.user_data.get('logs', [])],
            update.message.caption
        )
        
        logger.info("Получен анализ фото для пользователя %s", update.effective_user.id)
        
        # Обновляем статистику
        nutrients = extract_nutrients(analysis)
        update_daily_totals(context.user_data['daily_totals'], nutrients)
        
        # Сохраняем запись
        session = Session()
        log_entry = DailyLog(
            telegram_id=update.effective_user.id,
            date=context.user_data['date'],
            time=datetime.datetime.now(),
            data={
                'type': 'meal',
                'meal_type': context.user_data.get('meal_type', 'Прием пищи'),
                'analysis': analysis,
                'nutrients': nutrients,
                'photo_url': photo_url
            }
        )
        session.add(log_entry)
        session.commit()
        session.close()
        
        logger.info("Сохранена запись в БД для пользователя %s", update.effective_user.id)
        
        # Добавляем анализ в историю дня
        if 'logs' not in context.user_data:
            context.user_data['logs'] = []
        context.user_data['logs'].append({
            'type': 'meal',
            'meal_type': context.user_data.get('meal_type', 'Прием пищи'),
            'analysis': analysis
        })
        
        # Удаляем сообщение о прогрессе
        await progress_message.delete()
        
        # Форматируем и отправляем ответ
        formatted_analysis = format_analysis_for_user(analysis)
        await update.message.reply_text(
            f"✅ Запись добавлена!\n\n{formatted_analysis}",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        
        logger.info("Успешно обработано фото для пользователя %s", update.effective_user.id)
        
        # Завершаем разговор
        return ConversationHandler.END
        
    except Exception as e:
        logger.error("Ошибка при обработке фото для пользователя %s: %s", 
                    update.effective_user.id, str(e), exc_info=True)
        await progress_message.edit_text(
            "❌ Произошла ошибка при анализе фото. Пожалуйста, попробуйте еще раз."
        )
        return MEAL_PHOTO
    finally:
        # Очищаем все состояния разговора
        clear_conversation_state(context)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых описаний еды или активности"""
    if 'expecting_text' not in context.user_data and 'expecting_question' not in context.user_data:
        await update.message.reply_text(
            "❗ Пожалуйста, сначала выберите тип записи",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    # Отправляем сообщение о начале анализа
    progress_message = await update.message.reply_text(
        "🔄 Анализирую запись... Это может занять несколько секунд."
    )

    try:
        if 'expecting_question' in context.user_data:
            del context.user_data['expecting_question']
            await handle_open_query(update, context, progress_message)
            return ConversationHandler.END

        del context.user_data['expecting_text']
        
        # Получаем анализ текста
        analysis = await analyze_food_text(
            update.message.text,
            context.user_data['system_prompt'],
            [log.get('analysis', log) if isinstance(log, dict) else log for log in context.user_data.get('logs', [])]
        )
        
        # Обновляем статистику
        if context.user_data.get('meal_type') == 'Физическая активность':
            calories_burned = extract_calories_burned(analysis)
            if calories_burned > 0:
                context.user_data['daily_totals']['burned'] = \
                    context.user_data['daily_totals'].get('burned', 0) + calories_burned
                logger.info(f"Добавлена физическая активность: сожжено {calories_burned} ккал")
        else:
            nutrients = extract_nutrients(analysis)
            update_daily_totals(context.user_data['daily_totals'], nutrients)
            logger.info(f"Добавлен прием пищи {context.user_data.get('meal_type')}: {nutrients}")
        
        # Сохраняем запись
        session = Session()
        log_entry = DailyLog(
            telegram_id=update.effective_user.id,
            date=context.user_data['date'],
            time=datetime.datetime.now(),
            data={
                'type': 'activity' if context.user_data.get('meal_type') == 'Физическая активность' else 'meal',
                'meal_type': context.user_data.get('meal_type', 'Прием пищи'),
                'text': update.message.text,
                'analysis': analysis,
                'calories_burned': calories_burned if context.user_data.get('meal_type') == 'Физическая активность' else 0
            }
        )
        session.add(log_entry)
        session.commit()
        session.close()
        
        # Добавляем анализ в историю дня
        if 'logs' not in context.user_data:
            context.user_data['logs'] = []
        context.user_data['logs'].append({
            'type': 'activity' if context.user_data.get('meal_type') == 'Физическая активность' else 'meal',
            'meal_type': context.user_data.get('meal_type', 'Прием пищи'),
            'analysis': analysis,
            'calories_burned': calories_burned if context.user_data.get('meal_type') == 'Физическая активность' else 0
        })
        
        # Удаляем сообщение о прогрессе
        await progress_message.delete()
        
        # Форматируем и отправляем ответ
        formatted_analysis = format_analysis_for_user(analysis)
        
        # Формируем заголовок в зависимости от типа записи
        if context.user_data.get('meal_type') == 'Физическая активность':
            header = "🏃‍♂️ *Физическая активность добавлена!*"
        else:
            header = f"✅ *{context.user_data.get('meal_type', 'Прием пищи')} добавлен!*"
        
        await update.message.reply_text(
            f"{header}\n\n{formatted_analysis}",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        
        # Завершаем разговор
        return ConversationHandler.END
        
    except Exception as e:
        logger.error("Ошибка при обработке текста: %s", e)
        await progress_message.edit_text(
            "❌ Произошла ошибка при анализе. Пожалуйста, попробуйте еще раз."
        )
        return MEAL_TEXT
    finally:
        # Очищаем все состояния разговора
        clear_conversation_state(context)

async def handle_open_query(update: Update, context: ContextTypes.DEFAULT_TYPE, progress_message=None):
    """Обработчик открытых вопросов"""
    if 'date' not in context.user_data:
        if progress_message:
            await progress_message.delete()
        await update.message.reply_text(
            "❗ День ещё не начат. Используйте /start_day",
            reply_markup=get_main_keyboard()
        )
        return

    if not progress_message:
        progress_message = await update.message.reply_text(
            "🔄 Обрабатываю ваш вопрос... Это может занять несколько секунд."
        )

    try:
        user_query = update.message.text
        system_prompt = context.user_data['system_prompt']
        
        # Получаем текущую статистику
        totals = context.user_data.get('daily_totals', {})
        goals = context.user_data.get('daily_goals', {})
        
        net_calories = totals.get('calories', 0) - totals.get('burned', 0)
        remaining_calories = goals.get('calories', 0) - net_calories
        
        # Формируем контекст для запроса
        context_info = (
            f"Текущая статистика на сегодня:\n"
            f"- Потреблено калорий: {totals.get('calories', 0)} ккал\n"
            f"- Сожжено калорий: {totals.get('burned', 0)} ккал\n"
            f"- Осталось калорий: {remaining_calories} ккал\n"
            f"- Белки: {totals.get('protein', 0)}г / {goals.get('protein', 0)}г\n"
            f"- Жиры: {totals.get('fat', 0)}г / {goals.get('fat', 0)}г\n"
            f"- Углеводы: {totals.get('carbs', 0)}г / {goals.get('carbs', 0)}г\n"
        )
        
        # Получаем рекомендации с учетом контекста
        formatted_logs = []
        for log in context.user_data.get('logs', []):
            if isinstance(log, dict):
                formatted_logs.append(log.get('analysis', ''))
            else:
                formatted_logs.append(log)

        recommendations = await get_recommendations(
            system_prompt,
            formatted_logs,
            f"Контекст:\n{context_info}\n\nВопрос пользователя: {user_query}"
        )
        
        # Форматируем ответ
        formatted_response = format_analysis_for_user(recommendations)
        
        # Сохраняем запрос и ответ
        session = Session()
        log_entry = DailyLog(
            telegram_id=update.effective_user.id,
            date=context.user_data['date'],
            time=datetime.datetime.now(),
            data={
                'type': 'query',
                'query': user_query,
                'response': recommendations
            }
        )
        session.add(log_entry)
        session.commit()
        session.close()
        
        # Добавляем запрос в историю дня
        if 'logs' not in context.user_data:
            context.user_data['logs'] = []
        context.user_data['logs'].append(f"Вопрос: {user_query}\nОтвет: {recommendations}")
        
        # Удаляем сообщение о прогрессе
        if progress_message:
            await progress_message.delete()
        
        # Отправляем ответ с форматированием
        if formatted_response:
            await update.message.reply_text(
                f"💡 *Ответ на ваш вопрос:*\n\n{formatted_response}",
                parse_mode='Markdown',
                reply_markup=get_main_keyboard()
            )
        else:
            # Если форматированный ответ пустой, отправляем оригинальные рекомендации
            await update.message.reply_text(
                f"💡 *Ответ на ваш вопрос:*\n\n{recommendations}",
                parse_mode='Markdown',
                reply_markup=get_main_keyboard()
            )
        
    except Exception as e:
        logger.error("Ошибка при обработке запроса: %s", e)
        if progress_message:
            await progress_message.edit_text(
                "❌ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте еще раз."
            )

def extract_nutrients(analysis: str) -> dict:
    """Извлекает информацию о нутриентах из анализа"""
    try:
        # Ищем секцию с нутриентами
        start = analysis.find('[НУТРИЕНТЫ]')
        end = analysis.find('[/НУТРИЕНТЫ]')
        if start == -1 or end == -1:
            return {'calories': 0, 'protein': 0, 'fat': 0, 'carbs': 0}
        
        nutrients_text = analysis[start:end]
        
        # Извлекаем значения
        nutrients = {
            'calories': 0,
            'protein': 0,
            'fat': 0,
            'carbs': 0
        }
        
        for line in nutrients_text.split('\n'):
            line = line.strip()
            if 'Калории:' in line:
                nutrients['calories'] = int(line.split(':')[1].replace('ккал', '').strip())
            elif 'Белки:' in line:
                nutrients['protein'] = int(line.split(':')[1].replace('г', '').strip())
            elif 'Жиры:' in line:
                nutrients['fat'] = int(line.split(':')[1].replace('г', '').strip())
            elif 'Углеводы:' in line:
                nutrients['carbs'] = int(line.split(':')[1].replace('г', '').strip())
        
        return nutrients
    except Exception as e:
        logger.error("Ошибка при извлечении нутриентов: %s", e)
        return {'calories': 0, 'protein': 0, 'fat': 0, 'carbs': 0}

def extract_calories_burned(analysis: str) -> int:
    """Извлекает информацию о сожженных калориях из анализа"""
    try:
        # Ищем секцию с калориями
        start = analysis.find('[КАЛОРИИ]')
        end = analysis.find('[/КАЛОРИИ]')
        if start == -1 or end == -1:
            return 0
        
        calories_text = analysis[start:end]
        
        # Извлекаем значение
        for line in calories_text.split('\n'):
            line = line.strip()
            if 'Сожжено:' in line:
                calories = int(line.split(':')[1].replace('ккал', '').strip())
                logger.info(f"Извлечено сожженных калорий: {calories}")
                return calories
        
        return 0
    except Exception as e:
        logger.error("Ошибка при извлечении сожженных калорий: %s", e)
        return 0

def update_daily_totals(totals: dict, nutrients: dict):
    """Обновляет дневные итоги на основе новых данных"""
    for key in ('calories', 'protein', 'fat', 'carbs'):
        totals[key] = totals.get(key, 0) + nutrients.get(key, 0)
    logger.info(f"Обновлены дневные итоги: {totals}")

def register_tracking_handlers(app):
    # Конверсация для логирования приема пищи
    conv_meal = ConversationHandler(
        entry_points=[
            CommandHandler('log', start_meal_log),
            CallbackQueryHandler(handle_callback, pattern='^add_meal$')
        ],
        states={
            MEAL_TYPE: [
                CallbackQueryHandler(handle_callback, pattern='^meal_type_'),
                CallbackQueryHandler(handle_callback, pattern='^back_to_main$')
            ],
            MEAL_PHOTO: [
                MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo),
                CallbackQueryHandler(handle_callback, pattern='^input_'),
                CallbackQueryHandler(handle_callback, pattern='^back_to_meal_type$')
            ],
            MEAL_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
                CallbackQueryHandler(handle_callback, pattern='^input_'),
                CallbackQueryHandler(handle_callback, pattern='^back_to_meal_type$')
            ]
        },
        fallbacks=[
            CommandHandler('cancel', lambda u, c: ConversationHandler.END),
            CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern='^cancel$'),
            CallbackQueryHandler(handle_callback, pattern='^back_to_main$')
        ],
        per_user=True,
        name="meal_conversation"
    )

    # Конверсация для физической активности
    conv_activity = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_callback, pattern='^add_activity$')
        ],
        states={
            MEAL_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
                CallbackQueryHandler(handle_callback, pattern='^back_to_main$')
            ]
        },
        fallbacks=[
            CommandHandler('cancel', lambda u, c: ConversationHandler.END),
            CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern='^cancel$'),
            CallbackQueryHandler(handle_callback, pattern='^back_to_main$')
        ],
        per_user=True,
        name="activity_conversation"
    )

    # Регистрируем обработчики в правильном порядке
    app.add_handler(CommandHandler('start_day', start_day))
    app.add_handler(CommandHandler('end_day', end_day))
    app.add_handler(CommandHandler('history', handle_history))
    app.add_handler(CommandHandler('analyze_period', handle_analyze_period))
    app.add_handler(conv_meal)      # Сначала прием пищи
    app.add_handler(conv_activity)  # Потом активность
    app.add_handler(CallbackQueryHandler(handle_callback, pattern='^(day_stats|ask_question|start_day|end_day|get_advice)$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_open_query))
