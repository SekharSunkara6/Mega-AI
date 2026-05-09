import json
from anthropic import Anthropic
from config import settings
from schemas.context import SharedContext
from core.context_manager import count_tokens
import structlog

log = structlog.get_logger()
client = Anthropic(api_key=settings.anthropic_api_key)

COMPRESSION_SYSTEM = """You compress conversational context while preserving ALL structured data.

Rules:
- LOSSLESS: preserve all tool outputs, scores, citations, chunk IDs, structured data exactly
- LOSSY: compress conversational filler, repetitive reasoning, verbose explanations
- Output the compressed context as JSON with same structure but shorter text fields
- Never drop keys — only shorten string values that are conversational"""


def compress_context(context: SharedContext, agent_id: str) -> SharedContext:
    """Called when an agent is about to exceed its budget."""
    log.info("compressing_context", agent=agent_id)

    # Only compress agent_outputs content (not structured fields)
    compressible = {
        aid: str(out.content)[:500]
        for aid, out in context.agent_outputs.items()
    }

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            system=COMPRESSION_SYSTEM,
            messages=[{"role": "user", "content": f"Compress this context for agent {agent_id}:\n{json.dumps(compressible)}"}]
        )
        compressed_text = response.content[0].text.strip()
        # Store compressed summary in metadata
        context.metadata[f"compressed_for_{agent_id}"] = compressed_text
        log.info("compression_done", agent=agent_id, saved_tokens=count_tokens(json.dumps(compressible)) - count_tokens(compressed_text))

    except Exception as e:
        log.error("compression_failed", error=str(e))

    return context