"""
One-time OAuth2 setup. Run this locally before first use:
    python auth/setup.py

Requires auth/credentials.json (downloaded from Google Cloud Console).
Produces auth/token.json which the main pipeline uses.
"""
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

auth_dir = Path(__file__).parent
creds_path = auth_dir / "credentials.json"
token_path = auth_dir / "token.json"

if not creds_path.exists():
    raise FileNotFoundError(
        f"credentials.json not found at {creds_path}\n"
        "Download it from Google Cloud Console → APIs & Services → Credentials"
    )

flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
creds = flow.run_local_server(port=0)
token_path.write_text(creds.to_json())
print(f"token.json saved to {token_path}")
print("Next: base64-encode token.json and credentials.json for GitHub Actions secrets.")
print("  base64 -i auth/token.json | pbcopy       # GMAIL_TOKEN")
print("  base64 -i auth/credentials.json | pbcopy  # GMAIL_CREDENTIALS")
