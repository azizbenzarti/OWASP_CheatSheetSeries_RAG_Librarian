"""
Gemini as the answer generator. Only generation -- embeddings stay on the
OpenAI-compatible endpoint in src/indexing/embed.py, untouched.

Required env var (see .env.example): GEMINI_API_KEY.
Optional: GEMINI_MODEL (default "gemini-flash-latest"), GEMINI_TEMPERATURE.

NEVER print, log, or return the API key itself from this module.
"""
from __future__ import annotations

import os
import time
from typing import Any

from dotenv import load_dotenv

from .prompt import RESPONSE_SCHEMA

# An alias Google keeps pointed at its current Flash model, so it doesn't
# break when a dated model is retired. Pin an exact id in .env (e.g. from
# https://ai.google.dev/gemini-api/docs/models) when you need reproducible
# eval numbers.
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"
MAX_RETRIES = 5
RETRYABLE_STATUS_CODES = {429, 500, 503, 504}  # rate limit / transient server errors


class GeminiConfig:
    """Reads and validates the Gemini environment once, mirroring
    embed.py's EmbeddingConfig so both fail the same clear way."""

    def __init__(self) -> None:
        load_dotenv()
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.model = os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        temperature = os.environ.get("GEMINI_TEMPERATURE")
        # None = the model's own default. Google recommends leaving Gemini 3+
        # models at their default temperature, so only set this deliberately.
        self.temperature = float(temperature) if temperature else None

        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to .env (see .env.example); "
                "get a key at https://aistudio.google.com/apikey."
            )


class GeminiGenerator:
    """Callable (system_prompt, user_prompt) -> raw model text, the shape
    answer.py's Generate type expects. `client` is injectable so tests can
    pass a fake one; by default the real google-genai client is created."""

    def __init__(self, config: GeminiConfig | None = None, client: Any = None) -> None:
        self.config = config or GeminiConfig()
        self.model = self.config.model
        if client is None:
            from google import genai  # imported here so tests never need the SDK installed

            client = genai.Client(api_key=self.config.api_key)
        self._client = client

    def request_config(self, system_prompt: str) -> dict:
        # A plain dict is accepted by generate_content() in place of
        # types.GenerateContentConfig, which keeps this module SDK-import-free.
        config: dict = {
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "response_json_schema": RESPONSE_SCHEMA,
        }
        if self.config.temperature is not None:
            config["temperature"] = self.config.temperature
        return config

    def __call__(self, system_prompt: str, user_prompt: str) -> str | None:
        config = self.request_config(system_prompt)
        delay = 1.0
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.model, contents=user_prompt, config=config
                )
                # .text is None when the response was blocked or empty;
                # answer.py turns that into an "I don't know".
                return response.text
            except Exception as exc:
                # google.genai.errors.APIError carries the HTTP status as .code.
                # Checked by attribute so this module never has to import the SDK.
                if getattr(exc, "code", None) not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES:
                    raise
                time.sleep(delay)
                delay *= 2
        return None  # unreachable: the loop either returns or raises
