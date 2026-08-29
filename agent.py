"""ChatGPT-агент: инструменты, безопасный калькулятор, память, чтение URL."""

from __future__ import annotations

import ast
import ipaddress
import json
import math
import operator
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

DATA_DIR = Path(__file__).resolve().parent / "data"
MEMORY_PATH = DATA_DIR / "memory.json"
MOSCOW = ZoneInfo("Europe/Moscow")

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": (
                "Считает математическое выражение. Поддерживает + - * / ** %, "
                "скобки и функции sqrt, sin, cos, tan, log, log10, exp, abs, round, pow, "
                "константы pi и e."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Выражение, например 2+2*sqrt(9)",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Текущие дата и время (Europe/Moscow, UTC+3).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Сохранить факт в долговременную память агента.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "Короткий факт, который нужно запомнить",
                    }
                },
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Вернуть все факты из долговременной памяти агента.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget",
            "description": "Удалить факт из памяти по подстроке или очистить всю память.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Подстрока для поиска. Пусто — очистить всё.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": (
                "Скачать публичную веб-страницу и вернуть её текстовое содержимое. "
                "Не использовать для частных/локальных адресов."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Полный http(s) URL"}
                },
                "required": ["url"],
            },
        },
    },
]


def default_system_prompt() -> str:
    now = datetime.now(MOSCOW).strftime("%Y-%m-%d %H:%M")
    return (
        "Ты — Пульс, персональный ИИ-агент. Мозг — ChatGPT (OpenAI). "
        "Помогаешь решать задачи: отвечаешь, считаешь, запоминаешь важное, читаешь страницы. "
        "Отвечай на языке пользователя. Будь конкретным, без воды. "
        "Если нужно посчитать, запомнить или открыть URL — вызывай инструменты, не выдумывай. "
        f"Сейчас (Москва): {now}."
    )


class _SafeCalc(ast.NodeVisitor):
    OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }
    FUNCS = {
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "abs": abs,
        "round": round,
        "pow": pow,
        "floor": math.floor,
        "ceil": math.ceil,
        "factorial": math.factorial,
    }
    NAMES = {"pi": math.pi, "e": math.e, "tau": math.tau}

    def visit(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return self.visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self.OPS:
            return self.OPS[type(node.op)](self.visit(node.left), self.visit(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in self.OPS:
            return self.OPS[type(node.op)](self.visit(node.operand))
        if isinstance(node, ast.Name) and node.id in self.NAMES:
            return self.NAMES[node.id]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = self.FUNCS.get(node.func.id)
            if not fn or node.keywords:
                raise ValueError("недопустимый вызов")
            args = [self.visit(a) for a in node.args]
            return fn(*args)
        raise ValueError("недопустимое выражение")


def calculate(expression: str) -> str:
    expr = expression.strip().replace("^", "**")
    if len(expr) > 200:
        return "Слишком длинное выражение."
    try:
        tree = ast.parse(expr, mode="eval")
        value = _SafeCalc().visit(tree)
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)
    except Exception as exc:  # noqa: BLE001
        return f"Ошибка вычисления: {exc}"


def _load_memory() -> list[dict[str, str]]:
    if not MEMORY_PATH.exists():
        return []
    try:
        data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _save_memory(items: list[dict[str, str]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def remember(fact: str) -> str:
    fact = fact.strip()
    if not fact:
        return "Пустой факт не сохранён."
    items = _load_memory()
    items.append(
        {
            "fact": fact[:2000],
            "at": datetime.now(MOSCOW).strftime("%Y-%m-%d %H:%M"),
        }
    )
    _save_memory(items)
    return f"Запомнил ({len(items)} записей): {fact[:200]}"


def recall() -> str:
    items = _load_memory()
    if not items:
        return "Память пуста."
    lines = [f"- [{i['at']}] {i['fact']}" for i in items]
    return "Память агента:\n" + "\n".join(lines)


def forget(query: str | None) -> str:
    items = _load_memory()
    if not query:
        _save_memory([])
        return "Память очищена."
    q = query.lower()
    kept = [i for i in items if q not in i["fact"].lower()]
    removed = len(items) - len(kept)
    _save_memory(kept)
    return f"Удалено записей: {removed}. Осталось: {len(kept)}."


def _host_is_private(host: str) -> bool:
    host = host.strip("[]").lower()
    if host in {"localhost", "0.0.0.0"} or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
    except ValueError:
        return False


async def fetch_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "Нужен полный http(s) URL."
    host = parsed.hostname or ""
    if _host_is_private(host):
        return "Частные и локальные адреса запрещены."
    headers = {"User-Agent": "PulsAgent/1.0 (+https://local)"}
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, max_redirects=3) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        return f"Не удалось открыть страницу: {exc}"
    if response.status_code >= 400:
        return f"HTTP {response.status_code}"
    content_type = response.headers.get("content-type", "")
    text = response.text[:80_000]
    if "html" in content_type.lower() or text.lstrip()[:15].lower().startswith("<!doctype") or "<html" in text[:200].lower():
        text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
        text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;|&amp;|&lt;|&gt;|&quot;|&#39;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
    return text[:8000] or "Пустая страница."


async def execute_tool(name: str, arguments_json: str) -> str:
    try:
        args = json.loads(arguments_json or "{}")
        if not isinstance(args, dict):
            args = {}
    except json.JSONDecodeError:
        args = {}

    if name == "calculator":
        return calculate(str(args.get("expression", "")))
    if name == "get_current_datetime":
        return datetime.now(MOSCOW).strftime("%Y-%m-%d %H:%M:%S %Z")
    if name == "remember":
        return remember(str(args.get("fact", "")))
    if name == "recall":
        return recall()
    if name == "forget":
        return forget(args.get("query"))
    if name == "fetch_url":
        return await fetch_url(str(args.get("url", "")))
    return f"Неизвестный инструмент: {name}"
