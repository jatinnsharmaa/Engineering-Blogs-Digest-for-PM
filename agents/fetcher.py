import base64
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import trafilatura
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


@dataclass
class Article:
    company: str
    title: str
    url: str
    body: str
    source_type: str  # "gmail" or "rss"
    guid: str = ""    # RSS only, for dedup


class FetcherAgent:
    def __init__(self, sources: list[dict], settings: dict):
        self.sources = sources
        self.lookback_days = settings["limits"]["lookback_days"]
        self.max_per_source = settings["limits"]["max_articles_per_source"]
        self.db_path = settings["db_path"]
        self.auth_dir = Path(settings["auth_dir"])
        self.cutoff = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        self._gmail_service = None
        self._pending_gmail_ids: list[str] = []

    # ── public ────────────────────────────────────────────────────────────────

    def run(self) -> list[Article]:
        active = [s for s in self.sources if s.get("enabled", True)]
        skipped_sources = [s["name"] for s in self.sources if not s.get("enabled", True)]
        gmail_sources = [s for s in active if s["type"] == "gmail"]
        rss_sources = [s for s in active if s["type"] == "rss"]

        print(f"[fetcher] sources: {len(active)} active, {len(skipped_sources)} disabled")

        articles: list[Article] = []

        if gmail_sources:
            articles += self._fetch_gmail(gmail_sources)

        if rss_sources:
            articles += self._fetch_rss(rss_sources)

        return articles

    def mark_gmail_processed(self):
        """Mark fetched Gmail messages as read. Call only after successful send."""
        if not self._pending_gmail_ids:
            return
        svc = self._get_gmail_service()
        for msg_id in self._pending_gmail_ids:
            svc.users().messages().modify(
                userId="me",
                id=msg_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
        self._pending_gmail_ids.clear()

    def mark_rss_processed(self, articles: list[Article]):
        """Persist RSS article GUIDs to SQLite. Call only after successful send."""
        rss = [a for a in articles if a.source_type == "rss" and a.guid]
        if not rss:
            return
        conn = self._db_conn()
        conn.executemany(
            "INSERT OR IGNORE INTO rss_articles (guid, company, url, processed_at) VALUES (?,?,?,?)",
            [(a.guid, a.company, a.url, datetime.now(timezone.utc).isoformat()) for a in rss],
        )
        conn.commit()
        conn.close()

    # ── Gmail ─────────────────────────────────────────────────────────────────

    def _fetch_gmail(self, sources: list[dict]) -> list[Article]:
        import re
        svc = self._get_gmail_service()
        # validate sender addresses before interpolating into Gmail search query
        valid_sources = [
            s for s in sources
            if re.match(r'^[\w.+%-]+@[\w.-]+\.[a-zA-Z]{2,}$', s.get("sender", ""))
        ]
        if len(valid_sources) < len(sources):
            bad = [s["name"] for s in sources if s not in valid_sources]
            print(f"[fetcher] skipped gmail sources with invalid sender address: {bad}")
        sender_filter = " OR ".join(f'from:{s["sender"]}' for s in valid_sources)
        sender_map = {s["sender"]: s for s in valid_sources}

        query = f"is:unread ({sender_filter}) newer_than:{self.lookback_days}d"
        result = svc.users().messages().list(userId="me", q=query, maxResults=200).execute()
        messages = result.get("messages", [])

        articles: list[Article] = []
        company_counts: dict[str, int] = {}

        for msg_meta in messages:
            msg = svc.users().messages().get(
                userId="me", id=msg_meta["id"], format="full"
            ).execute()

            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            subject = headers.get("Subject", "(no subject)")
            from_addr = headers.get("From", "")
            sender_email = self._extract_email(from_addr)
            source = sender_map.get(sender_email)
            if not source:
                continue
            company = source["name"]

            # optional subject keyword filter (e.g. for noreply@medium.com noise reduction)
            subject_contains = source.get("subject_contains")
            if subject_contains and subject_contains.lower() not in subject.lower():
                continue

            if company_counts.get(company, 0) >= self.max_per_source:
                continue

            body_text = self._extract_gmail_body(msg)
            if not body_text:
                print(f"[fetcher] empty body from Gmail for '{subject}' — skipping")
                continue

            url = self._extract_first_url(body_text) or ""
            self._pending_gmail_ids.append(msg_meta["id"])
            articles.append(
                Article(
                    company=company,
                    title=subject,
                    url=url,
                    body=body_text[:8000],
                    source_type="gmail",
                )
            )
            company_counts[company] = company_counts.get(company, 0) + 1

        return articles

    def _get_gmail_service(self):
        if self._gmail_service:
            return self._gmail_service

        # token.json persists the OAuth access + refresh tokens across runs.
        # If the access token is expired, the refresh token silently gets a new one.
        # If no token exists at all, run_local_server() opens a browser for first-time auth.
        creds = None
        token_path = self.auth_dir / "token.json"
        creds_path = self.auth_dir / "credentials.json"

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    raise RuntimeError(
                        f"Gmail token refresh failed: {e}\n"
                        "The OAuth refresh token has likely expired (Google invalidates them after 7 days "
                        "for apps in 'Testing' mode).\n"
                        "Fix: publish your Google Cloud OAuth app (Testing → Production), regenerate "
                        "token.json locally via 'python auth/setup.py', then update the GMAIL_TOKEN "
                        "secret in GitHub → Settings → Secrets."
                    ) from e
            else:
                # run_local_server() opens a browser — never works in CI.
                raise RuntimeError(
                    "No valid Gmail credentials found and interactive auth is not possible in CI.\n"
                    "Run 'python auth/setup.py' locally to generate auth/token.json, then base64-encode "
                    "it and store it as the GMAIL_TOKEN secret in GitHub → Settings → Secrets."
                )
            token_path.write_text(creds.to_json())

        self._gmail_service = build("gmail", "v1", credentials=creds)
        return self._gmail_service

    @staticmethod
    def _extract_gmail_body(msg: dict) -> str:
        # Gmail messages are MIME trees: a single email can nest multipart/alternative
        # inside multipart/mixed, etc. We walk the tree recursively, preferring HTML
        # (which trafilatura can clean up) over plain text, returning the first hit.
        payload = msg.get("payload", {})

        def _get_parts(part):
            mime = part.get("mimeType", "")
            if mime == "text/html":
                data = part.get("body", {}).get("data", "")
                if data:
                    html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    return trafilatura.extract(html) or ""
            if mime == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            for sub in part.get("parts", []):
                result = _get_parts(sub)
                if result:
                    return result
            return ""

        return _get_parts(payload)

    @staticmethod
    def _extract_email(from_header: str) -> str:
        if "<" in from_header:
            return from_header.split("<")[-1].rstrip(">").strip().lower()
        return from_header.strip().lower()

    @staticmethod
    def _extract_first_url(text: str) -> str:
        import re
        match = re.search(r"https?://[^\s\)\"']+", text)
        return match.group(0) if match else ""

    # ── RSS ───────────────────────────────────────────────────────────────────

    def _fetch_rss(self, sources: list[dict]) -> list[Article]:
        conn = self._db_conn()
        articles: list[Article] = []
        failed_sources: list[str] = []

        for source in sources:
            try:
                feed = feedparser.parse(source["url"])
                total_entries = len(feed.entries)
                already_seen = 0
                too_old = 0
                no_body = 0
                count = 0

                for entry in feed.entries:
                    if count >= self.max_per_source:
                        break

                    guid = entry.get("id") or entry.get("link", "")
                    if self._rss_already_processed(conn, guid):
                        already_seen += 1
                        continue

                    pub = self._parse_rss_date(entry)
                    if pub and pub < self.cutoff:
                        too_old += 1
                        continue

                    url = entry.get("link", "")
                    body = self._fetch_url_body(url)
                    if not body:
                        body = entry.get("summary", "")[:4000]
                    if not body:
                        no_body += 1
                        continue

                    articles.append(
                        Article(
                            company=source["name"],
                            title=entry.get("title", "(untitled)"),
                            url=url,
                            body=body[:8000],
                            source_type="rss",
                            guid=guid,
                        )
                    )
                    count += 1

                skipped = already_seen + too_old + no_body
                print(
                    f"[fetcher] {source['name']}: {total_entries} in feed, "
                    f"{count} new | {already_seen} seen, {too_old} too old, {no_body} no body"
                )
            except Exception as e:
                print(f"[fetcher] RSS error for {source['name']}: {e}")
                failed_sources.append(source["name"])

        if failed_sources:
            print(f"[fetcher] failed sources ({len(failed_sources)}): {', '.join(failed_sources)}")

        conn.close()
        return articles

    def _rss_already_processed(self, conn: sqlite3.Connection, guid: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM rss_articles WHERE guid = ?", (guid,)
        ).fetchone()
        return row is not None

    def _db_conn(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS rss_articles (
                guid TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                url TEXT NOT NULL,
                processed_at TIMESTAMP NOT NULL
            )"""
        )
        conn.commit()
        return conn

    @staticmethod
    def _parse_rss_date(entry) -> datetime | None:
        try:
            t = entry.get("published_parsed") or entry.get("updated_parsed")
            if t:
                return datetime(*t[:6], tzinfo=timezone.utc)
        except Exception:
            pass
        return None

    @staticmethod
    def _fetch_url_body(url: str) -> str:
        if not url:
            return ""
        try:
            downloaded = trafilatura.fetch_url(url, timeout=15)
            if downloaded:
                return trafilatura.extract(downloaded) or ""
        except Exception:
            pass
        return ""
