"""
OSCAR API Server — FastAPI endpoints for the GitHub coding assistant.

Wraps the Asterix-based OSCAR agent for consumption by the VS Code extension.
Start with: oscar-server  (or: uvicorn oscar.api.server:app --port 8420)
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import asyncio
import importlib.metadata as importlib_metadata
import json
from pathlib import Path
import tomllib
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

from oscar.config.settings import settings
from oscar.core.agent import get_agent, get_last_step
from oscar.logging_config import configure_logging
from oscar.tools.git_tool import (
    git_branches,
    git_compare,
    git_review,
    git_status,
)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


class HistoryEntry(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None


class CompareRequest(BaseModel):
    base: str = "main"
    head: str


class ReviewRequest(BaseModel):
    branch: str
    base: str = "main"


class GitResponse(BaseModel):
    success: bool
    output: str
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# App lifespan — initialise agent once on startup
# ---------------------------------------------------------------------------

_agent = None
_chat_executor: Optional[ThreadPoolExecutor] = None


def _get_package_version() -> str:
    """Return installed package version, falling back to pyproject.toml."""
    try:
        return importlib_metadata.version("oscar-agent")
    except importlib_metadata.PackageNotFoundError:
        try:
            pyproject_path = Path(__file__).resolve().parents[3] / "pyproject.toml"
            with open(pyproject_path, "rb") as handle:
                data = tomllib.load(handle)
            return data.get("project", {}).get("version", "unknown")
        except Exception:
            return "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent, _chat_executor

    configure_logging()
    _agent = get_agent()
    _chat_executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="oscar-chat"
    )
    try:
        yield
    finally:
        if _chat_executor is not None:
            _chat_executor.shutdown(wait=False, cancel_futures=True)
            _chat_executor = None


app = FastAPI(
    title="OSCAR API",
    description="GitHub-Specialized AI Coding Assistant",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    try:
        status = git_status()
        git_ok = not status.startswith("Error")
    except Exception:
        git_ok = False

    return {
        "status": "ok",
        "version": _get_package_version(),
        "agent_ready": _agent is not None,
        "git_available": git_ok,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if _agent is None or _chat_executor is None:
        raise HTTPException(503, "Agent not initialized")
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            _chat_executor, _agent.chat, req.message
        )
        return ChatResponse(response=response)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE streaming endpoint — sends step-by-step progress events."""
    if _agent is None or _chat_executor is None:
        raise HTTPException(503, "Agent not initialized")

    _result = {"done": False, "response": "", "error": None}

    def _run_chat():
        try:
            _result["response"] = _agent.chat(req.message)
        except Exception as e:
            _result["error"] = str(e)
        finally:
            _result["done"] = True

    async def _event_generator():
        loop = asyncio.get_event_loop()
        loop.run_in_executor(_chat_executor, _run_chat)

        last_sent = {}
        while not _result["done"]:
            step = get_last_step()
            if step and step != last_sent:
                last_sent = step.copy()
                # Format step info as readable label for the UI
                tool_names = step.get('tool_names', step.get('tool_calls', []))
                step_num = step.get('step_number', step.get('step', '?'))
                max_steps = step.get('max_steps', '?')
                label = f"Step {step_num}/{max_steps}"
                if tool_names:
                    label += f": {', '.join(tool_names) if isinstance(tool_names, list) else tool_names}"
                yield f"data: {json.dumps({'type': 'step', 'data': label})}\n\n"
            await asyncio.sleep(0.3)

        if _result["error"]:
            yield f"data: {json.dumps({'type': 'error', 'data': _result['error']})}\n\n"
        else:
            # Send the response text first, then signal done
            yield f"data: {json.dumps({'type': 'response', 'data': _result['response']})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(_event_generator(), media_type="text/event-stream")


@app.get("/history", response_model=List[HistoryEntry])
async def history():
    if _agent is None:
        raise HTTPException(503, "Agent not initialized")
    try:
        entries = []
        for item in _agent.conversation_history[-20:]:
            if isinstance(item, dict):
                entries.append(
                    HistoryEntry(
                        role=str(item.get("role", "")),
                        content=str(item.get("content", "")),
                        timestamp=item.get("timestamp"),
                    )
                )
                continue

            entries.append(
                HistoryEntry(
                    role=str(getattr(item, "role", "")),
                    content=str(getattr(item, "content", "")),
                    timestamp=getattr(item, "timestamp", None),
                )
            )
        return entries
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/branches")
async def branches():
    raw = git_branches()
    if raw.startswith("Error"):
        raise HTTPException(500, raw)

    # Parse branch names from git output
    branch_list = []
    current = ""
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("* "):
            name = line[2:].strip()
            current = name
            branch_list.append(name)
        elif "->" in line:
            continue  # skip HEAD -> origin/main
        else:
            # Strip remotes/origin/ prefix for cleaner display
            name = line.replace("remotes/origin/", "").strip()
            if name and name not in branch_list:
                branch_list.append(name)

    return {"branches": branch_list, "current": current}


@app.post("/compare", response_model=GitResponse)
async def compare(req: CompareRequest):
    output = git_compare(req.base, req.head)
    return GitResponse(
        success=not output.startswith("Error"),
        output=output,
        error=output if output.startswith("Error") else None,
    )


@app.post("/review", response_model=GitResponse)
async def review(req: ReviewRequest):
    output = git_review(req.branch, req.base)
    return GitResponse(
        success=not output.startswith("Error"),
        output=output,
        error=output if output.startswith("Error") else None,
    )


@app.get("/memory")
async def memory():
    if _agent is None:
        raise HTTPException(503, "Agent not initialized")
    try:
        return {
            name: block.content
            for name, block in _agent.blocks.items()
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/status")
async def status():
    if _agent is None:
        raise HTTPException(503, "Agent not initialized")
    return {
        "agent_id": _agent.id,
        "tools": [t.name for t in _agent.get_all_tools()],
        "memory_blocks": list(_agent.blocks.keys()),
        "conversation_length": len(_agent.conversation_history),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def start_server(host: Optional[str] = None, port: Optional[int] = None):
    """Start the OSCAR API server.

    Defaults bind to 127.0.0.1 (loopback only). Override via OSCAR_HOST /
    OSCAR_PORT env vars, or by passing explicit arguments.
    """
    uvicorn.run(
        app,
        host=host or settings.host,
        port=port or settings.port,
    )


if __name__ == "__main__":
    start_server()
