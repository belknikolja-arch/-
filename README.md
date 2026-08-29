# Пульс — ИИ-агент на ChatGPT

Персональный агент с веб-интерфейсом. Мозг — официальный API OpenAI (ChatGPT), не взлом и не обход защиты.

## Что умеет

- Диалог с моделями GPT-4o / GPT-4.1 / GPT-5 (какие доступны на вашем ключе)
- Режим агента с инструментами: калькулятор, время (Москва), память, чтение публичных URL
- Поток ответа, история разговоров в браузере
- API-ключ хранится локально в браузере или в `.env`

## Запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

Откройте http://localhost:8000 (в превью Arena — адрес live preview).

1. Возьмите ключ на [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Вставьте его в «Настройки ключа»
3. Напишите задачу агенту

Опционально ключ можно положить в `.env`:

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

## Важно

Нужен аккаунт OpenAI с оплатой API. Бесплатный chat.openai.com сюда не подключается — только официальный API.
