"""Local-first LLM client.

Speaks the OpenAI-compatible chat-completions protocol against a configurable
base URL. The reference deployment is Ollama on the demo machine
(``http://localhost:11434/v1`` serving ``qwen2.5:3b-instruct``); the same code
works unchanged with LM Studio, llama.cpp's server, vLLM, or a hosted
endpoint. No cloud key is required.

Structured output strategy (small local models are not reliable JSON
emitters, so every layer assumes failure is possible):

1. Ask for JSON with the schema embedded in the prompt, requesting
   ``response_format: json_object`` when the server accepts it.
2. Extract the first balanced JSON object from the reply.
3. Validate against the target Pydantic model.
4. On failure, send one repair round-trip quoting the validation errors.
5. On repeated failure, return ``None`` — callers always hold a deterministic
   fallback, so the pipeline degrades instead of breaking.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "qwen2.5:3b-instruct"


class LLMUnavailable(RuntimeError):
    """Raised when no chat endpoint answers at the configured base URL."""


@dataclass
class LLMConfig:
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: str = "ollama"  # Ollama ignores it; other servers may not
    timeout: float = 120.0
    temperature: float = 0.2

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            base_url=os.getenv("FLEXIGRID_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            model=os.getenv("FLEXIGRID_LLM_MODEL", DEFAULT_MODEL),
            api_key=os.getenv("FLEXIGRID_LLM_API_KEY", "ollama"),
            timeout=float(os.getenv("FLEXIGRID_LLM_TIMEOUT", "120")),
            temperature=float(os.getenv("FLEXIGRID_LLM_TEMPERATURE", "0.2")),
        )


def extract_json(text: str) -> dict[str, Any] | None:
    """Return the first balanced top-level JSON object found in ``text``."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:index + 1]
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        break  # try the next opening brace
                    return parsed if isinstance(parsed, dict) else None
        start = text.find("{", start + 1)
    return None


class LocalLLM:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        self._availability: bool | None = None
        self._availability_at = 0.0
        self._lock = threading.Lock()
        self.last_error: str | None = None

    # -- availability -----------------------------------------------------
    def available(self, max_age_seconds: float = 30.0) -> bool:
        with self._lock:
            fresh = time.monotonic() - self._availability_at < max_age_seconds
            if self._availability is not None and fresh:
                return self._availability
        try:
            response = httpx.get(f"{self.config.base_url}/models", timeout=3.0,
                                 headers=self._headers())
            ok = response.status_code == 200
        except httpx.HTTPError as error:
            self.last_error = f"{type(error).__name__}: {error}"
            ok = False
        with self._lock:
            self._availability = ok
            self._availability_at = time.monotonic()
        return ok

    def list_models(self) -> list[str]:
        response = httpx.get(f"{self.config.base_url}/models", timeout=5.0,
                             headers=self._headers())
        response.raise_for_status()
        return [item.get("id", "") for item in response.json().get("data", [])]

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_key}"}

    # -- chat -------------------------------------------------------------
    def chat(self, messages: list[dict[str, str]], *, json_mode: bool = False,
             max_tokens: int = 700, temperature: float | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": self.config.temperature if temperature is None else temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            response = httpx.post(f"{self.config.base_url}/chat/completions",
                                  json=payload, timeout=self.config.timeout,
                                  headers=self._headers())
            if response.status_code == 400 and json_mode:
                # Server rejects response_format — retry relying on the prompt.
                payload.pop("response_format", None)
                response = httpx.post(f"{self.config.base_url}/chat/completions",
                                      json=payload, timeout=self.config.timeout,
                                      headers=self._headers())
            response.raise_for_status()
        except httpx.HTTPError as error:
            self.last_error = f"{type(error).__name__}: {error}"
            raise LLMUnavailable(str(error)) from error
        body = response.json()
        try:
            return body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as error:
            raise LLMUnavailable(f"Malformed completion payload: {body}") from error

    # -- structured output ------------------------------------------------
    def structured(self, schema: type[ModelT], system: str, user: str,
                   *, repair_rounds: int = 1,
                   max_tokens: int = 700) -> tuple[ModelT | None, list[str]]:
        """Ask for JSON validating against ``schema``.

        Returns ``(instance, notes)``; ``instance`` is None when every attempt
        failed. ``notes`` records what happened for the agent trace.
        """
        notes: list[str] = []
        schema_json = json.dumps(schema.model_json_schema(), indent=None)
        prompt = (
            f"{user}\n\n"
            f"Respond with a single JSON object that validates against this "
            f"JSON schema — no prose, no markdown fences:\n{schema_json}"
        )
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": prompt}]

        for attempt in range(repair_rounds + 1):
            try:
                reply = self.chat(messages, json_mode=True, max_tokens=max_tokens)
            except LLMUnavailable as error:
                notes.append(f"llm-unavailable: {error}")
                return None, notes
            parsed = extract_json(reply)
            if parsed is None:
                errors = "reply contained no parseable JSON object"
            else:
                try:
                    return schema.model_validate(parsed), notes
                except ValidationError as error:
                    errors = "; ".join(
                        f"{'.'.join(str(loc) for loc in item['loc'])}: {item['msg']}"
                        for item in error.errors()[:6]
                    )
            notes.append(f"attempt {attempt + 1} invalid: {errors}")
            messages.append({"role": "assistant", "content": reply})
            messages.append({
                "role": "user",
                "content": (f"That output failed validation ({errors}). "
                            f"Return ONLY the corrected JSON object."),
            })
        return None, notes


_default_llm: LocalLLM | None = None
_default_llm_lock = threading.Lock()


def get_llm() -> LocalLLM:
    global _default_llm
    with _default_llm_lock:
        if _default_llm is None:
            _default_llm = LocalLLM()
        return _default_llm


def reset_llm() -> None:
    """Testing hook: force re-reading configuration from the environment."""
    global _default_llm
    with _default_llm_lock:
        _default_llm = None
