import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .compiler import DigestContent


class SenderAgent:
    def __init__(self, gmail_service, recipient: str, sender: str):
        self.svc = gmail_service
        self.recipient = recipient
        self.sender = sender
        self.jinja = Environment(loader=FileSystemLoader("templates"), autoescape=True)

    def run(self, digest: DigestContent) -> bool:
        tmpl = self.jinja.get_template("digest.html.jinja2")
        html = tmpl.render(digest=digest)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = digest.subject
        msg["From"] = self.sender
        msg["To"] = self.recipient
        msg.attach(MIMEText(html, "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        try:
            self.svc.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()
        except Exception as e:
            print(f"    Failed to send: {e}", file=__import__("sys").stderr)
            raise
        print("    Digest delivered successfully")
        return True
