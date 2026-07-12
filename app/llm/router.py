import structlog
from app.llm import ollama_client, anthropic_client

logger = structlog.get_logger("llm.router")


async def generate(prompt: str, user_llm_choice: str, system_prompt: str = "") -> str:
    """Route an LLM request to the backend indicated by user_llm_choice."""
    backend = user_llm_choice.lower()

    if backend in ("anthropic", "api"):
        logger.info("llm.router.dispatch", backend="anthropic")
        return await anthropic_client.generate(prompt, system_prompt=system_prompt)

    # Default: self-hosted Ollama
    logger.info("llm.router.dispatch", backend="ollama")
    return await ollama_client.generate(prompt, system_prompt=system_prompt)
