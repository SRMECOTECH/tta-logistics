"""LangChain AI layer.

Every insight request goes through the same LangChain pipeline:
    ChatPromptTemplate | chat-model | StrOutputParser

The chat model is swappable at runtime from the Settings UI:
  * azure_openai  -> langchain_openai.AzureChatOpenAI
  * openai        -> langchain_openai.ChatOpenAI
  * huggingface   -> HuggingFaceChat (custom LangChain BaseChatModel wrapping
                     the free HF Inference API via huggingface_hub) — no heavy
                     torch/transformers install needed, works on free tier.
"""
import json
import time
from typing import Any, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.prompts import ChatPromptTemplate


class HuggingFaceChat(BaseChatModel):
    """Minimal LangChain chat model over the HF serverless Inference API."""

    model_id: str
    api_key: str
    max_tokens: int = 900
    temperature: float = 0.3

    @property
    def _llm_type(self) -> str:
        return "huggingface-inference-api"

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                  run_manager: Any = None, **kwargs: Any) -> ChatResult:
        from huggingface_hub import InferenceClient

        client = InferenceClient(model=self.model_id, token=self.api_key, timeout=120)
        hf_messages = []
        for m in messages:
            role = "system" if isinstance(m, SystemMessage) else ("assistant" if isinstance(m, AIMessage) else "user")
            hf_messages.append({"role": role, "content": m.content})
        resp = client.chat_completion(hf_messages, max_tokens=self.max_tokens, temperature=self.temperature)
        text = resp.choices[0].message.content or ""
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


def build_llm(settings: dict):
    """Return (llm, label) for the currently selected provider."""
    provider = settings.get("ai_provider", "disabled")
    temperature = float(settings.get("ai_temperature", 0.3) or 0.3)
    max_tokens = int(settings.get("ai_max_tokens", 900) or 900)

    if provider == "azure_openai":
        if not settings.get("azure_api_key"):
            raise ValueError("Azure OpenAI is selected but no API key is set. Add it in Settings.")
        from langchain_openai import AzureChatOpenAI

        llm = AzureChatOpenAI(
            azure_endpoint=settings.get("azure_endpoint", ""),
            api_key=settings.get("azure_api_key", ""),
            api_version=settings.get("azure_api_version", "2024-12-01-preview"),
            azure_deployment=settings.get("azure_chat_deployment", "gpt-4.1"),
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=120,
        )
        return llm, f"Azure OpenAI · {settings.get('azure_chat_deployment')}"

    if provider == "openai":
        if not settings.get("openai_api_key"):
            raise ValueError("OpenAI is selected but no API key is set. Add it in Settings.")
        from langchain_openai import ChatOpenAI

        model = settings.get("openai_model", "gpt-4o-mini")
        llm = ChatOpenAI(model=model, api_key=settings.get("openai_api_key", ""),
                         temperature=temperature, max_tokens=max_tokens, timeout=120)
        return llm, f"OpenAI · {model}"

    if provider == "glm":
        if not settings.get("glm_api_key"):
            raise ValueError("GLM (Zhipu) is selected but no API key is set. Add it in Settings "
                             "(free key from z.ai — the glm-4.5-flash / glm-4.7-flash models are free).")
        from langchain_openai import ChatOpenAI

        model = settings.get("glm_model", "glm-4.5-flash")
        llm = ChatOpenAI(
            model=model,
            api_key=settings.get("glm_api_key", ""),
            base_url=settings.get("glm_base_url", "https://api.z.ai/api/paas/v4/"),
            temperature=temperature, max_tokens=max_tokens, timeout=120,
        )
        return llm, f"GLM (Zhipu) · {model}"

    if provider == "huggingface":
        if not settings.get("hf_api_key"):
            raise ValueError("Hugging Face is selected but no API token is set. Add it in Settings "
                             "(free token from huggingface.co/settings/tokens).")
        model = settings.get("hf_model", "Qwen/Qwen2.5-7B-Instruct")
        llm = HuggingFaceChat(model_id=model, api_key=settings.get("hf_api_key", ""),
                              temperature=temperature, max_tokens=max_tokens)
        return llm, f"Hugging Face · {model}"

    raise ValueError("AI provider is disabled. Enable GLM, Azure OpenAI, OpenAI or Hugging Face in Settings.")


SYSTEM_PROMPT = (
    "You are a senior supply-chain and logistics data analyst presenting findings to a client. "
    "The dataset covers outbound road logistics trips of a large steel plant in Jamshedpur, India: "
    "transporters, lanes to destinations across India, transit times (hours), detention, distances (km), "
    "GPS telemetry, speed violations and on-time delivery (OTD) performance. "
    "Base every statement STRICTLY on the numbers provided — never invent figures. "
    "Be crisp, quantitative and business-oriented."
)

USER_PROMPT = """Analysis context: {context}
Active filters: {filters}

Computed data (JSON):
{data}

Task: {task}

Respond in markdown with exactly these sections:
### Key insights
(3-5 bullets, each anchored on a specific number from the data)
### Risks & watch-outs
(2-3 bullets)
### Recommendations
(2-4 actionable bullets a logistics manager could execute)

Keep the whole answer under 350 words."""

DEFAULT_TASK = "Analyse the data and produce insights, risks and recommendations."


def _truncate_json(data: Any, limit: int = 11000) -> str:
    text = json.dumps(data, default=str, ensure_ascii=False)
    if len(text) > limit:
        text = text[:limit] + ' ... [truncated]"}'
    return text


def generate_insight(settings: dict, context: str, data: Any,
                     question: Optional[str] = None, filters: Optional[dict] = None) -> dict:
    llm, label = build_llm(settings)
    prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", USER_PROMPT)])
    chain = prompt | llm | StrOutputParser()

    start = time.time()
    answer = chain.invoke({
        "context": context,
        "filters": json.dumps(filters or {}, default=str) if filters else "none",
        "data": _truncate_json(data),
        "task": question or DEFAULT_TASK,
    })
    return {
        "markdown": answer,
        "provider": label,
        "elapsed_s": round(time.time() - start, 1),
    }


def test_connection(settings: dict) -> dict:
    llm, label = build_llm(settings)
    start = time.time()
    resp = llm.invoke("Reply with exactly: CONNECTION OK")
    text = resp.content if hasattr(resp, "content") else str(resp)
    return {"provider": label, "response": text.strip()[:200], "elapsed_s": round(time.time() - start, 1)}
