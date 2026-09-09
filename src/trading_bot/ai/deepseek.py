"""DeepSeek provider — OpenAI-compatible chat/completions via stdlib (plan 03-01).

Deliberately zero third-party dependencies. The project is dependency-light by
policy (stdlib ``tomllib``, stdlib logging) and a machine that only backtests
must not be forced to install a vendor SDK. DeepSeek's API is OpenAI-shaped
(``POST /chat/completions``), so this client is a thin ``urllib`` translation
layer with no strategy knowledge — exactly like ``MT5Broker`` is a thin layer
over the MT5 API.

The API key is read from the environment variable named by ``[ai] api_key_env``
(default ``DEEPSEEK_API_KEY``) at CALL time, never from config and never from a
default. The constructor makes no network call and import-time does nothing but
import stdlib.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from trading_bot.ai.base import AIClient, AIClientUnavailableError
from trading_bot.ai.context import RegimeContext, TradeContext
from trading_bot.ai.prompts import render_regime_prompt, render_trade_prompt
from trading_bot.ai.schema import parse_proposal, parse_regime

TRADE_SYSTEM = (
    "You are the reasoning module of a hybrid trading system. Deterministic "
    "code owns risk and execution; you give an independent directional verdict "
    "with a confidence score. Reply with exactly the JSON object the user "
    "requests and nothing else."
)

REGIME_SYSTEM = (
    "You are the daily regime reader of a hybrid gold trading system. Judge "
    "whether today is tradeable for a 5-minute breakout strategy. Reply with "
    "exactly the JSON object the user requests and nothing else."
)


def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict,
    timeout: float,
) -> dict:
    """POST JSON, return the parsed response body. Isolated so tests can fake it."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class DeepSeekClient(AIClient):
    """Call DeepSeek's OpenAI-compatible endpoint with JSON output mode.

    ``cfg`` is the loaded project Config; only the ``[ai]`` table is read.
    """

    def __init__(self, cfg):
        self._cfg = cfg
        self._key = None  # resolved lazily so the constructor never reads env

    def propose_trade(self, context: TradeContext):
        prompt = render_trade_prompt(context, self._cfg.ai.prompt_dir)
        content = self._chat(prompt, TRADE_SYSTEM)
        return parse_proposal(content)

    def assess_regime(self, context: RegimeContext):
        prompt = render_regime_prompt(context, self._cfg.ai.prompt_dir)
        content = self._chat(prompt, REGIME_SYSTEM)
        return parse_regime(content)

    def _chat(self, user_text: str, system: str) -> str:
        key = os.environ.get(self._cfg.ai.api_key_env)
        if not key:
            raise AIClientUnavailableError(
                f"ai.provider=deepseek but environment variable "
                f"{self._cfg.ai.api_key_env!r} is not set"
            )
        url = self._cfg.ai.api_base.rstrip("/") + "/chat/completions"
        payload = {
            "model": self._cfg.ai.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            "temperature": self._cfg.ai.temperature,
            "max_tokens": self._cfg.ai.max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        try:
            body = _post_json(url, headers, payload, self._cfg.ai.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise AIClientUnavailableError(
                f"DeepSeek HTTP {exc.code}: {detail}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise AIClientUnavailableError(
                f"DeepSeek unreachable at {self._cfg.ai.api_base}: {exc}"
            ) from exc

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIClientUnavailableError(
                f"DeepSeek response missing choices/message/content: {body!r}"
            ) from exc
