import json
from dataclasses import dataclass
from pathlib import Path

import anthropic

from .summarizer import ArticleSummary


@dataclass
class DigestContent:
    subject: str
    intro: str
    closing: str
    themes: list[dict]
    n_articles: int
    n_companies: int


class CompilerAgent:
    def __init__(self, model: str):
        self.client = anthropic.Anthropic()
        self.model = model
        self._system_prompt = Path("prompts/compiler.txt").read_text()

    def run(self, summaries: list[ArticleSummary], date_str: str) -> DigestContent:
        # All summaries are sent in a single LLM call so the model can see the full
        # week's picture and detect cross-company themes. A per-article approach would
        # miss patterns that span multiple posts (e.g. 3 companies investing in the same area).
        payload = [
            {
                "company": s.company,
                "title": s.title,
                "url": s.url,
                "problem": s.problem,
                "solution": s.solution,
                "business_impact": s.business_impact,
                "user_impact": s.user_impact,
                "key_takeaway": s.key_takeaway,
            }
            for s in summaries
        ]

        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=8000,
            betas=["prompt-caching-2024-07-31"],
            system=[
                {
                    "type": "text",
                    "text": self._system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Here are {len(summaries)} article summaries for the week of {date_str}.\n\n"
                        + json.dumps(payload, indent=2)
                    ),
                }
            ],
        )

        raw = response.content[0].text.strip()
        # strip markdown code fences if present
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Compiler returned invalid JSON: {e}\nRaw output:\n{raw[:500]}")

        n_companies = len({s.company for s in summaries})
        subject = "Engineering Blogs Digest for PM"

        return DigestContent(
            subject=subject,
            intro=data["intro"],
            closing=data["closing"],
            themes=data["themes"],
            n_articles=len(summaries),
            n_companies=n_companies,
        )
