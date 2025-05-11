# openai_utils.py

import base64
import logging
from openai import OpenAI
from config import OPENAI_API_KEY
from prompts import AGENT_SYSTEM_PROMPT_TEMPLATE

# Инициализация клиента и логгера
client = OpenAI(api_key=OPENAI_API_KEY)
logger = logging.getLogger(__name__)

def analyze_food_image(image_path: str, system_prompt: str) -> str:
    """
    Анализирует изображение еды, логирует payload и возвращает ответ от OpenAI.
    """
    with open(image_path, "rb") as image_file:
        b64 = base64.b64encode(image_file.read()).decode("utf-8")

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ],
        },
    ]

    # Логируем payload перед отправкой
    logger.debug("=== OpenAI REQUEST (analyze_food_image) ===")
    logger.debug("Model: gpt-4o")
    logger.debug("Messages: %s", messages)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=600,
    )
    return response.choices[0].message.content

def analyze_food_text(description: str, system_prompt: str) -> str:
    """
    Анализирует текстовое описание еды, логирует payload и возвращает ответ.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": description},
    ]

    logger.debug("=== OpenAI REQUEST (analyze_food_text) ===")
    logger.debug("Model: gpt-4o")
    logger.debug("Messages: %s", messages)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=300,
    )
    return response.choices[0].message.content

def summarize_daily_intake(logs: list, system_prompt: str) -> str:
    """
    Формирует итоговый отчёт, логирует payload и возвращает ответ.
    """
    combined = "\n\n".join(logs)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": combined},
    ]

    logger.debug("=== OpenAI REQUEST (summarize_daily_intake) ===")
    logger.debug("Model: gpt-4o")
    logger.debug("Messages: %s", messages)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=400,
    )
    return response.choices[0].message.content
