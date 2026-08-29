"""Пульс — веб-сервер ИИ-агента на ChatGPT."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import APIError, AsyncOpenAI
from pydantic import BaseModel, Field

from agent import TOOLS, default_system_prompt, execute_tool

load_dotenv()

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = FastAPI(title="Пульс", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class ChatRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(default_factory=list)
    model: str = Field(default="gpt-4o-mini", max_length=80)
    system_prompt: str = Field(default="", max_length=8000)
    tools_enabled: bool = True
    temperature: float = Field(default=0.7, ge=0, le=2)


def _api_key(authorization: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        key = authorization[7:].strip()
        if key:
            return key
    env = os.getenv("OPENAI_API_KEY", "").strip()
    if env:
        return env
    raise HTTPException(status_code=401, detail="Нужен OpenAI API-ключ.")


def _sse(event: str, data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


async def _run_agent(req: ChatRequest, api_key: str) -> AsyncIterator[str]:
    client = AsyncOpenAI(api_key=api_key)
    system = req.system_prompt.strip() or default_system_prompt()
    history: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for msg in req.messages[-40:]:
        role = msg.get("role")
        content = msg.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            history.append({"role": role, "content": content})

    model = (req.model or "gpt-4o-mini").strip()[:80]
    tools = TOOLS if req.tools_enabled else None

    try:
        for _round in range(8):
            stream = await client.chat.completions.create(
                model=model,
                messages=history,
                tools=tools,
                temperature=req.temperature,
                stream=True,
            )
            content_parts: list[str] = []
            tool_acc: dict[int, dict[str, str]] = {}

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    content_parts.append(delta.content)
                    yield _sse("token", delta.content)
                if delta and delta.tool_calls:
                    for call in delta.tool_calls:
                        slot = tool_acc.setdefault(
                            call.index, {"id": "", "name": "", "arguments": ""}
                        )
                        if call.id:
                            slot["id"] = call.id
                        if call.function:
                            if call.function.name:
                                slot["name"] += call.function.name
                            if call.function.arguments:
                                slot["arguments"] += call.function.arguments

            if not tool_acc:
                break

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": "".join(content_parts) or None,
                "tool_calls": [
                    {
                        "id": t["id"],
                        "type": "function",
                        "function": {"name": t["name"], "arguments": t["arguments"]},
                    }
                    for t in tool_acc.values()
                ],
            }
            history.append(assistant_msg)

            for t in tool_acc.values():
                yield _sse(
                    "tool",
                    {"name": t["name"], "args": t["arguments"], "status": "running"},
                )
                result = await execute_tool(t["name"], t["arguments"])
                yield _sse(
                    "tool",
                    {
                        "name": t["name"],
                        "args": t["arguments"],
                        "status": "done",
                        "result": result[:1200],
                    },
                )
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": t["id"],
                        "content": result,
                    }
                )
        yield _sse("done", {"ok": True})
    except APIError as exc:
        message = getattr(exc, "message", None) or str(exc)
        status = getattr(exc, "status_code", None) or 502
        yield _sse("error", {"status": status, "message": message})
    except Exception as exc:  # noqa: BLE001
        yield _sse("error", {"status": 500, "message": str(exc)})
    finally:
        await client.close()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "name": "Пульс",
        "has_env_key": bool(os.getenv("OPENAI_API_KEY")),
        "default_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    }


@app.post("/api/chat")
async def chat(
    req: ChatRequest,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    key = _api_key(authorization)
    if not req.messages:
        raise HTTPException(status_code=400, detail="Пустой запрос.")
    return StreamingResponse(
        _run_agent(req, key),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/ping-key")
async def ping_key(authorization: str | None = Header(default=None)) -> dict[str, str]:
    key = _api_key(authorization)
    client = AsyncOpenAI(api_key=key)
    try:
        models = await client.models.list()
        names = [m.id for m in models.data if "gpt" in m.id][:8]
        return {"ok": "true", "sample": ", ".join(names) or "ok"}
    except APIError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 401), detail=str(exc)) from exc
    finally:
        await client.close()


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("server:app", host=host, port=port, reload=False)
