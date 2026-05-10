from groq import Groq
from config import settings

# Single client used by all agents
client = Groq(api_key=settings.groq_api_key)
MODEL = "llama-3.3-70b-versatile"

def chat(system: str, user: str, max_tokens: int = 1000) -> str:
    """
    Drop-in replacement for Anthropic calls.
    Returns the text content directly.
    """
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")