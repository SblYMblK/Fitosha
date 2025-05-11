# handlers/common.py

from prompts import AGENT_SYSTEM_PROMPT_TEMPLATE

def calculate_daily_goals(height, weight, age, gender, goal):
    """
    Рассчитывает суточную норму калорий и макронутриентов
    по формуле Миффлина–Сан Жеора и поправке на цель.
    """
    h = float(height)
    w = float(weight)
    a = int(age)

    # BMR (Mifflin – St Jeor)
    if gender == 'Мужской':
        bmr = 10 * w + 6.25 * h - 5 * a + 5
    else:
        bmr = 10 * w + 6.25 * h - 5 * a - 161

    # Коэффициент активности (малоподвижный образ жизни)
    maintenance = bmr * 1.2

    # Корректируем по цели
    if goal == 'Сбросить вес':
        calories = maintenance - 500
    elif goal == 'Набрать массу':
        calories = maintenance + 500
    else:  # Поддерживать вес
        calories = maintenance

    # Макронутриенты: белки 1.5 г на кг, жиры 25% калорий, остальное углеводы
    protein = w * 1.5
    fat = calories * 0.25 / 9
    carbs = (calories - protein * 4 - fat * 9) / 4

    return (
        round(calories),
        round(protein),
        round(fat),
        round(carbs),
    )

def build_system_prompt(height, weight, age, gender, goal, calories, protein, fat, carbs):
    """
    Формирует персональный системный промпт для агента на основе шаблона.
    """
    return AGENT_SYSTEM_PROMPT_TEMPLATE.format(
        height=height,
        weight=weight,
        age=age,
        gender=gender,
        goal=goal,
        calories=calories,
        protein=protein,
        fat=fat,
        carbs=carbs,
    )
