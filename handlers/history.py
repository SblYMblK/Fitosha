# handlers/history.py

import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)
from database import Session
from models import DailyLog, User
from openai_utils import summarize_daily_intake
import calendar
import logging

# Состояния для ConversationHandler
HISTORY_DATE = 0
ANALYZE_START, ANALYZE_END = range(2)

logger = logging.getLogger(__name__)

def get_calendar_keyboard(year: int, month: int):
    """Создает клавиатуру-календарь для выбора даты"""
    keyboard = []
    
    # Заголовок с месяцем и годом
    month_name = calendar.month_name[month]
    keyboard.append([
        InlineKeyboardButton(f"◀️", callback_data=f'calendar_prev_{year}_{month}'),
        InlineKeyboardButton(f"{month_name} {year}", callback_data='ignore'),
        InlineKeyboardButton(f"▶️", callback_data=f'calendar_next_{year}_{month}')
    ])
    
    # Дни недели
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([InlineKeyboardButton(day, callback_data='ignore') for day in days])
    
    # Получаем матрицу дней месяца
    cal = calendar.monthcalendar(year, month)
    
    # Добавляем дни
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data='ignore'))
            else:
                row.append(InlineKeyboardButton(
                    str(day),
                    callback_data=f'date_{year}_{month}_{day}'
                ))
        keyboard.append(row)
    
    # Добавляем кнопку отмены
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data='cancel_history')])
    
    return InlineKeyboardMarkup(keyboard)

async def history_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало просмотра истории"""
    today = datetime.date.today()
    await update.message.reply_text(
        "📅 Выберите дату для просмотра истории:",
        reply_markup=get_calendar_keyboard(today.year, today.month)
    )
    return HISTORY_DATE

async def handle_calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки календаря"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancel_history':
        await query.message.edit_text("❌ Просмотр истории отменен")
        return ConversationHandler.END
    
    if query.data.startswith('calendar_'):
        # Обработка навигации по календарю
        _, direction, year, month = query.data.split('_')
        year, month = int(year), int(month)
        
        if direction == 'prev':
            if month == 1:
                month = 12
                year -= 1
            else:
                month -= 1
        else:  # next
            if month == 12:
                month = 1
                year += 1
            else:
                month += 1
        
        await query.message.edit_text(
            "📅 Выберите дату для просмотра истории:",
            reply_markup=get_calendar_keyboard(year, month)
        )
        return HISTORY_DATE
    
    if query.data.startswith('date_'):
        # Обработка выбора даты
        _, year, month, day = query.data.split('_')
        date = datetime.date(int(year), int(month), int(day))
        
        session = Session()
        logs = session.query(DailyLog).filter_by(
            telegram_id=update.effective_user.id,
            date=date
        ).order_by(DailyLog.time).all()
        session.close()

        if not logs:
            keyboard = [[InlineKeyboardButton("◀️ Назад к календарю", callback_data='back_to_calendar')]]
            await query.message.edit_text(
                f"📭 Нет данных за {date.strftime('%d.%m.%Y')}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return HISTORY_DATE

        parts = []
        daily_summary = None
        
        for log in logs:
            data = log.data
            time_str = log.time.strftime('%H:%M')
            
            if data['type'] == 'summary':
                daily_summary = data
                continue
                
            if data['type'] == 'meal':
                meal_type = data.get('meal_type', 'Прием пищи')
                nutrients = data.get('nutrients', {})
                parts.append(
                    f"🕐 {time_str} - {meal_type}\n"
                    f"Состав: {data['analysis']}\n"
                    f"Калории: {nutrients.get('calories', 0)} ккал\n"
                    f"Белки: {nutrients.get('protein', 0)}г\n"
                    f"Жиры: {nutrients.get('fat', 0)}г\n"
                    f"Углеводы: {nutrients.get('carbs', 0)}г\n"
                )
            elif data['type'] == 'activity':
                parts.append(
                    f"🕐 {time_str} - Физическая активность\n"
                    f"Активность: {data['activity']}\n"
                    f"Анализ: {data['analysis']}\n"
                    f"Сожжено калорий: {data.get('calories_burned', 0)} ккал\n"
                )
            elif data['type'] == 'query':
                parts.append(
                    f"🕐 {time_str} - Запрос к ассистенту\n"
                    f"Вопрос: {data['query']}\n"
                    f"Ответ: {data['response']}\n"
                )

        # Добавляем итоги дня, если есть
        if daily_summary:
            parts.append("\n" + daily_summary['summary'])
        
        report = "\n\n".join(parts)
        
        # Добавляем кнопки навигации
        keyboard = [
            [
                InlineKeyboardButton("◀️ Предыдущий день", 
                    callback_data=f'date_{(date - datetime.timedelta(days=1)).strftime("%Y_%m_%d")}'),
                InlineKeyboardButton("Следующий день ▶️", 
                    callback_data=f'date_{(date + datetime.timedelta(days=1)).strftime("%Y_%m_%d")}')
            ],
            [InlineKeyboardButton("◀️ Назад к календарю", callback_data='back_to_calendar')]
        ]
        
        await query.message.edit_text(
            f"📖 История за {date.strftime('%d.%m.%Y')}:\n\n{report}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return HISTORY_DATE
    
    if query.data == 'back_to_calendar':
        today = datetime.date.today()
        await query.message.edit_text(
            "📅 Выберите дату для просмотра истории:",
            reply_markup=get_calendar_keyboard(today.year, today.month)
        )
        return HISTORY_DATE

async def analyze_period_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало анализа периода"""
    today = datetime.date.today()
    context.user_data['analyze_period'] = {}
    await update.message.reply_text(
        "📅 Выберите начальную дату периода:",
        reply_markup=get_calendar_keyboard(today.year, today.month)
    )
    return ANALYZE_START

async def handle_analyze_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик календаря для анализа периода"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancel_history':
        await query.message.edit_text("❌ Анализ периода отменен")
        return ConversationHandler.END
    
    if query.data.startswith('calendar_'):
        # Обработка навигации по календарю
        _, direction, year, month = query.data.split('_')
        year, month = int(year), int(month)
        
        if direction == 'prev':
            if month == 1:
                month = 12
                year -= 1
            else:
                month -= 1
        else:  # next
            if month == 12:
                month = 1
                year += 1
            else:
                month += 1
        
        message = "📅 Выберите "
        message += "начальную" if context.user_data['analyze_period'].get('start_date') is None else "конечную"
        message += " дату периода:"
        
        await query.message.edit_text(
            message,
            reply_markup=get_calendar_keyboard(year, month)
        )
        return ANALYZE_START if context.user_data['analyze_period'].get('start_date') is None else ANALYZE_END
    
    if query.data.startswith('date_'):
        # Обработка выбора даты
        _, year, month, day = query.data.split('_')
        selected_date = datetime.date(int(year), int(month), int(day))
        
        if context.user_data['analyze_period'].get('start_date') is None:
            # Выбрана начальная дата
            context.user_data['analyze_period']['start_date'] = selected_date
            await query.message.edit_text(
                "📅 Выберите конечную дату периода:",
                reply_markup=get_calendar_keyboard(selected_date.year, selected_date.month)
            )
            return ANALYZE_END
        else:
            # Выбрана конечная дата
            start_date = context.user_data['analyze_period']['start_date']
            if selected_date < start_date:
                await query.message.edit_text(
                    "❗ Конечная дата не может быть раньше начальной. Выберите другую дату:",
                    reply_markup=get_calendar_keyboard(selected_date.year, selected_date.month)
                )
                return ANALYZE_END
            
            session = Session()
            logs = session.query(DailyLog).filter(
                DailyLog.telegram_id == update.effective_user.id,
                DailyLog.date >= start_date,
                DailyLog.date <= selected_date,
                DailyLog.data['type'].astext == 'summary'  # Только итоги дней
            ).order_by(DailyLog.date).all()
            session.close()

            if not logs:
                await query.message.edit_text(
                    f"📭 Нет данных за период {start_date.strftime('%d.%m.%Y')}–{selected_date.strftime('%d.%m.%Y')}.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔄 Выбрать другой период", callback_data='restart_analysis')
                    ]])
                )
                return ANALYZE_START

            # Собираем статистику по дням
            total_calories = 0
            total_burned = 0
            total_protein = 0
            total_fat = 0
            total_carbs = 0
            days_count = 0

            for log in logs:
                days_count += 1
                totals = log.data.get('totals', {})
                total_calories += totals.get('calories', 0)
                total_burned += totals.get('burned', 0)
                total_protein += totals.get('protein', 0)
                total_fat += totals.get('fat', 0)
                total_carbs += totals.get('carbs', 0)

            # Считаем средние значения
            avg_calories = total_calories / days_count if days_count > 0 else 0
            avg_burned = total_burned / days_count if days_count > 0 else 0
            avg_protein = total_protein / days_count if days_count > 0 else 0
            avg_fat = total_fat / days_count if days_count > 0 else 0
            avg_carbs = total_carbs / days_count if days_count > 0 else 0

            summary = (
                f"📊 Статистика за период {start_date.strftime('%d.%m.%Y')}–{selected_date.strftime('%d.%m.%Y')}\n"
                f"Всего дней: {days_count}\n\n"
                f"📈 Средние показатели за день:\n"
                f"🍽 Калории: {avg_calories:.1f} ккал\n"
                f"🏃‍♂️ Сожжено: {avg_burned:.1f} ккал\n"
                f"📊 Нетто калорий: {(avg_calories - avg_burned):.1f} ккал\n"
                f"🥩 Белки: {avg_protein:.1f}г\n"
                f"🥑 Жиры: {avg_fat:.1f}г\n"
                f"🍚 Углеводы: {avg_carbs:.1f}г\n\n"
                f"📊 Общие показатели за период:\n"
                f"🍽 Калории: {total_calories} ккал\n"
                f"🏃‍♂️ Сожжено: {total_burned} ккал\n"
                f"📊 Нетто калорий: {total_calories - total_burned} ккал\n"
                f"🥩 Белки: {total_protein}г\n"
                f"🥑 Жиры: {total_fat}г\n"
                f"🍚 Углеводы: {total_carbs}г"
            )

            keyboard = [[InlineKeyboardButton("🔄 Выбрать другой период", callback_data='restart_analysis')]]
            await query.message.edit_text(
                summary,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ANALYZE_START
    
    if query.data == 'restart_analysis':
        context.user_data['analyze_period'] = {}
        today = datetime.date.today()
        await query.message.edit_text(
            "📅 Выберите начальную дату периода:",
            reply_markup=get_calendar_keyboard(today.year, today.month)
        )
        return ANALYZE_START

async def handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /history"""
    # Отправляем сообщение о начале обработки
    progress_message = await update.message.reply_text(
        "🔄 Загружаю историю... Это может занять несколько секунд."
    )

    try:
        # Получаем историю из БД
        session = Session()
        logs = session.query(DailyLog).filter(
            DailyLog.telegram_id == update.effective_user.id
        ).order_by(DailyLog.date.desc()).limit(7).all()
        session.close()

        if not logs:
            await progress_message.edit_text(
                "📝 История пуста. Начните вести дневник питания!"
            )
            return

        # Группируем записи по дням
        days = {}
        for log in logs:
            date_str = log.date.strftime('%d.%m.%Y')
            if date_str not in days:
                days[date_str] = []
            days[date_str].append(log)

        # Формируем отчет
        report_parts = []
        for date_str, day_logs in days.items():
            day_parts = [f"\n📅 *{date_str}*"]
            
            for log in day_logs:
                data = log.data
                time_str = log.time.strftime('%H:%M')
                
                if data['type'] == 'meal':
                    meal_type = data.get('meal_type', 'Прием пищи')
                    nutrients = data.get('nutrients', {})
                    if nutrients:
                        day_parts.append(
                            f"🕐 {time_str} - {meal_type}\n"
                            f"Состав: {data.get('text', 'Нет описания')}\n"
                            f"Калории: {nutrients.get('calories', 0)} ккал\n"
                            f"Белки: {nutrients.get('protein', 0)}г\n"
                            f"Жиры: {nutrients.get('fat', 0)}г\n"
                            f"Углеводы: {nutrients.get('carbs', 0)}г"
                        )
                elif data['type'] == 'activity':
                    day_parts.append(
                        f"🕐 {time_str} - Физическая активность\n"
                        f"Описание: {data.get('text', 'Нет описания')}\n"
                        f"Сожжено калорий: {data.get('calories_burned', 0)} ккал"
                    )

            report_parts.append("\n\n".join(day_parts))

        # Удаляем сообщение о загрузке
        await progress_message.delete()

        # Отправляем отчет
        full_report = "\n\n".join(report_parts)
        await update.message.reply_text(
            f"📋 История за последние 7 дней:\n{full_report}",
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error("Ошибка при получении истории: %s", str(e), exc_info=True)
        await progress_message.edit_text(
            "❌ Произошла ошибка при загрузке истории. Пожалуйста, попробуйте позже."
        )

async def handle_analyze_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /analyze_period"""
    # Отправляем сообщение о начале анализа
    progress_message = await update.message.reply_text(
        "🔄 Анализирую данные... Это может занять несколько секунд."
    )

    try:
        # Получаем данные за последние 7 дней
        session = Session()
        logs = session.query(DailyLog).filter(
            DailyLog.telegram_id == update.effective_user.id,
            DailyLog.date >= datetime.date.today() - datetime.timedelta(days=7)
        ).order_by(DailyLog.date.asc()).all()
        session.close()

        if not logs:
            await progress_message.edit_text(
                "📝 Нет данных для анализа. Начните вести дневник питания!"
            )
            return

        # Группируем данные по дням
        days_data = {}
        for log in logs:
            date_str = log.date.strftime('%d.%m.%Y')
            if date_str not in days_data:
                days_data[date_str] = {
                    'calories': 0,
                    'protein': 0,
                    'fat': 0,
                    'carbs': 0,
                    'burned': 0
                }
            
            data = log.data
            if data['type'] == 'meal' and 'nutrients' in data:
                nutrients = data['nutrients']
                days_data[date_str]['calories'] += nutrients.get('calories', 0)
                days_data[date_str]['protein'] += nutrients.get('protein', 0)
                days_data[date_str]['fat'] += nutrients.get('fat', 0)
                days_data[date_str]['carbs'] += nutrients.get('carbs', 0)
            elif data['type'] == 'activity':
                days_data[date_str]['burned'] += data.get('calories_burned', 0)

        # Считаем средние значения
        total_days = len(days_data)
        avg_data = {
            'calories': sum(d['calories'] for d in days_data.values()) / total_days,
            'burned': sum(d['burned'] for d in days_data.values()) / total_days,
            'protein': sum(d['protein'] for d in days_data.values()) / total_days,
            'fat': sum(d['fat'] for d in days_data.values()) / total_days,
            'carbs': sum(d['carbs'] for d in days_data.values()) / total_days
        }

        # Получаем цели пользователя
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        goals = user.user_info.get('daily_goals', {})

        # Формируем отчет
        report = (
            f"📊 *Анализ за последние {total_days} дней:*\n\n"
            f"Среднее потребление в день:\n"
            f"• Калории: {int(avg_data['calories'])} ккал"
        )
        
        if goals.get('calories'):
            diff = int(goals['calories'] - (avg_data['calories'] - avg_data['burned']))
            report += f" (цель: {goals['calories']} ккал, {'+' if diff < 0 else '-'}{abs(diff)} ккал)"
        
        report += (
            f"\n• Сожжено калорий: {int(avg_data['burned'])} ккал\n"
            f"• Белки: {int(avg_data['protein'])}г"
        )
        
        if goals.get('protein'):
            diff = int(goals['protein'] - avg_data['protein'])
            report += f" (цель: {goals['protein']}г, {'+' if diff < 0 else '-'}{abs(diff)}г)"
            
        report += f"\n• Жиры: {int(avg_data['fat'])}г"
        if goals.get('fat'):
            diff = int(goals['fat'] - avg_data['fat'])
            report += f" (цель: {goals['fat']}г, {'+' if diff < 0 else '-'}{abs(diff)}г)"
            
        report += f"\n• Углеводы: {int(avg_data['carbs'])}г"
        if goals.get('carbs'):
            diff = int(goals['carbs'] - avg_data['carbs'])
            report += f" (цель: {goals['carbs']}г, {'+' if diff < 0 else '-'}{abs(diff)}г)"

        # Удаляем сообщение о загрузке
        await progress_message.delete()

        # Отправляем отчет
        await update.message.reply_text(
            report,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error("Ошибка при анализе периода: %s", str(e), exc_info=True)
        await progress_message.edit_text(
            "❌ Произошла ошибка при анализе данных. Пожалуйста, попробуйте позже."
        )

def register_history_handlers(app):
    # Конверсация для просмотра истории
    conv_hist = ConversationHandler(
        entry_points=[CommandHandler('history', history_start)],
        states={
            HISTORY_DATE: [
                CallbackQueryHandler(handle_calendar_callback, pattern='^(date_|calendar_|back_to_calendar|cancel_history)')
            ]
        },
        fallbacks=[
            CommandHandler('cancel', lambda u, c: ConversationHandler.END),
            CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern='^cancel$')
        ],
        per_message=True,
        per_user=True
    )

    # Конверсация для анализа периода
    conv_analyze = ConversationHandler(
        entry_points=[CommandHandler('analyze_period', analyze_period_start)],
        states={
            ANALYZE_START: [
                CallbackQueryHandler(handle_analyze_calendar, pattern='^(date_|calendar_|restart_analysis|cancel_history)')
            ],
            ANALYZE_END: [
                CallbackQueryHandler(handle_analyze_calendar, pattern='^(date_|calendar_|restart_analysis|cancel_history)')
            ]
        },
        fallbacks=[
            CommandHandler('cancel', lambda u, c: ConversationHandler.END),
            CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern='^cancel$')
        ],
        per_message=True,
        per_user=True
    )

    # Регистрируем обработчики в правильном порядке
    app.add_handler(conv_hist)
    app.add_handler(conv_analyze)
