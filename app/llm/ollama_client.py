import httpx
import structlog
from app.config import settings

logger = structlog.get_logger("llm.ollama")


async def generate(prompt: str, system_prompt: str = "") -> str:
    """POST to Ollama /api/generate and return the response text."""
    payload: dict = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
    }
    if system_prompt:
        payload["system"] = system_prompt

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/generate",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    text = data.get("response", "")
    logger.info("ollama.generate.done", model=settings.ollama_model, chars=len(text))
    return text
