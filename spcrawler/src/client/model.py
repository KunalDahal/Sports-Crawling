from __future__ import annotations

import random
import threading
import time

import requests

from ..utils.config import Config
from ..utils.constants import (
    LLM_BACKOFF_BASE,
    LLM_BACKOFF_MAX,
    LLM_MAX_REQUEST_CHARS,
    LLM_MAX_RETRIES,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_REQUEST_TIMEOUT_SEC,
    LLM_RATE_LIMIT_COOLDOWN,
    LLM_TEMPERATURE,
    MIN_DELAY_BETWEEN_LLM_CALLS,
)

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

_model_cache: dict[str, "Model"] = {}
_model_lock = threading.Lock()


def get_model(cfg: Config) -> "Model":
    with _model_lock:
        key = cfg.api_key
        if key not in _model_cache:
            _model_cache[key] = Model(cfg)
        return _model_cache[key]


class Model:
    def __init__(self, cfg: Config) -> None:
        self._api_key = cfg.api_key
        self._lock = threading.Lock()
        self._last_call_time = 0.0
        self._cooldown_until = 0.0
        self._session = requests.Session()

    def call(self, system_prompt: str, user_message: str, *, operation: str = "unknown") -> str:
        if len(system_prompt) + len(user_message) > LLM_MAX_REQUEST_CHARS:
            raise ValueError("LLM request exceeds configured size limit")
        url = f"{_BASE_URL}/{LLM_MODEL}:generateContent?key={self._api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": {
                "maxOutputTokens": LLM_MAX_TOKENS,
                "temperature": LLM_TEMPERATURE,
                "responseMimeType": "application/json",
            },
        }

        with self._lock:
            self._throttle(operation)
            backoff = float(LLM_BACKOFF_BASE)

            for attempt in range(1, LLM_MAX_RETRIES + 1):
                try:
                    resp = self._session.post(
                        url,
                        json=payload,
                        timeout=(3, LLM_REQUEST_TIMEOUT_SEC),
                    )

                    if resp.status_code == 429:
                        wait = min(
                            self._retry_after(resp, backoff) + random.uniform(1, 5),
                            LLM_BACKOFF_MAX,
                        )
                        self._cooldown_until = max(
                            self._cooldown_until,
                            time.monotonic() + wait + LLM_RATE_LIMIT_COOLDOWN,
                        )
                        time.sleep(wait)
                        backoff = min(backoff * 2, LLM_BACKOFF_MAX)
                        continue

                    if 500 <= resp.status_code < 600:
                        wait = min(backoff + random.uniform(1, 5), LLM_BACKOFF_MAX)
                        time.sleep(wait)
                        backoff = min(backoff * 1.5, LLM_BACKOFF_MAX)
                        continue

                    resp.raise_for_status()
                    data = resp.json()
                    self._last_call_time = time.monotonic()
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()

                except requests.exceptions.HTTPError:
                    if attempt == LLM_MAX_RETRIES:
                        raise
                    wait = min(backoff + random.uniform(1, 5), LLM_BACKOFF_MAX)
                    time.sleep(wait)
                    backoff = min(backoff * 2, LLM_BACKOFF_MAX)

                except requests.exceptions.Timeout:
                    if attempt == LLM_MAX_RETRIES:
                        raise
                    time.sleep(min(backoff, LLM_BACKOFF_MAX))
                    backoff = min(backoff * 1.5, LLM_BACKOFF_MAX)

                except Exception:
                    raise

        raise RuntimeError("call() exhausted retries without returning")

    def _throttle(self, operation: str) -> None:
        _ = operation
        now = time.monotonic()
        next_allowed = max(
            self._last_call_time + MIN_DELAY_BETWEEN_LLM_CALLS,
            self._cooldown_until,
        )
        wait = max(0.0, next_allowed - now)
        if wait > 0:
            time.sleep(wait)

    @staticmethod
    def _retry_after(resp: requests.Response, default: float) -> float:
        header = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
        if header:
            try:
                return float(header)
            except ValueError:
                pass
        return default
