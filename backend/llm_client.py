from groq import Groq
from config import settings

client = Groq(api_key=settings.groq_api_key)

MODELS = [
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
    "llama-3.3-70b-versatile",
]

def chat(system: str, user: str, max_tokens: int = 1000) -> str:
    for model in MODELS:
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            if "rate_limit" in str(e) or "429" in str(e):
                continue
            raise RuntimeError(f"LLM call failed: {e}")
    raise RuntimeError("All models rate limited — please wait a few minutes")

def extract_json(raw: str) -> str:
    raw = raw.strip()
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{") or part.startswith("["):
                raw = part
                break
    start = raw.find("{")
    arr_start = raw.find("[")
    if arr_start >= 0 and (start < 0 or arr_start < start):
        start = arr_start
        end = raw.rfind("]") + 1
    else:
        end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        return raw[start:end]
    return raw