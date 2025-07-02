"""Shared utilities for Azure Functions."""

from __future__ import annotations

import os
import datetime as _dt
import hmac
import hashlib

import httpx
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()


def get_openai_client() -> AsyncOpenAI:
    """Return an OpenAI client using env vars."""
    timeout = int(os.getenv("OPENAI_TIMEOUT", "15"))
    api_key = os.getenv("OPENAI_API_KEY")
    return AsyncOpenAI(api_key=api_key, timeout=timeout)


async def nocodb_upsert(session_id: str, summary: str) -> None:
    """Upsert summary record into the NocoDB table."""
    base = os.getenv("NOCODB_API_URL")
    key = os.getenv("NOCODB_API_KEY")
    if not base or not key:
        raise RuntimeError("NocoDB configuration missing")

    headers = {"xc-token": key, "Content-Type": "application/json"}
    payload = {
        "session_id": session_id,
        "summary": summary,
        "updated_at": _dt.datetime.utcnow().isoformat(),
    }
    async with httpx.AsyncClient(timeout=10) as client:
        url = f"{base}/summaries"
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 409:
            await client.patch(f"{url}/{session_id}", json=payload, headers=headers)
        else:
            resp.raise_for_status()


def verify_signature(body: bytes, signature: str | None) -> bool:
    """Optional verification for OpenAI-Signature header."""
    secret = os.getenv("OPENAI_SIGNING_KEY")
    if not secret or not signature:
        return True
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)
