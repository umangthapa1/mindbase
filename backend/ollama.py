import httpx
import json
import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, Optional
from config import OLLAMA_HOST, DEFAULT_MODEL

logger = logging.getLogger(__name__)


# ── Shared, pooled HTTP client ─────────────────────────────────────────
# Each call used to spin up its own `httpx.AsyncClient`, paying a fresh TCP
# handshake to localhost on every request. One long-lived pooled client reuses
# keep-alive connections across turns. It's created lazily inside the running
# loop (httpx binds the connection pool on first use), so it survives --reload.
_shared_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()

# Per-call ceilings. `read` is the max gap between bytes/chunks, NOT total wall
# time — so a long streaming generation keeps flowing (each chunk resets the
# read clock) while a hung Ollama still times out. `connect` fails fast (10s)
# so a down Ollama is detected quickly instead of waiting the full read budget.
_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
_EMBED_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)
_PULL_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)
_QUICK_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
_HEALTH_TIMEOUT = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)


async def _get_client() -> httpx.AsyncClient:
    """Return the shared pooled client, creating it on first use (double-checked
    so concurrent first-callers don't build two clients)."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        async with _client_lock:
            if _shared_client is None or _shared_client.is_closed:
                _shared_client = httpx.AsyncClient(
                    limits=httpx.Limits(
                        max_connections=20,
                        max_keepalive_connections=10,
                        keepalive_expiry=30.0,
                    ),
                    timeout=_DEFAULT_TIMEOUT,
                )
    return _shared_client


async def aclose() -> None:
    """Close the shared client — call from the lifespan shutdown."""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()


class OllamaError(RuntimeError):
    """Raised when an Ollama chat/embedding request fails.

    Callers should catch this rather than string-matching "[Error: ...]".
    """


class OllamaClient:
    def __init__(self, host: str = OLLAMA_HOST):
        self.host = host
        self.current_model = None

    async def list_models(self) -> list[Dict[str, Any]]:
        try:
            client = await _get_client()
            response = await client.get(f"{self.host}/api/tags", timeout=_QUICK_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                return data.get("models", [])
        except Exception as e:
            logger.error("Error listing models: %s", e)
        return []

    async def set_model(self, model_name: str) -> bool:
        if not model_name:
            return False

        models = await self.list_models()
        model_exists = any(m["name"] == model_name or m["name"].startswith(f"{model_name}:") for m in models)
        if model_exists:
            self.current_model = model_name
            return True
        return False

    async def get_model(self, requested_model: str | None = None) -> str:
        candidates = [
            requested_model,
            self.current_model,
            DEFAULT_MODEL,
        ]

        for model_name in candidates:
            if model_name and await self.set_model(model_name):
                return model_name

        models = await self.list_models()
        if not models:
            raise RuntimeError("No Ollama models are installed")

        # Filter out models that are clearly embedding models (cannot perform chat generation)
        chat_models = [
            m for m in models
            if not any(word in m["name"].lower() for word in ("embed", "similarity", "bge"))
        ]

        if chat_models:
            model_name = chat_models[0]["name"]
        else:
            raise RuntimeError(
                "No chat-capable models are installed in Ollama. "
                "Please pull a chat model (e.g., 'ollama pull qwen2.5:7b' or 'ollama pull mistral') before using chat or document asking."
            )

        await self.set_model(model_name)
        return model_name

    def _build_options(
        self,
        temperature: float | None = None,
        num_predict: int | None = None,
    ) -> Dict[str, Any]:
        options: Dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if num_predict is not None:
            options["num_predict"] = num_predict
        return options

    async def generate(
        self,
        model: str,
        messages: list[Dict[str, str]],
        *,
        temperature: float | None = None,
        num_predict: int | None = None,
        **kwargs,
    ) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            **kwargs,
        }
        opts = self._build_options(temperature, num_predict)
        if opts:
            payload["options"] = opts

        try:
            client = await _get_client()
            response = await client.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=_DEFAULT_TIMEOUT,
            )
            if response.status_code != 200:
                raise OllamaError(f"Ollama returned HTTP {response.status_code}")
            data = response.json()
            return data.get("message", {}).get("content", "") or ""
        except OllamaError:
            raise
        except Exception as e:
            logger.error("Ollama generate failed: %s", e)
            raise OllamaError(str(e)) from e

    async def stream_generate(
        self,
        model: str,
        messages: list[Dict[str, str]],
        *,
        temperature: float | None = None,
        num_predict: int | None = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            **kwargs
        }
        opts = self._build_options(temperature, num_predict)
        if opts:
            payload["options"] = opts

        try:
            client = await _get_client()
            # `client.stream(...)` opens a streaming response and closes only the
            # response when the block exits — it does NOT close the shared client.
            # `timeout=_DEFAULT_TIMEOUT` (read=120s) means a hung stream (no chunks
            # for 2 min) times out, but a long generation keeps flowing token-by-token
            # and resets the read clock on every chunk.
            async with client.stream(
                "POST",
                f"{self.host}/api/chat",
                json=payload,
                timeout=_DEFAULT_TIMEOUT,
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.warning("Ollama stream returned HTTP %s", response.status_code)
                    yield f"\n[Error: Ollama returned HTTP {response.status_code}: {error_text.decode('utf-8', errors='replace')}]\n"
                    return

                async for line in response.aiter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            if "message" in chunk and "content" in chunk["message"]:
                                yield chunk["message"]["content"]
                        except json.JSONDecodeError:
                            pass
        except httpx.TimeoutException as e:
            logger.error("Ollama stream timed out: %s", e)
            yield "\n[Error: the model stopped responding (timeout).]"
        except Exception as e:
            logger.error("Ollama stream failed: %s", e)
            yield f"\n[Error: {str(e)}]"

    async def generate_embedding(self, text: str, model: str = "nomic-embed-text") -> list[float]:
        try:
            client = await _get_client()
            # 1. Try modern Ollama /api/embed endpoint (Ollama v0.1.34+)
            payload = {
                "model": model,
                "input": text
            }
            response = await client.post(
                f"{self.host}/api/embed",
                json=payload,
                timeout=_EMBED_TIMEOUT,
            )
            if response.status_code == 200:
                data = response.json()
                embeddings = data.get("embeddings", [])
                if embeddings and isinstance(embeddings, list) and len(embeddings) > 0:
                    return embeddings[0]

            # 2. Fallback to legacy /api/embeddings endpoint (older Ollama versions)
            legacy_payload = {
                "model": model,
                "prompt": text
            }
            legacy_response = await client.post(
                f"{self.host}/api/embeddings",
                json=legacy_payload,
                timeout=_EMBED_TIMEOUT,
            )
            if legacy_response.status_code == 200:
                legacy_data = legacy_response.json()
                return legacy_data.get("embedding", [])
        except Exception as e:
            logger.warning("Error generating embedding: %s", e)
        return []

    async def pull_model(self, model_name: str) -> bool:
        payload = {
            "name": model_name,
            "stream": False
        }
        try:
            # Model pull can take minutes; read=600s gives a large gap budget. With
            # stream=False Ollama replies once at the end, so this is effectively a
            # long single-response wait rather than a chunked stream.
            client = await _get_client()
            logger.info("Pulling model '%s' from Ollama library...", model_name)
            response = await client.post(
                f"{self.host}/api/pull",
                json=payload,
                timeout=_PULL_TIMEOUT,
            )
            if response.status_code == 200:
                logger.info("Successfully pulled model '%s'", model_name)
                return True
            else:
                logger.error("Failed to pull model '%s': HTTP %s", model_name, response.status_code)
                return False
        except Exception as e:
            logger.error("Error pulling model '%s': %s", model_name, e)
            return False

    async def check_health(self) -> bool:
        try:
            client = await _get_client()
            response = await client.get(f"{self.host}/api/tags", timeout=_HEALTH_TIMEOUT)
            return response.status_code == 200
        except Exception:
            return False

ollama_client = OllamaClient()
