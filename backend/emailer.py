"""Transactional email delivery via Resend.

All email templates live here so the routers stay lean.  Emails are dispatched
synchronously inside a background task so the HTTP request returns fast.

If ``RESEND_API_KEY`` isn't configured (dev without email), we log the link and
skip the actual API call so the flow is still testable locally.
"""
from __future__ import annotations

import logging
from typing import Optional

import resend

from config import (
    APP_DEEP_LINK_SCHEME,
    PUBLIC_APP_URL,
    RESEND_API_KEY,
    RESEND_FROM_EMAIL,
)

logger = logging.getLogger(__name__)

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


# ---- URL helpers ----------------------------------------------------------
def build_verify_url(token: str) -> str:
    if PUBLIC_APP_URL:
        return f"{PUBLIC_APP_URL}/verify-email?token={token}"
    return f"{APP_DEEP_LINK_SCHEME}://verify-email?token={token}"


def build_reset_url(token: str) -> str:
    if PUBLIC_APP_URL:
        return f"{PUBLIC_APP_URL}/reset-password?token={token}"
    return f"{APP_DEEP_LINK_SCHEME}://reset-password?token={token}"


# ---- Templates ------------------------------------------------------------
_BASE_STYLE = (
    "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;"
    "background:#F4F1EA;padding:32px 16px;color:#132A1C;"
)

_BUTTON = (
    "display:inline-block;padding:14px 28px;background:#2F7A4E;color:#ffffff;"
    "text-decoration:none;border-radius:999px;font-weight:800;font-size:15px;"
)


def _wrap(inner_html: str) -> str:
    return f"""\
<!doctype html>
<html><body style=\"{_BASE_STYLE}\">
  <div style=\"max-width:520px;margin:0 auto;background:#FFFFFF;border-radius:16px;padding:32px;\">
    <div style=\"text-align:center;margin-bottom:24px;\">
      <div style=\"display:inline-block;width:48px;height:48px;border-radius:24px;background:#DCFCE7;line-height:48px;color:#14532D;font-weight:800;font-size:22px;\">⛳</div>
      <div style=\"margin-top:8px;font-weight:800;font-size:18px;letter-spacing:0.3px;\">TeeBox</div>
    </div>
    {inner_html}
    <hr style=\"border:none;border-top:1px solid #E7E4DE;margin:32px 0 16px;\"/>
    <div style=\"color:#6B7161;font-size:12px;line-height:18px;\">
      You received this email because you have (or someone claimed to have) a TeeBox account.
      If this wasn't you, you can safely ignore it.
    </div>
  </div>
</body></html>"""


def verify_email_html(display_name: str, url: str) -> str:
    inner = f"""\
<h2 style=\"margin:0 0 12px;font-size:22px;\">Welcome, {display_name or 'golfer'}!</h2>
<p style=\"margin:0 0 20px;line-height:22px;\">Please confirm your email address so we can secure your account and start showing up in the feed.</p>
<div style=\"text-align:center;margin:24px 0;\"><a href=\"{url}\" style=\"{_BUTTON}\">Verify my email</a></div>
<p style=\"margin:0;font-size:13px;color:#6B7161;line-height:20px;\">Or copy and paste this link into your browser:<br/><span style=\"word-break:break-all;color:#132A1C;\">{url}</span></p>
<p style=\"margin:16px 0 0;font-size:12px;color:#6B7161;\">This link expires in 48 hours.</p>
"""
    return _wrap(inner)


def reset_password_html(display_name: str, url: str) -> str:
    inner = f"""\
<h2 style=\"margin:0 0 12px;font-size:22px;\">Reset your password</h2>
<p style=\"margin:0 0 20px;line-height:22px;\">Hi {display_name or 'golfer'} — tap the button below to set a new password for your TeeBox account.</p>
<div style=\"text-align:center;margin:24px 0;\"><a href=\"{url}\" style=\"{_BUTTON}\">Reset password</a></div>
<p style=\"margin:0;font-size:13px;color:#6B7161;line-height:20px;\">Or copy and paste this link:<br/><span style=\"word-break:break-all;color:#132A1C;\">{url}</span></p>
<p style=\"margin:16px 0 0;font-size:12px;color:#6B7161;\">This link expires in 30 minutes and can only be used once.</p>
"""
    return _wrap(inner)


# ---- Sender ---------------------------------------------------------------
def send_email(to: str, subject: str, html: str) -> Optional[str]:
    """Fire-and-forget synchronous send. Returns the Resend message id on success."""
    if not RESEND_API_KEY:
        logger.warning(
            "RESEND_API_KEY missing — skipping real send. Subject=%r to=%r", subject, to,
        )
        return None
    try:
        result = resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
        })
        msg_id = result.get("id") if isinstance(result, dict) else None
        logger.info("Sent email %s to %s (id=%s)", subject, to, msg_id)
        return msg_id
    except Exception as e:  # noqa: BLE001
        logger.exception("Resend send failed to=%s subject=%s error=%s", to, subject, e)
        return None


def send_verify_email(to: str, display_name: str, url: str) -> None:
    send_email(to, "Verify your TeeBox email", verify_email_html(display_name, url))


def send_reset_email(to: str, display_name: str, url: str) -> None:
    send_email(to, "Reset your TeeBox password", reset_password_html(display_name, url))
