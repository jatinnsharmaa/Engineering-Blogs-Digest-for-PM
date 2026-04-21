import argparse
import os
import sys
from pathlib import Path

# load .env if present
_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
from datetime import datetime
from pathlib import Path

import yaml

from agents.compiler import CompilerAgent, DigestContent
from agents.fetcher import FetcherAgent
from agents.sender import SenderAgent
from agents.summarizer import SummarizerAgent


def load_config():
    with open("config/sources.yaml") as f:
        sources = yaml.safe_load(f)["sources"]
    with open("config/settings.yaml") as f:
        settings = yaml.safe_load(f)
    return sources, settings


def _render_html(digest: DigestContent) -> str:
    from jinja2 import Environment, FileSystemLoader
    jinja = Environment(loader=FileSystemLoader("templates"), autoescape=True)
    return jinja.get_template("digest.html.jinja2").render(digest=digest)


def _empty_digest(date_str: str, reason: str) -> DigestContent:
    return DigestContent(
        subject="Engineering Blogs Digest for PM — quiet week",
        intro=f"No new engineering posts were found this week ({reason}). The digest will resume automatically next Monday.",
        closing="Sources are monitored continuously — this happens occasionally when blogs take a publishing break.",
        themes=[],
        n_articles=0,
        n_companies=0,
    )


def main(dry_run: bool = False):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[main] ANTHROPIC_API_KEY is not set", file=sys.stderr)
        sys.exit(1)

    sources, settings = load_config()
    date_str = datetime.now().strftime("%a, %b %d %Y")

    # 1. Fetch
    fetcher = FetcherAgent(sources=sources, settings=settings)
    articles = fetcher.run()
    print(f"[fetcher] {len(articles)} new articles found")

    # 2. Summarize (skip if no articles)
    summaries = []
    if articles:
        summarizer = SummarizerAgent(
            model=settings["models"]["summarizer"],
            batch_size=settings["limits"]["summarizer_batch_size"],
        )
        summaries = summarizer.run(articles)
        print(f"[summarizer] {len(summaries)} summaries generated ({len(articles) - len(summaries)} skipped)")

    # 3. Compile — or build an empty digest if nothing to send
    if summaries:
        compiler = CompilerAgent(model=settings["models"]["compiler"])
        digest = compiler.run(summaries, date_str)
        print(f"[compiler] digest compiled — {len(digest.themes)} themes")
    else:
        reason = "no new posts found" if not articles else f"{len(articles)} articles fetched but all were not PM-relevant"
        digest = _empty_digest(date_str, reason)
        print(f"[main] sending empty digest: {reason}")

    if dry_run:
        out_path = Path("digest_preview.html")
        out_path.write_text(_render_html(digest))
        print(f"[dry-run] digest written to {out_path} — NOT sent")
        print(f"[dry-run] subject: {digest.subject}")
        return

    # 4. Send
    gmail_svc = fetcher._get_gmail_service()
    sender = SenderAgent(
        gmail_service=gmail_svc,
        recipient=settings["email"]["recipient"],
        sender=settings["email"]["sender"],
    )
    try:
        sender.run(digest)
        # Mark articles as processed ONLY after a confirmed successful send.
        # If the send raises, we exit here and nothing is marked — so the same
        # articles will be picked up and retried on the next run.
        fetcher.mark_gmail_processed()
        fetcher.mark_rss_processed(articles)
        print("[main] done — articles marked as processed")
    except Exception as e:
        print(f"[main] pipeline failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PM Engineering Digest")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and summarize but write HTML to file instead of sending email",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
