"""Privacy-conscious email content generation.

Adheres strictly to financial privacy principles:
- Never includes transaction amounts, account balances, merchant names,
  or financial evidence in subjects or bodies.
- Never puts financial information into URL query parameters.
- Directs users to the authenticated web application to review details.
"""
from app.core.config import settings
from app.models.financial_alert import FinancialAlert
from app.services.notifications.email_sender import EmailMessage


def build_privacy_safe_alert_email(
    alert: FinancialAlert,
    recipient_email: str,
) -> EmailMessage:
    """Build a privacy-preserving email notification for a financial alert."""
    severity = alert.severity.lower()
    is_critical = severity == "critical"

    if is_critical:
        subject = "PorerHishab critical financial alert"
        summary_line = "PorerHishab has detected a critical financial alert that requires your immediate attention."
    else:
        subject = "PorerHishab financial alert"
        summary_line = "PorerHishab has a financial alert that may need your attention."

    app_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/alerts"

    body_text = (
        f"{summary_line}\n\n"
        f"To protect your financial privacy, specific balances, amounts, and account details "
        f"are not included in email notifications.\n\n"
        f"Please sign in to PorerHishab to review this alert and take recommended action:\n"
        f"{app_url}\n\n"
        f"— Team PorerHishab"
    )

    body_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{subject}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; color: #1e293b; padding: 24px; background-color: #f8fafc;">
  <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; padding: 32px;">
    <div style="display: flex; align-items: center; margin-bottom: 20px;">
      <h2 style="margin: 0; color: #0f172a; font-size: 20px;">PorerHishab</h2>
    </div>
    <p style="font-size: 16px; margin: 0 0 16px 0; color: #334155;">
      {summary_line}
    </p>
    <p style="font-size: 14px; margin: 0 0 24px 0; color: #64748b;">
      To protect your financial privacy, specific balances, account numbers, and transaction details are never included in email notifications.
    </p>
    <div style="margin-bottom: 28px;">
      <a href="{app_url}" style="display: inline-block; background-color: #0f172a; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 500; font-size: 15px;">
        Open PorerHishab
      </a>
    </div>
    <hr style="border: 0; border-top: 1px solid #f1f5f9; margin: 24px 0 16px 0;" />
    <p style="font-size: 12px; color: #94a3b8; margin: 0;">
      You received this because email notifications are enabled in your PorerHishab settings.
    </p>
  </div>
</body>
</html>"""

    return EmailMessage(
        recipient=recipient_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )
