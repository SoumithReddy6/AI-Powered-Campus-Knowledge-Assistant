from __future__ import annotations

import logging
import time
from typing import Any

from campus_assistant.config import SETTINGS

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = (
    "You are a UMBC campus domain assistant. "
    "Answer only using the provided campus context. "
    "If context is insufficient, explicitly say what is missing."
)


def answer_with_domain_assistant(
    *,
    query: str,
    context: str,
    route_label: str,
) -> str | None:
    if not SETTINGS.openai_api_key:
        return None

    try:
        from openai import OpenAI
    except Exception as exc:
        logger.warning("OpenAI SDK unavailable for domain assistant path: %s", exc)
        return None

    client = OpenAI(api_key=SETTINGS.openai_api_key)
    system_prompt = SETTINGS.openai_assistant_system_prompt or _DEFAULT_SYSTEM_PROMPT
    prompt = (
        f"Route: {route_label}\n"
        f"Question: {query}\n\n"
        f"Campus Context:\n{context}\n\n"
        "Return a direct campus answer."
    )

    if SETTINGS.openai_assistant_id:
        return _assistant_api_answer(
            client=client,
            assistant_id=SETTINGS.openai_assistant_id,
            system_prompt=system_prompt,
            prompt=prompt,
        )
    return _responses_api_answer(client=client, system_prompt=system_prompt, prompt=prompt)


def _assistant_api_answer(
    *,
    client: Any,
    assistant_id: str,
    system_prompt: str,
    prompt: str,
) -> str | None:
    try:
        thread = client.beta.threads.create(
            messages=[{"role": "user", "content": prompt}]
        )
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant_id,
            instructions=system_prompt,
        )
        run = _poll_run_completion(client=client, thread_id=thread.id, run=run)
        if getattr(run, "status", "") != "completed":
            logger.warning("Assistant run did not complete. status=%s", getattr(run, "status", "unknown"))
            return None

        messages = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=15)
        for message in getattr(messages, "data", []):
            if _get_attr(message, "role") != "assistant":
                continue
            text = _extract_assistant_text(_get_attr(message, "content", []))
            if text:
                return text
        return None
    except Exception as exc:
        logger.warning("Assistant API request failed: %s", exc)
        return None


def _responses_api_answer(*, client: Any, system_prompt: str, prompt: str) -> str | None:
    try:
        response = client.responses.create(
            model=SETTINGS.openai_model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        text = _get_attr(response, "output_text", None)
        if text:
            return str(text).strip()
        return None
    except Exception as exc:
        logger.warning("Responses API request failed: %s", exc)
        return None


def _poll_run_completion(*, client: Any, thread_id: str, run: Any) -> Any:
    deadline = time.time() + SETTINGS.openai_assistant_timeout_seconds
    status = _get_attr(run, "status", "")
    while status in {"queued", "in_progress", "cancelling"} and time.time() < deadline:
        time.sleep(0.7)
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=_get_attr(run, "id"))
        status = _get_attr(run, "status", "")
    return run


def _extract_assistant_text(content_blocks: list[Any]) -> str:
    parts: list[str] = []
    for block in content_blocks or []:
        block_type = _get_attr(block, "type", "")
        if block_type != "text":
            continue
        text_obj = _get_attr(block, "text")
        value = _get_attr(text_obj, "value", "")
        if value:
            parts.append(str(value))
    return "\n".join(parts).strip()


def _get_attr(item: Any, name: str, default: Any = None) -> Any:
    if item is None:
        return default
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)
