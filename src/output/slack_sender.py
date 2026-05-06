"""Slack DM sender for paper digest reports.

Uses Slack Bot Token (free) with the new files upload flow:
1. users.lookupByEmail - find user by email
2. conversations.open - open DM channel with user
3. files.getUploadURLExternal - get upload URL
4. POST file to upload URL
5. files.completeUploadExternal - finalize upload to DM channel

The legacy files.upload was deprecated; the new flow is the only supported way.
"""

from pathlib import Path
from typing import Optional

import requests


class SlackSender:
    """Send paper digest reports as Slack DM via Bot Token."""

    BASE_URL = "https://slack.com/api"

    def __init__(self, bot_token: str, user_email: str):
        self.bot_token = bot_token
        self.user_email = user_email
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {bot_token}",
        })

    def _api(self, method: str, **params) -> dict:
        """Call Slack Web API method."""
        r = self.session.post(
            f"{self.BASE_URL}/{method}",
            data={k: v for k, v in params.items() if v is not None},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API {method} error: {data.get('error')}")
        return data

    def _get_dm_channel(self) -> str:
        """Find user by email, open DM channel, return channel ID."""
        user_data = self._api("users.lookupByEmail", email=self.user_email)
        user_id = user_data["user"]["id"]

        dm_data = self._api("conversations.open", users=user_id)
        return dm_data["channel"]["id"]

    def _upload_file(self, file_path: Path, channel_id: str, initial_comment: str) -> bool:
        """Upload file using new files.getUploadURLExternal + completeUploadExternal flow."""
        file_size = file_path.stat().st_size
        filename = file_path.name

        # Step 1: Get upload URL
        upload_info = self._api(
            "files.getUploadURLExternal",
            filename=filename,
            length=file_size,
        )
        upload_url = upload_info["upload_url"]
        file_id = upload_info["file_id"]

        # Step 2: POST file content to upload URL (no auth header needed)
        with open(file_path, "rb") as f:
            r = requests.post(upload_url, files={"file": (filename, f)}, timeout=120)
            r.raise_for_status()

        # Step 3: Complete upload + share to channel
        import json
        self._api(
            "files.completeUploadExternal",
            files=json.dumps([{"id": file_id, "title": filename}]),
            channel_id=channel_id,
            initial_comment=initial_comment,
        )
        return True

    def send_report(
        self,
        html_path: Path,
        paper_count: int,
        date_str: str,
        changelog: Optional[str] = None,
    ) -> bool:
        """Send HTML report as DM to user.

        Args:
            html_path: Path to HTML report
            paper_count: Number of papers
            date_str: Report date (e.g., "2026-04-15")
            changelog: Optional markdown bullets describing recent updates.

        Returns:
            True on success, False on failure.
        """
        if not html_path.exists():
            print(f"[Slack] Report file not found: {html_path}")
            return False

        try:
            channel_id = self._get_dm_channel()
            comment_lines = [
                f":book: *Paper Digest - {date_str}*",
                f"논문 {paper_count}편 분석 완료. 첨부된 HTML을 다운로드하여 브라우저에서 열어 확인하세요.",
            ]
            if changelog and changelog.strip():
                comment_lines.append("")
                comment_lines.append(":sparkles: *최근 업데이트*")
                # Slack uses • for bullets visually but - works fine in mrkdwn
                for line in changelog.strip().split("\n"):
                    line = line.strip()
                    if line.startswith("- "):
                        comment_lines.append(f"• {line[2:].strip()}")
            comment = "\n".join(comment_lines)
            self._upload_file(html_path, channel_id, comment)
            print(f"[Slack] DM sent to {self.user_email}")
            return True
        except RuntimeError as e:
            err_msg = str(e)
            print(f"[Slack] {err_msg}")
            if "users_not_found" in err_msg:
                print("[Slack] Email not found in Slack workspace. Check SLACK_USER_EMAIL.")
            elif "missing_scope" in err_msg:
                print("[Slack] Bot token missing scopes. Required: chat:write, files:write, users:read, users:read.email, im:write")
            elif "invalid_auth" in err_msg:
                print("[Slack] Invalid bot token. Check SLACK_BOT_TOKEN.")
            return False
        except Exception as e:
            print(f"[Slack] Failed to send: {e}")
            return False
