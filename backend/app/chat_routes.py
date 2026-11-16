"""
The chatbot endpoint. It only calls chat_service.answer, so plugging in an AI never touches this file.

    POST /api/chat     public    body: { "question": "..." }    ->  { "answer": "...", "topic": null }

One question in, one answer out. No sign-in, no history, no database, no phone ID: nothing about who
asked or what they asked is stored. The only memory is the per-IP counter for the rate limit, which
holds a hashed IP in memory and forgets it after the window.
"""
from fastapi import APIRouter, HTTPException, Request

from . import chat_service, config
from .content_schemas import ChatIn, ChatOut
from .evac_service import hash_ip
from .rate_limit import chat_limiter

router = APIRouter(tags=["chat"])


@router.post("/api/chat", response_model=ChatOut)
def ask(payload: ChatIn, request: Request):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Please type a question.")
    # Checked before the rate limit, so a question that is too long does not use up the allowance.
    if len(question) > config.CHAT_MAX_QUESTION_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Your question is too long. Please keep it under {config.CHAT_MAX_QUESTION_LENGTH} characters.",
        )

    ip = request.client.host if request.client else "unknown"
    wait = chat_limiter.check(hash_ip(ip))
    if wait is not None:
        minutes = max(1, round(wait / 60))
        raise HTTPException(
            status_code=429,
            detail=f"Too many questions from your connection. Please try again in about {minutes} minute(s).",
            headers={"Retry-After": str(wait)},
        )

    result = chat_service.answer(question)
    return ChatOut(answer=result.answer, topic=result.topic)
