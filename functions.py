"""Utilities for talking with an OpenAI Assistant."""

from __future__ import annotations

import os
import time
from typing import Dict

from openai import OpenAI

# Simple in-memory mapping of our session IDs to OpenAI thread IDs.
# TODO: persist this mapping to a real database.
thread_cache: Dict[str, str] = {}


def ask_openai(session_id: str, user_content: str, assistant_id: str) -> str:
    """Send a message to the OpenAI Assistant and return its reply.

    Parameters
    ----------
    session_id:
        Identifier for the chat session. Each session maps to a single
        assistant thread which is reused across calls.
    user_content:
        The text sent by the user.
    assistant_id:
        The ID of the assistant within OpenAI's platform.

    Returns
    -------
    str
        The assistant's reply as plain text.
    """

    client = OpenAI()  # uses OPENAI_API_KEY from environment

    thread_id = thread_cache.get(session_id)
    if thread_id is None:
        thread = client.beta.threads.create()
        thread_id = thread.id
        thread_cache[session_id] = thread_id
        # TODO: persist thread_id so it survives restarts.

    # Attach the user's message to the thread
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_content,
    )

    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
    )

    start = time.time()
    while run.status != "completed":
        if time.time() - start > 60:
            raise TimeoutError("Assistant response timed out")
        time.sleep(0.5)
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id, run_id=run.id
        )

    messages = client.beta.threads.messages.list(
        thread_id=thread_id, order="desc", limit=1
    )
    if messages.data:
        msg = messages.data[0]
        if msg.content and msg.content[0].type == "text":
            return msg.content[0].text.value.strip()
    return ""


if __name__ == "__main__":
    api_key = os.getenv("OPENAI_API_KEY")
    assistant_id = os.getenv("ASSISTANT_ID") or os.getenv("OPENAI_ASSISTANT_ID")
    if api_key and assistant_id:
        print(ask_openai("demo", "Hello!", assistant_id))
    else:
        print("Set OPENAI_API_KEY and ASSISTANT_ID to run this demo.")
