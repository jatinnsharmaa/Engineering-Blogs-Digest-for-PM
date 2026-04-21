import json
import time
from dataclasses import dataclass
from pathlib import Path

import anthropic

from .fetcher import Article


@dataclass
class ArticleSummary:
    company: str
    title: str
    url: str
    problem: str
    solution: str
    business_impact: str
    user_impact: str
    key_takeaway: str


class SummarizerAgent:
    def __init__(self, model: str, batch_size: int = 5):
        self.client = anthropic.Anthropic()
        self.model = model
        self.batch_size = batch_size
        self._system_prompt = Path("prompts/summarizer.txt").read_text()

    def run(self, articles: list[Article]) -> list[ArticleSummary]:
        summaries: list[ArticleSummary] = []

        # Process in batches with a brief sleep between them to avoid hitting
        # Anthropic rate limits on rapid sequential requests.
        for i in range(0, len(articles), self.batch_size):
            batch = articles[i : i + self.batch_size]
            for article in batch:
                summary = self._summarize(article)
                if summary:
                    summaries.append(summary)
            if i + self.batch_size < len(articles):
                time.sleep(1)

        return summaries

    def _summarize(self, article: Article) -> ArticleSummary | None:
        try:
            # Prompt caching: the system prompt is identical across all article calls.
            # Anthropic caches it on the first call (cache_control: ephemeral, 5-min TTL)
            # and serves subsequent calls from cache — ~80-90% token cost reduction per run.
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=600,
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
                            f"Title: {article.title}\n"
                            f"Company: {article.company}\n"
                            f"URL: {article.url}\n\n"
                            f"Article body:\n{article.body[:6000]}"
                        ),
                    }
                ],
            )

            raw = response.content[0].text.strip()
            # strip accidental markdown fences
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)

            if data.get("skip"):
                return None

            return ArticleSummary(
                company=article.company,
                title=article.title,
                url=article.url,
                problem=data.get("problem", ""),
                solution=data.get("solution", ""),
                business_impact=data.get("business_impact", ""),
                user_impact=data.get("user_impact", ""),
                key_takeaway=data.get("key_takeaway", ""),
            )
        except Exception as e:
            print(f"[summarizer] skipped '{article.title}': {e}")
            return None
