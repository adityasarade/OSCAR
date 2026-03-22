"""
OSCAR API Server — FastAPI endpoints for the GitHub coding assistant.

Wraps the Asterix-based OSCAR agent for consumption by the VS Code extension.
Start with: oscar-server  (or: uvicorn oscar.api.server:app --port 8420)
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    from oscar.core.agent import get_agent

    _agent = get_agent()
    yield


app = FastAPI(
    title="OSCAR API",
    description="GitHub-Specialized AI Coding Assistant",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    from oscar.tools.git_tool import git_status

    try:
        status = git_status()
        git_ok = not status.startswith("Error")
    except Exception:
        git_ok = False

    return {
        "status": "ok",
        "agent_ready": _agent is not None,
        "git_available": git_ok,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    if _agent is None:
        raise HTTPException(503, "Agent not initialized")
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            ThreadPoolExecutor(max_workers=1), _agent.chat, req.message
        )
        return ChatResponse(response=response)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE streaming endpoint — sends step-by-step progress events."""
    import asyncio
    import json as _json
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.responses import StreamingResponse
    from oscar.core.agent import get_last_step

    if _agent is None:
        raise HTTPException(503, "Agent not initialized")

    _executor = ThreadPoolExecutor(max_workers=1)
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
        loop.run_in_executor(_executor, _run_chat)

        last_sent = {}
        while not _result["done"]:
            step = get_last_step()
            if step and step != last_sent:
                last_sent = step.copy()
                yield f"data: {_json.dumps({'type': 'step', 'data': step})}\n\n"
            await asyncio.sleep(0.3)

        if _result["error"]:
            yield f"data: {_json.dumps({'type': 'error', 'message': _result['error']})}\n\n"
        else:
            yield f"data: {_json.dumps({'type': 'done', 'response': _result['response']})}\n\n"

    return StreamingResponse(_event_generator(), media_type="text/event-stream")


@app.get("/history")
async def history():
    if _agent is None:
        raise HTTPException(503, "Agent not initialized")
    try:
        return _agent.conversation_history[-20:]
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/branches", response_model=GitResponse)
async def branches():
    from oscar.tools.git_tool import git_branches

    output = git_branches()
    return GitResponse(
        success=not output.startswith("Error"),
        output=output,
        error=output if output.startswith("Error") else None,
    )


@app.post("/compare", response_model=GitResponse)
async def compare(req: CompareRequest):
    from oscar.tools.git_tool import git_compare

    output = git_compare(req.base, req.head)
    return GitResponse(
        success=not output.startswith("Error"),
        output=output,
        error=output if output.startswith("Error") else None,
    )


@app.post("/review", response_model=GitResponse)
async def review(req: ReviewRequest):
    from oscar.tools.git_tool import git_review

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


def start_server(host: str = "0.0.0.0", port: int = 8420):
    """Start the OSCAR API server."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
