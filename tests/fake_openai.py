"""A tiny OpenAI-compatible server for tests: records requests and answers like Muse Spark would."""

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse


def make_server(answers: dict[str, dict], live_text: str):
    """answers: json_schema name -> object to return as JSON content."""
    app = FastAPI()
    app.state.requests = []

    def usage(prompt: int = 5000, cached: int = 4800) -> dict:
        return {
            "prompt_tokens": prompt,
            "completion_tokens": 40,
            "total_tokens": prompt + 40,
            "prompt_tokens_details": {"cached_tokens": cached},
        }

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        app.state.requests.append(body)
        if body.get("stream"):

            async def events():
                for i in range(0, len(live_text), 7):
                    chunk = {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": body["model"],
                             "choices": [{"index": 0, "delta": {"content": live_text[i:i + 7]}, "finish_reason": None}]}
                    yield f"data: {json.dumps(chunk)}\n\n"
                final = {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": body["model"],
                         "choices": [], "usage": usage()}
                yield f"data: {json.dumps(final)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(events(), media_type="text/event-stream")

        fmt = body.get("response_format") or {}
        name = fmt.get("json_schema", {}).get("name")
        content = json.dumps(answers[name]) if name else "OK"
        return JSONResponse({
            "id": "c", "object": "chat.completion", "created": 0, "model": body["model"],
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
            "usage": usage(),
        })

    return app
