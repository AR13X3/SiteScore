"""AI analyst endpoints. The answer streams as server-sent events (see analyst/agent.py).

Without a model key (a hosted demo), the analyst replays recorded runs of its standard
questions (analyst/replay.py) and turns anything else away with a 409 the app explains.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from sitescore.analyst import ChatModel, OpenRouterModel, Toolbox, Workspace, replay, run_analyst
from sitescore.api.deps import get_store
from sitescore.datastore import DataStore
from sitescore.settings import get_settings

router = APIRouter(prefix="/api/analyst", tags=["analyst"])
StoreDep = Annotated[DataStore, Depends(get_store)]


def get_chat_model() -> ChatModel | None:
    """The configured model, or None when no OpenRouter key is set (tests override this)."""
    s = get_settings()
    return OpenRouterModel(s.openrouter_api_key, s.openrouter_model) if s.openrouter_api_key else None


ModelDep = Annotated[ChatModel | None, Depends(get_chat_model)]


@router.get("/status")
def status(model: ModelDep) -> dict:
    """mode: "live" (a model key is set), "replay" (no key, recorded runs only) or "off"."""
    recorded = [] if model else [r.summary() for r in replay.recordings()]
    mode = "live" if model else "replay" if recorded else "off"
    return {"enabled": model is not None, "mode": mode,
            "model": model.name if model else get_settings().openrouter_model,
            "provider": "OpenRouter", "replays": recorded}


class HistoryMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=60)
    workspace: Workspace = Field(default_factory=Workspace)


@router.post("/chat")
def chat(req: ChatRequest, store: StoreDep, model: ModelDep) -> StreamingResponse:
    if model is None:
        rec = replay.find(req.question, req.workspace.business_type)
        if rec is not None:
            return StreamingResponse(_sse(replay.replay(rec)), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        if replay.recordings():
            raise HTTPException(409, "This demo only replays recorded questions. To ask your own, run "
                                     "SiteScore locally with an OPENROUTER_API_KEY in .env.")
        raise HTTPException(503, "The AI analyst is off: add OPENROUTER_API_KEY to .env and restart.")
    toolbox = Toolbox(store=store, workspace=req.workspace)
    events = run_analyst(model, toolbox, [m.model_dump() for m in req.history], req.question)
    return StreamingResponse(_sse(events), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(events: Iterator[tuple[str, dict]]) -> Iterator[str]:
    for name, data in events:
        yield f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"
