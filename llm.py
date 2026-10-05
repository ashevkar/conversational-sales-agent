"""Thin client for the local model server (OpenAI-compatible API).

Works with any OpenAI-compatible local server (Ollama, llama.cpp, LM Studio,
vLLM) by changing LLM_BASE_URL / LLM_MODEL. No hosted APIs are used.
Connection problems are raised as LLM*Error with a message saying how to fix them.
"""
import os

import openai
from openai import OpenAI

BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")  # Ollama
MODEL = os.getenv("LLM_MODEL", "qwen3.5-4b-8k")  # built from ./Modelfile
# A local 4B model can take a while on a laptop CPU, but should never hang forever.
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "300"))

_client = OpenAI(base_url=BASE_URL, api_key="local", timeout=TIMEOUT, max_retries=1)

START_HINT = ("Start it, e.g. `ollama serve` (model built with `ollama create {model} -f Modelfile`) "
              "or `llama-server -m <model.gguf> --port 8080 -c 8192 --jinja` with "
              "LLM_BASE_URL=http://localhost:8080/v1.")


class LLMError(Exception):
    """Base class for model-server problems; the message says how to fix them."""


class LLMConnectionError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMModelNotFoundError(LLMError):
    pass


def _hint() -> str:
    return START_HINT.format(model=MODEL)


def check_server() -> None:
    """Fail fast with a clear message if the model server or model is unavailable."""
    try:
        models = [m.id for m in _client.models.list().data]
    except openai.APIConnectionError as e:
        raise LLMConnectionError(f"Can't reach the model server at {BASE_URL}. {_hint()}") from e
    # Ollama lists 'name:latest'; llama-server lists its alias or file name.
    if models and not any(m == MODEL or m.split(":")[0] == MODEL for m in models):
        raise LLMModelNotFoundError(
            f"The model server at {BASE_URL} doesn't have the model '{MODEL}' "
            f"(it has: {', '.join(models[:5])}). Set LLM_MODEL or load the model.")


def chat(messages: list[dict], temperature: float = 0.0, max_tokens: int = 1024) -> str:
    try:
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
    except openai.APITimeoutError as e:
        raise LLMTimeoutError(f"The model server at {BASE_URL} did not answer within "
                              f"{TIMEOUT:.0f}s. Raise LLM_TIMEOUT or use a smaller model.") from e
    except openai.APIConnectionError as e:
        raise LLMConnectionError(f"Lost connection to the model server at {BASE_URL}. "
                                 f"{_hint()}") from e
    except openai.NotFoundError as e:
        raise LLMModelNotFoundError(f"The model server at {BASE_URL} doesn't know the model "
                                    f"'{MODEL}'. Set LLM_MODEL to a model it serves.") from e
    return (resp.choices[0].message.content or "").strip()
