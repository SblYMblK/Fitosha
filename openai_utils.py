import logging
from openai import AsyncOpenAI
from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

async def analyze_food_image(
    image_url: str,
    system_prompt: str,
    history: list[str] | None = None,
    user_caption: str | None = None
) -> str:
    """
    Анализ фото по его публичному URL.
    - image_url: URL картинки (telegram.org/file/…)
    - system_prompt: ваш промпт
    - history: тексты прошлых ответов за день
    - user_caption: подпись к фото (если есть)
    """
    try:
        # 1) Собираем систему и историю
        messages: list[dict] = [
            {
                "role": "system", 
                "content": system_prompt + "\n\nПроанализируй фотографию еды и предоставь следующую информацию в формате:\n" +
                          "[АНАЛИЗ]\nПодробное описание блюда и его состава\n[/АНАЛИЗ]\n" +
                          "[НУТРИЕНТЫ]\nКалории: X ккал\nБелки: X г\nЖиры: X г\nУглеводы: X г\n[/НУТРИЕНТЫ]\n" +
                          "[РЕКОМЕНДАЦИИ]\nКраткие рекомендации по этому приему пищи\n[/РЕКОМЕНДАЦИИ]"
            }
        ]
        
        if history:
            for prev in history:
                messages.append({"role": "assistant", "content": prev})

        # 2) Формируем user-сообщение как массив content
        content_items: list[dict] = [
            {
                "type": "image_url", 
                "image_url": {
                    "url": image_url,
                    "detail": "high"
                }
            }
        ]
        
        if user_caption:
            content_items.append({"type": "text", "text": user_caption})

        messages.append({"role": "user", "content": content_items})

        # 3) DEBUG-лог
        logger.debug("=== analyze_food_image REQUEST ===")
        for msg in messages:
            logger.debug("%s %s", msg["role"], msg["content"] if msg["role"]!="user" else "[USER image/text items]")

        # 4) Отправляем
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )
        return resp.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error("Ошибка при анализе фото: %s", str(e), exc_info=True)
        raise


async def analyze_food_text(
    text: str,
    system_prompt: str,
    history: list[str] | None = None
) -> str:
    """
    Анализ текстового описания еды.
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        for prev in history:
            messages.append({"role": "assistant", "content": prev})
    messages.append({"role": "user", "content": text})

    logger.debug("=== analyze_food_text REQUEST ===")
    for msg in messages:
        logger.debug("%s %s", msg["role"], msg["content"])

    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=1000
    )
    return resp.choices[0].message.content.strip()


async def summarize_daily_intake(
    system_prompt: str,
    history: list[str],
    totals: dict,
    goals: dict
) -> str:
    """
    Подведение итогов дня.
    """
    summary = (
        f"Итоги дня:\n"
        f"Калории: {totals.get('calories', 0)}/{goals.get('calories', 0)} ккал\n"
        f"Белки: {totals.get('protein', 0)}/{goals.get('protein', 0)}г\n"
        f"Жиры: {totals.get('fat', 0)}/{goals.get('fat', 0)}г\n"
        f"Углеводы: {totals.get('carbs', 0)}/{goals.get('carbs', 0)}г\n"
        f"Сожжено калорий: {totals.get('burned', 0)} ккал"
    )
    
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"История за день:\n\n" + "\n\n".join(history)},
        {"role": "user", "content": f"Проанализируй день и дай рекомендации:\n{summary}"}
    ]

    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=1000
    )
    return resp.choices[0].message.content.strip()

async def get_recommendations(
    system_prompt: str,
    history: list[str] | None = None,
    query: str | None = None
) -> str:
    """
    Получение рекомендаций на основе истории и текущего запроса.
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        for prev in history:
            messages.append({"role": "assistant", "content": prev})
    if query:
        messages.append({"role": "user", "content": query})

    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=1000
    )
    return resp.choices[0].message.content.strip()
