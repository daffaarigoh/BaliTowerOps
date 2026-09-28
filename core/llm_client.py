import json
import logging
import time
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class CircuitBreakerOpenException(Exception):
    """Raised when the LLM circuit breaker is temporarily open."""
    pass


class ModelGateway:
    """
    Unified client gateway for:
    - 'qwen-38': Single corporate model for Planning, Routing, and Compliance Auditing
    Includes persistent class-level circuit breaker and shared HTTP client pool.
    """
    _instance = None
    _last_failure_time: float = 0.0
    _consecutive_failures: int = 0
    _cooldown_seconds: float = 20.0
    _failure_threshold: int = 2
    _client: httpx.AsyncClient | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelGateway, cls).__new__(cls)
        return cls._instance

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        import asyncio
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if (
            cls._client is None
            or cls._client.is_closed
            or getattr(cls, "_client_loop", None) is not current_loop
            or (current_loop and current_loop.is_closed())
        ):
            timeout = httpx.Timeout(timeout=60.0, connect=10.0, read=60.0)
            limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
            cls._client = httpx.AsyncClient(timeout=timeout, limits=limits)
            cls._client_loop = current_loop
        return cls._client

    def _check_circuit(self):
        if ModelGateway._consecutive_failures >= ModelGateway._failure_threshold:
            elapsed = time.time() - ModelGateway._last_failure_time
            if elapsed < ModelGateway._cooldown_seconds:
                raise CircuitBreakerOpenException(
                    f"Circuit breaker OPEN: AI Gateway unreachable ({elapsed:.1f}s / {ModelGateway._cooldown_seconds}s cooldown)"
                )
            logger.info("Circuit breaker entering HALF-OPEN state, attempting reconnection...")

    def _record_success(self):
        ModelGateway._consecutive_failures = 0

    def _record_failure(self):
        ModelGateway._consecutive_failures += 1
        ModelGateway._last_failure_time = time.time()

    async def chat_completion(
        self,
        model_name: str = "qwen-38",
        messages: list[dict[str, str]] | None = None,
        temperature: float = 0.2,
        response_format_json: bool = False,
    ) -> str:
        """
        Calls configured LLM model (qwen-38) using settings from .env.
        """
        self._check_circuit()

        actual_model = settings.MODEL_NAME or "qwen-38"
        endpoint = (settings.MODEL_URL or "http://localhost:8001/v1").rstrip("/")
        if endpoint.endswith("/models"):
            endpoint = endpoint[:-7]

        headers = {
            "Content-Type": "application/json",
        }
        if settings.MODEL_API_KEY and settings.MODEL_API_KEY.strip():
            headers["Authorization"] = f"Bearer {settings.MODEL_API_KEY.strip()}"

        payload: dict[str, Any] = {
            "model": actual_model,
            "messages": messages or [],
            "temperature": temperature,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        client = self.get_client()
        try:
            res = await client.post(f"{endpoint}/chat/completions", json=payload, headers=headers)
            res.raise_for_status()
            data = res.json()
            self._record_success()
            msg = data["choices"][0]["message"]
            return msg.get("content") or msg.get("reasoning_content") or ""
        except Exception as e:
            self._record_failure()
            logger.error(f"Failed to connect to model {actual_model} at {endpoint}: {e!r}")
            raise e

    async def chat_completion_stream(
        self,
        model_name: str = "qwen-38",
        messages: list[dict[str, str]] | None = None,
        temperature: float = 0.2,
    ):
        """
        Streams response tokens from configured LLM model (qwen-38).
        Yields text chunks as they arrive from the upstream server.
        """
        self._check_circuit()

        actual_model = settings.MODEL_NAME or "qwen-38"
        endpoint = (settings.MODEL_URL or "http://localhost:8001/v1").rstrip("/")
        if endpoint.endswith("/models"):
            endpoint = endpoint[:-7]

        headers = {
            "Content-Type": "application/json",
        }
        if settings.MODEL_API_KEY and settings.MODEL_API_KEY.strip():
            headers["Authorization"] = f"Bearer {settings.MODEL_API_KEY.strip()}"

        payload: dict[str, Any] = {
            "model": actual_model,
            "messages": messages or [],
            "temperature": temperature,
            "stream": True,
        }

        client = self.get_client()
        try:
            async with client.stream("POST", f"{endpoint}/chat/completions", json=payload, headers=headers) as response:
                response.raise_for_status()
                self._record_success()
                async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            raw_data = line[6:].strip()
                            if raw_data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(raw_data)
                                content = chunk["choices"][0]["delta"].get("content", "")
                                if content:
                                    yield content
                            except Exception:
                                pass
        except Exception as e:
            self._record_failure()
            logger.error(f"Streaming failed for model {actual_model} at {endpoint}: {e!r}")
            raise e


gateway = ModelGateway()
