"""llama.cpp `llama-server` 的流式客户端（OpenAI 兼容接口）。

只依赖 requests，不需要任何原生扩展 / 编译环境，适合内网离线部署。
"""
from __future__ import annotations

import json
from typing import Iterable

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:8080"


class LlamaServerError(RuntimeError):
    """本地推理引擎不可用或返回错误。"""


class LlamaServerClient:
    """极简的 llama-server 客户端。"""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, *, timeout: float = 300.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ 连通性
    def health(self, timeout: float = 2.0) -> bool:
        """引擎是否已加载完成并可用。"""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=timeout)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def model_list(self) -> list[dict]:
        try:
            resp = requests.get(f"{self.base_url}/v1/models", timeout=3.0)
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception:  # noqa: BLE001 - 仅用于展示，失败可忽略
            return []

    # ------------------------------------------------------------------ 推理
    def stream_chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        top_p: float = 0.95,
        max_tokens: int = 2048,
    ) -> Iterable[str]:
        """逐段产出译文。调用方负责拼接。"""
        payload = {
            "model": "local",
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            resp = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                stream=True,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LlamaServerError(f"无法连接翻译引擎（{self.base_url}）：{exc}") from exc

        if resp.status_code >= 400:
            detail = ""
            try:
                detail = resp.text[:400]
            except Exception:  # noqa: BLE001
                pass
            resp.close()
            raise LlamaServerError(f"翻译引擎返回错误 {resp.status_code}：{detail}")

        try:
            for raw in resp.iter_lines(decode_unicode=False):
                if not raw:
                    continue
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if not data:
                    continue
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                piece = delta.get("content")
                if piece:
                    yield piece
        finally:
            resp.close()
