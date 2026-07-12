import anthropic
import structlog
from app.config import settings

logger = structlog.get_logger("llm.anthropic")

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def generate(prompt: str, system_prompt: str = "") -> str:
    """Call Anthropic Messages API and return response text."""
    client = _get_client()
    kwargs: dict = {
        "model": "claude-opus-4-5",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    message = await client.messages.create(**kwargs)
    text = message.content[0].text
    logger.info(
        "anthropic.generate.done",
        model="claude-opus-4-5",
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
    )
    return text
