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
        "status": "healthy",
        "agent_ready": _agent is not None,
        "git_available": git_ok,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if _agent is None:
        raise HTTPException(503, "Agent not initialized")
    try:
        response = _agent.chat(req.message)
        return ChatResponse(response=response)
    except Exception as e:
        raise HTTPException(500, str(e))


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
