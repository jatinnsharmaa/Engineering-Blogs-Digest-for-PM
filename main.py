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
    n_sources = len([s for s in sources if s.get("enabled", True)])
    lookback = settings["limits"]["lookback_days"]
    SEP = "=" * 60

    # 1. Fetch
    print(SEP)
    print(f"  STEP 1 — Reading RSS feeds  ({n_sources} sources, past {lookback} days)")
    print(SEP)
    fetcher = FetcherAgent(sources=sources, settings=settings)
    articles = fetcher.run()
    print(f"\n  → {len(articles)} {'article' if len(articles) == 1 else 'articles'} to process\n")

    # 2. Summarize
    print(SEP)
    print("  STEP 2 — Summarising")
    print(SEP)
    summaries = []
    if articles:
        summarizer = SummarizerAgent(
            model=settings["models"]["summarizer"],
            batch_size=settings["limits"]["summarizer_batch_size"],
        )
        summaries = summarizer.run(articles)
        skipped = len(articles) - len(summaries)
        print(f"  Summarised: {len(summaries)}")
        if skipped:
            print(f"  Skipped:    {skipped}  (not PM-relevant)")
    else:
        print("  Nothing to summarise")
    print()

    # 3. Compile
    print(SEP)
    print("  STEP 3 — Compiling digest")
    print(SEP)
    if summaries:
        compiler = CompilerAgent(model=settings["models"]["compiler"])
        digest = compiler.run(summaries, date_str)
    else:
        reason = "no new posts found" if not articles else "all articles were not PM-relevant"
        digest = _empty_digest(date_str, reason)
        print(f"  Nothing to compile — sending quiet-week notice")
    print()

    if dry_run:
        out_path = Path("digest_preview.html")
        out_path.write_text(_render_html(digest))
        print(f"[dry-run] digest written to {out_path} — NOT sent")
        return

    # 4. Send
    print(SEP)
    print("  STEP 4 — Sending")
    print(SEP)
    recipient = os.environ.get("DIGEST_RECIPIENT") or settings["email"]["recipient"]
    sender_addr = os.environ.get("DIGEST_SENDER") or settings["email"]["sender"]
    gmail_svc = fetcher._get_gmail_service()
    sender = SenderAgent(
        gmail_service=gmail_svc,
        recipient=recipient,
        sender=sender_addr,
    )
    try:
        sender.run(digest)
        fetcher.mark_gmail_processed()
        fetcher.mark_rss_processed(articles)
        print()
        print(SEP)
        print(f"  DONE  |  {n_sources} feeds checked  |  {len(articles)} found  |  {len(summaries)} summarised  |  {len(digest.themes)} themes")
        print(SEP)
    except Exception as e:
        print(f"  Pipeline failed: {e}", file=sys.stderr)
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
