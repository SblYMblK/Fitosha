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
    # 1) Собираем систему и историю
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        for prev in history:
            messages.append({"role": "assistant", "content": prev})

    # 2) Формируем user-сообщение как массив content
    content_items: list[dict] = [
        {"type": "image_url", "image_url": {"url": image_url}}
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
        messages=messages
    )
    return resp.choices[0].message.content.strip()


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
        messages=messages
    )
    return resp.choices[0].message.content.strip()


async def summarize_daily_intake(analyses: list[str]) -> str:
    """
    Сводка по списку текстовых анализов.
    """
    messages = [
        {"role": "system", "content": "Ты — агрегатор и суммаризатор дневной информации о питании."},
        {"role": "user",   "content": "Сделай короткий свод по этим записям:\n\n" + "\n\n".join(analyses)},
    ]

    logger.debug("=== summarize_daily_intake REQUEST ===")
    for msg in messages:
        logger.debug("%s %s", msg["role"], msg["content"])

    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    return resp.choices[0].message.content.strip()
