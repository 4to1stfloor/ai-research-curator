"""Email sender for paper digest reports."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Optional


class EmailSender:
    """Send paper digest reports via email (Gmail SMTP)."""

    def __init__(
        self,
        smtp_email: str,
        smtp_password: str,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
    ):
        self.smtp_email = smtp_email
        self.smtp_password = smtp_password
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port

    def send_report(
        self,
        to_email: str,
        html_path: Path,
        paper_count: int,
        date_str: str,
        subject: Optional[str] = None,
    ) -> bool:
        """Send HTML report as email attachment.

        Args:
            to_email: Recipient email address
            html_path: Path to the HTML report file
            paper_count: Number of papers in the report
            date_str: Report date string (e.g., "2026-04-02")
            subject: Custom email subject (optional)

        Returns:
            True if sent successfully, False otherwise
        """
        if not html_path.exists():
            print(f"[Email] Report file not found: {html_path}")
            return False

        subject = subject or f"[AI Research Curator] Paper Digest - {date_str} ({paper_count}편)"

        msg = MIMEMultipart()
        msg["From"] = self.smtp_email
        msg["To"] = to_email
        msg["Subject"] = subject

        body = f"""AI Research Curator - Paper Digest

날짜: {date_str}
논문 수: {paper_count}편

첨부된 HTML 파일을 브라우저에서 열어 확인하세요.
"""
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Attach HTML report
        with open(html_path, "rb") as f:
            attachment = MIMEBase("text", "html")
            attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            filename = html_path.name
            attachment.add_header(
                "Content-Disposition",
                f"attachment; filename={filename}",
            )
            msg.attach(attachment)

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_email, self.smtp_password)
                server.sendmail(self.smtp_email, to_email, msg.as_string())
            print(f"[Email] Report sent to {to_email}")
            return True
        except smtplib.SMTPAuthenticationError:
            print("[Email] Authentication failed. Check your email and app password.")
            print("[Email] Gmail requires an App Password: https://myaccount.google.com/apppasswords")
            return False
        except Exception as e:
            print(f"[Email] Failed to send: {e}")
            return False
