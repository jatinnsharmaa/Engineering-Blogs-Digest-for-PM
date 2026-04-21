# PM Engineering Digest

A weekly email intelligence briefing for Product Managers — automatically collects engineering blog posts from 18 top Indian and global tech companies, extracts the business and product story from each, and delivers a themed digest to your inbox every week.

Built as a multi-agent Python pipeline using the Claude API (Anthropic) and Gmail API.

---

## What you get

Every week you receive an email with engineering posts grouped into 3–5 themes (e.g. "AI in Core Products", "Infrastructure for Reliability", "Growth & Monetisation Bets"). Each article is summarised from a PM's perspective — not the technical how, but the business why: what problem existed, what was the impact, and what's the one takeaway a PM should remember.
<img width="608" height="739" alt="image" src="https://github.com/user-attachments/assets/76f77e73-aeb3-4059-bb0c-c022df973f20" />

---

## Architecture

```
18 RSS Feeds
     │
     ▼
FetcherAgent  ─────────────────────────────  SQLite (tracks seen articles)
     │
     ▼
SummarizerAgent  ──  Claude Haiku  ──  1 API call per article
     │
     ▼
CompilerAgent  ──  Claude Sonnet  ──  1 API call for the full week
     │
     ▼
SenderAgent  ──  Gmail API  ──  weekly digest to your inbox
```

**Key behaviour**: nothing is marked as processed until the email send succeeds. If the pipeline fails mid-way, all articles are retried on the next run.

---

## How it works

**FetcherAgent** polls all enabled RSS feeds in `config/sources.yaml`. It checks each article's GUID against SQLite to skip already-processed ones, fetches the full article body via `trafilatura`, and returns a unified list of `Article` objects. Gmail-type sources (if configured) are fetched via Gmail API instead.

**SummarizerAgent** calls Claude Haiku once per article with a fixed system prompt (cached via Anthropic's prompt caching — ~80-90% cost reduction across a batch). Articles that aren't PM-relevant (pure infra theory, announcements with no business context) are automatically skipped. Returns structured `ArticleSummary` objects with five fields: problem, solution, business_impact, user_impact, key_takeaway.

**CompilerAgent** makes a single Claude Sonnet call with all summaries for the week. Seeing all articles together allows it to detect cross-company themes and write editorial framing that a per-article model couldn't produce. Returns a `DigestContent` with 3–5 themes, an intro, and a closing observation.

**SenderAgent** renders the HTML email template and sends it via Gmail API. If it fails, the pipeline exits with a non-zero code and no articles are marked as processed.

---

## Sources (18 verified)

| Sector | Companies |
|---|---|
| Food & Grocery | Swiggy, Zepto |
| Mobility | Rapido |
| Travel | MakeMyTrip, Ixigo, OYO |
| Fintech | Zerodha, Groww, Razorpay, CRED |
| Entertainment / Social | ShareChat |
| E-commerce | Flipkart, Meesho, Myntra |
| B2B / SaaS | Freshworks, BrowserStack |
| Global | Netflix, Airbnb |

All sources use RSS feeds (no email subscription required). RSS availability and feed URLs were verified before inclusion.

---

## Configuration

**Adding or disabling a source** — edit `config/sources.yaml`. Set `enabled: false` to pause a source without deleting it. Add a new entry with `type: rss` and a working feed URL.

**Changing the schedule** — edit `schedule.day` and `schedule.hour` in `config/settings.yaml` (24-hour UTC), then run `python make_cron.py` and paste the output into `.github/workflows/weekly_digest.yml`.

**Adjusting the digest framing** — edit `prompts/summarizer.txt` (controls per-article extraction) or `prompts/compiler.txt` (controls theme grouping and editorial voice).

---

## Setup

See [SETUP.md](SETUP.md) for full step-by-step installation, Google Cloud credentials setup, and GitHub Actions deployment.

**Quick summary**: Python 3.12+, a Google Cloud project with Gmail API enabled, an Anthropic API key, and a one-time browser OAuth flow.
