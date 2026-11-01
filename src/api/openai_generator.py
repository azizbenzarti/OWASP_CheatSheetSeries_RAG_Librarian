"""
OpenAI answer generator: the API's default (GENERATOR=openai, or unset).
GENERATOR=gemini switches back to src/generation/gemini.py, which is what
the earlier eval numbers in docs/ were measured with. Switched because
Gemini took 100-300s per answer with our key, vs ~3s for gpt-4o-mini.

It is a drop-in for GeminiGenerator: a callable (system_prompt, user_prompt)
-> raw model text, using the same SYSTEM_PROMPT and the same JSON schema
({"answerable", "answer"}), so answer.py's citation check and refusal rules
apply unchanged. Nothing in src/generation/ is modified.

Env: OPENAI_API_KEY, or else EMBEDDING_API_KEY (the same OpenAI key the
embeddings use); OPENAI_GENERATION_MODEL (default gpt-4o-mini).
NEVER print, log, or return the API key itself from this module.
"""
from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from ..generation.prompt import RESPONSE_SCHEMA

DEFAULT_OPENAI_GENERATION_MODEL = "gpt-4o-mini"


class OpenAIGenerator:
    def __init__(self, client: Any = None) -> None:
        load_dotenv()
        self.model = os.environ.get("OPENAI_GENERATION_MODEL") or DEFAULT_OPENAI_GENERATION_MODEL
        if client is None:
            api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EMBEDDING_API_KEY")
            if not api_key:
                raise RuntimeError("GENERATOR=openai needs OPENAI_API_KEY (or EMBEDDING_API_KEY) in .env.")
            from openai import OpenAI

            client = OpenAI(api_key=api_key, max_retries=3)  # the SDK retries 429/5xx with backoff
        self._client = client
        # Only for reasoning models (gpt-5*, o*): e.g. "minimal" keeps hidden
        # reasoning tokens -- billed as output -- and latency down.
        self.reasoning_effort = os.environ.get("OPENAI_REASONING_EFFORT") or None
        # Structured outputs' strict mode requires additionalProperties: false.
        self._schema = {**RESPONSE_SCHEMA, "additionalProperties": False}
        self.last_usage: dict[str, int] | None = None  # billed tokens of the last call, for the cost eval

    def __call__(self, system_prompt: str, user_prompt: str) -> str | None:
        extra = {"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "answer", "schema": self._schema, "strict": True},
            },
            **extra,
        )
        usage = getattr(response, "usage", None)
        self.last_usage = (
            {"input_tokens": usage.prompt_tokens, "output_tokens": usage.completion_tokens} if usage else None
        )
        # content is None on a refusal; answer.py turns that into an "I don't know".
        return response.choices[0].message.content
