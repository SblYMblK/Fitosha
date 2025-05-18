# handlers/common.py

from prompts import AGENT_SYSTEM_PROMPT_TEMPLATE

def calculate_daily_goals(height, weight, age, gender, goal, activity_multiplier=1.2):
    """
    Рассчитывает дневные нормы калорий и макронутриентов с учетом уровня активности
    """
    try:
        height = float(height)
        weight = float(weight)
        age = float(age)
    except ValueError:
        return 2000, 75, 60, 250  # Значения по умолчанию при ошибке

    # Формула Миффлина-Сан Жеора для расчета базового обмена веществ (BMR)
    if gender == 'Мужской':
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    # Учитываем уровень активности
    tdee = bmr * activity_multiplier

    # Корректируем калории в зависимости от цели
    if goal == 'Сбросить вес':
        calories = int(tdee * 0.85)  # Дефицит 15%
    elif goal == 'Набрать массу':
        calories = int(tdee * 1.15)  # Профицит 15%
    else:  # Поддерживать вес
        calories = int(tdee)

    # Рассчитываем макронутриенты
    if goal == 'Набрать массу':
        protein = int(2.0 * weight)  # 2г белка на кг веса
    else:
        protein = int(1.8 * weight)  # 1.8г белка на кг веса
    
    fat = int(0.8 * weight)  # 0.8г жира на кг веса
    remaining_calories = calories - (protein * 4 + fat * 9)
    carbs = int(remaining_calories / 4)  # Оставшиеся калории в углеводы

    return calories, protein, fat, carbs

def build_system_prompt(height, weight, age, gender, goal, calories, protein, fat, carbs, 
                       activity_level=None, training_exp=None):
    """
    Формирует системный промпт для GPT с учетом всех параметров пользователя
    """
    prompt = AGENT_SYSTEM_PROMPT_TEMPLATE.format(
        height=height,
        weight=weight,
        age=age,
        gender=gender,
        goal=goal,
        calories=calories,
        protein=protein,
        fat=fat,
        carbs=carbs
    )

    # Добавляем дополнительную информацию в промпт
    if activity_level:
        prompt += f"\nУровень активности: {activity_level}"
    
    if training_exp:
        prompt += f"\nОпыт тренировок: {training_exp}"

    return prompt
