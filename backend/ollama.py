import httpx
import json
import asyncio
from typing import AsyncGenerator, Dict, Any, Optional
from config import OLLAMA_HOST, DEFAULT_MODEL

class OllamaClient:
    def __init__(self, host: str = OLLAMA_HOST):
        self.host = host
        self.current_model = None

    async def list_models(self) -> list[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.host}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    return data.get("models", [])
        except Exception as e:
            print(f"Error listing models: {e}")
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

        model_name = models[0]["name"]
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
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{self.host}/api/chat",
                    json=payload,
                )
                if response.status_code != 200:
                    return f"[Error: Ollama returned HTTP {response.status_code}]"
                data = response.json()
                return data.get("message", {}).get("content", "") or ""
        except Exception as e:
            return f"[Error: {str(e)}]"

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
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{self.host}/api/chat",
                    json=payload
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
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
        except Exception as e:
            yield f"\n[Error: {str(e)}]"

    async def generate_embedding(self, text: str, model: str = "nomic-embed-text") -> list[float]:
        payload = {
            "model": model,
            "prompt": text
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.host}/api/embed",
                    json=payload
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("embedding", [])
        except Exception as e:
            print(f"Error generating embedding: {e}")
        return []

    async def check_health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.host}/api/tags")
                return response.status_code == 200
        except:
            return False

ollama_client = OllamaClient()
