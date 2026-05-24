import json
import logging
import os
import re
from openai import OpenAI

logger = logging.getLogger(__name__)


class BaseAgent:
    """Shared OpenAI client, JSON parsing, and token tracking for all agents."""

    MODEL = "gpt-4o"

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.total_tokens_used = 0

    def _chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> tuple[str, int]:
        response = self.client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else 0
        self.total_tokens_used += tokens
        return content, tokens

    def _parse_json(self, raw: str, fallback: dict | list | None = None) -> dict | list:
        """Parse JSON from LLM response with fallback on malformed output."""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Strip markdown code fences if present
            cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                logger.error("Failed to parse LLM JSON response: %s", raw[:200])
                if fallback is not None:
                    return fallback
                raise ValueError(f"LLM returned unparseable JSON: {raw[:200]}")
