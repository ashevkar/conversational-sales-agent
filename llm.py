"""Thin client for the local model (LM Studio's OpenAI-compatible server).

Works with any OpenAI-compatible local server (LM Studio, Ollama, llama.cpp,
vLLM) by changing LLM_BASE_URL / LLM_MODEL. No hosted APIs are used.
"""
import os

from openai import OpenAI

BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
MODEL = os.getenv("LLM_MODEL", "qwen3.5-4b")

_client = OpenAI(base_url=BASE_URL, api_key="local")  # key is ignored locally


def chat(messages: list[dict], temperature: float = 0.0, max_tokens: int = 1024) -> str:
    resp = _client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        # Qwen 3.5 "thinks" by default (2,000+ tokens even for trivial SQL).
        # Turning it off makes answers ~100x shorter and fast enough on a laptop.
        extra_body={
            "reasoning_effort": "none",
            "chat_template_kwargs": {"enable_thinking": False},
        },
    )
    return (resp.choices[0].message.content or "").strip()
