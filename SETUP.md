# PM Engineering Digest — Setup Guide

A weekly email digest of engineering blog posts from top tech companies, framed for Product Managers.

---

## Prerequisites

- **Python 3.12+** — check with `python3 --version`. Install from python.org if needed.
- **Git** — to push to GitHub for the weekly cron to run.
- **An Anthropic API key** — from console.anthropic.com.
- **A Google account** — jatin0331@gmail.com (already configured in settings.yaml).

---

## Step 1 — Clone and set up Python environment

```bash
cd ~/Code/Personal
# create an isolated Python environment (prevents dependency conflicts)
python3 -m venv pm-digest-env
source pm-digest-env/bin/activate    # run this each time you open a terminal

cd pm-digest
pip install -r requirements.txt
```

---

## Step 2 — Set your Anthropic API key (local runs)

```bash
export ANTHROPIC_API_KEY=sk-ant-...your-key-here...
```

To avoid typing this every session, add it to your shell profile:
```bash
echo 'export ANTHROPIC_API_KEY=sk-ant-...your-key-here...' >> ~/.zshrc
```

---

## Step 3 — Google Cloud setup (one-time, ~10 minutes)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → create a new project (name it anything, e.g. "PM Digest")
2. Search for "Gmail API" in the search bar → click Enable
3. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
4. Application type: **Desktop app** → name it anything → click Create
5. Click the download icon (⬇) next to your new credential → save as `auth/credentials.json` inside the pm-digest folder

---

## Step 4 — Authenticate Gmail (one-time)

```bash
# make sure you're in the pm-digest directory with venv active
python auth/setup.py
```

This opens your browser. Log in with jatin0331@gmail.com and grant permissions.
A `auth/token.json` file is created — this is your login token. Keep it private.

---

## Step 5 — Subscribe to blog newsletters

For each blog in `config/sources.yaml` that has `type: gmail`, subscribe to their email newsletter and then check what sender address the emails actually arrive from. Update `sources.yaml` with the real sender address.

**Gmail sources that need verification** (check after subscribing):
- Zomato Engineering — `blog@zomato.com` (verify)
- Zerodha Tech — `blog@zerodha.tech` (verify)
- Stripe Engineering — `info@stripe.com` (verify)

All other sources use RSS feeds — no subscription needed for those.

---

## Step 6 — Test locally (dry run)

This fetches articles and generates the digest HTML without sending any email:

```bash
python main.py --dry-run
```

Open `digest_preview.html` in your browser to see the formatted digest.
If it looks good, do a real send:

```bash
python main.py
```

Check your Gmail inbox — you should receive the digest from yourself.

---

## Step 7 — Set up weekly GitHub Actions cron

1. Create a GitHub repo and push this project:
   ```bash
   git init
   git add .
   git commit -m "initial pm-digest setup"
   git remote add origin https://github.com/YOUR_USERNAME/pm-digest.git
   git push -u origin main
   ```

2. In your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**. Add these 3 secrets:

   | Secret name | Value |
   |---|---|
   | `ANTHROPIC_API_KEY` | Your Anthropic API key |
   | `GMAIL_CREDENTIALS` | base64 of credentials.json (see below) |
   | `GMAIL_TOKEN` | base64 of token.json (see below) |

   To get the base64 values (run in terminal):
   ```bash
   base64 -i auth/credentials.json | pbcopy   # pastes GMAIL_CREDENTIALS value
   base64 -i auth/token.json | pbcopy          # pastes GMAIL_TOKEN value
   ```

3. Go to **Actions tab** in your GitHub repo → find "Weekly PM Digest" → click **Run workflow** to test it runs end-to-end in CI.

The digest will now run automatically every Monday at 7am UTC (12:30pm IST).

---

## Customising sources

Edit `config/sources.yaml` to add or remove blogs:

- `type: rss` — just add the RSS feed URL; no subscription needed
- `type: gmail` — subscribe to their newsletter, then set the sender email address
- `subject_contains` — optional filter for gmail sources (useful if multiple blogs share the same sender domain, e.g. Medium); only emails with this string in the subject are fetched

---

## Troubleshooting

**"ANTHROPIC_API_KEY is not set"** — run `export ANTHROPIC_API_KEY=sk-ant-...` in your terminal first.

**"credentials.json not found"** — download it from Google Cloud Console (Step 3) and place it at `auth/credentials.json`.

**No articles this week** — you'll still get an email saying it was a quiet week. Check that you subscribed to newsletters and the sender addresses in sources.yaml are correct.

**Gmail token expired** — re-run `python auth/setup.py` to refresh. Then re-encode `token.json` and update the `GMAIL_TOKEN` secret in GitHub.
