# PM Engineering Digest

A weekly email intelligence briefing for Product Managers — automatically collects engineering blog posts from 18 top Indian and global tech companies, extracts the business and product story from each, and delivers a themed digest to your inbox every week.

Built as a multi-agent Python pipeline using the Claude API (Anthropic) and Gmail API.

---

## What you get

Every week you receive an email with engineering posts grouped into 3–5 themes (e.g. "AI in Core Products", "Infrastructure for Reliability", "Growth & Monetisation Bets"). Each article is summarised from a PM's perspective — not the technical how, but the business why: what problem existed, what was the impact, and what's the one takeaway a PM should remember.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                       pm-digest pipeline                         │
│                   (orchestrated by main.py)                      │
└──────────────────────────────────────────────────────────────────┘

  18 RSS Feeds
  (config/sources.yaml)
        │
        ▼
  ┌─────────────┐     reads new articles      ┌──────────────────┐
  │ FetcherAgent│ ◄─── skips seen GUIDs ─────►│ SQLite (db/)     │
  │             │     marks seen after send    │ rss_articles tbl │
  └──────┬──────┘                             └──────────────────┘
         │
         │  List[Article]
         │  (company, title, url, body)
         ▼
  ┌──────────────────┐
  │ SummarizerAgent  │──── Claude Haiku (1 call per article)
  │                  │     prompt cached across all articles
  └────────┬─────────┘     returns: skip | {problem, solution,
           │                         business_impact, user_impact,
           │  List[ArticleSummary]   key_takeaway}
           ▼
  ┌──────────────────┐
  │  CompilerAgent   │──── Claude Sonnet (1 call for entire week)
  │                  │     sees all summaries together
  └────────┬─────────┘     groups into themes, writes intro/closing
           │
           │  DigestContent
           │  (themes, intro, closing)
           ▼
  ┌──────────────────┐     renders digest.html.jinja2
  │   SenderAgent    │──── Gmail API ──► your.email@gmail.com
  └──────────────────┘
           │
           ▼
    mark articles processed
    (Gmail: mark as read | RSS: write GUIDs to SQLite)
```

**State management**: processed articles are never re-sent. For RSS sources, processed GUIDs are stored in SQLite (`db/digest.db`). State is only committed after the email send succeeds — if the send fails, nothing is marked and the articles are retried next run.

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
