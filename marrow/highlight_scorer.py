import json
import re

import requests

from .utils import log

PROMPT = """You are an expert short-form video editor. Judge the transcript excerpt below as a standalone vertical clip for YouTube Shorts and Reels.

Score each of these from 1 to 10:
- hook: how strongly the first sentence grabs attention
- standalone: how well it makes sense with no outside context
- emotion: emotional intensity, surprise, humor, or controversy
- payoff: whether it ends on a satisfying point instead of trailing off

Also write:
- title: a catchy title, at most 60 characters
- reason: one short sentence explaining the scores
- hashtags: 3 to 5 relevant lowercase hashtags

Respond with ONLY a JSON object with exactly these keys: hook, standalone, emotion, payoff, title, reason, hashtags.

Transcript:
\"\"\"
{text}
\"\"\"
"""


def parse_llm_json(raw):
    """Extract and validate the JSON object from a model reply. Returns None if unusable."""
    if not raw:
        return None
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    out = {}
    for key in ("hook", "standalone", "emotion", "payoff"):
        try:
            out[key] = min(10.0, max(1.0, float(data.get(key))))
        except (TypeError, ValueError):
            return None
    out["title"] = str(data.get("title", "")).strip()[:80]
    out["reason"] = str(data.get("reason", "")).strip()
    tags = data.get("hashtags") or []
    if isinstance(tags, str):
        tags = re.findall(r"\w+", tags)
    out["hashtags"] = [str(t).lstrip("#").lower() for t in tags][:5]
    return out


def llm_score(parsed: dict) -> float:
    """Weighted blend of the sub-scores, mapped to 0..1."""
    weighted = (
        0.30 * parsed["hook"]
        + 0.25 * parsed["standalone"]
        + 0.20 * parsed["emotion"]
        + 0.25 * parsed["payoff"]
    )
    return (weighted - 1.0) / 9.0


class OllamaScorer:
    def __init__(self, model, host="http://localhost:11434", timeout=120, retries=2):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()

    def available(self) -> bool:
        """True if Ollama is reachable and the configured model is pulled."""
        try:
            resp = self.session.get(f"{self.host}/api/tags", timeout=5)
            resp.raise_for_status()
            names = {m.get("name", "") for m in resp.json().get("models", [])}
        except Exception as e:
            log.warning("Ollama not reachable at %s (%s).", self.host, e)
            return False
        if self.model in names or f"{self.model}:latest" in names:
            return True
        log.warning("Ollama model '%s' is not pulled. Run: ollama pull %s", self.model, self.model)
        return False

    def score(self, text: str):
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": PROMPT.replace("{text}", text[:8000])}],
            "stream": False,
            "format": "json",
            "keep_alive": "10m",
            "options": {"temperature": 0.2, "num_ctx": 4096},
        }
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
                resp.raise_for_status()
                parsed = parse_llm_json(resp.json().get("message", {}).get("content", ""))
                if parsed:
                    return parsed
            except Exception as e:
                log.debug("LLM attempt %d failed: %s", attempt + 1, e)
        return None
