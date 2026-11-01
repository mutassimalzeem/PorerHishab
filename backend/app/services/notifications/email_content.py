"""Privacy-conscious email content generation.

Adheres strictly to financial privacy principles:
- Never includes transaction amounts, account balances, merchant names,
  or financial evidence in subjects or bodies.
- Never puts financial information into URL query parameters.
- Directs users to the authenticated web application to review details.
- Supports bilingual rendering (English and Bengali).
"""
from typing import Sequence
from app.core.config import settings
from app.models.financial_alert import FinancialAlert
from app.models.notification_digest import NotificationDigest, NotificationDigestItem
from app.services.notifications.email_sender import EmailMessage

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


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


def build_privacy_safe_digest_email(
    digest: NotificationDigest,
    items: Sequence[NotificationDigestItem],
    recipient_email: str,
    language: str = "en",
) -> EmailMessage:
    """Build a consolidated, privacy-preserving daily digest email in English or Bengali."""
    is_bn = language.lower().startswith("bn")
    app_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/alerts"
    item_count = len(items)

    # Localized copy
    if is_bn:
        subject = "আপনার পরের হিসাব — আজকের আর্থিক সংক্ষিপ্তসার"
        heading = "পরের হিসাব — দৈনিক আর্থিক বিবরণী"
        summary_line = f"আজ আপনার {item_count}টি আর্থিক বিজ্ঞপ্তি রয়েছে।"
        privacy_note = (
            "আপনার আর্থিক গোপনীয়তা রক্ষার্থে কোনো নির্দিষ্ট ব্যালেন্স, লেনদেনের পরিমাণ "
            "বা অ্যাকাউন্টের বিবরণ ইমেইলে উল্লেখ করা হয় না।"
        )
        cta_text = "বিজ্ঞপ্তিগুলো পর্যালোচনা করতে পরের হিসাব খুলুন"
        footer_text = "পরের হিসাব সেটিংসে ইমেইল সংক্ষিপ্তসার সক্রিয় থাকার কারণে এই ইমেইলটি পাঠানো হয়েছে।"
        severity_labels = {
            "critical": "জরুরি",
            "high": "উচ্চ ঝুঁকি",
            "medium": "মাঝারি",
            "low": "সাধারণ",
            "info": "তথ্য",
        }
    else:
        subject = "Your PorerHishab daily financial brief"
        heading = "PorerHishab — Daily Financial Brief"
        plural = "s" if item_count != 1 else ""
        summary_line = f"You have {item_count} financial alert{plural} today."
        privacy_note = (
            "To protect your financial privacy, specific balances, transaction amounts, "
            "and account details are not included in email notifications."
        )
        cta_text = "Open PorerHishab to review these alerts"
        footer_text = "You received this because the daily digest is enabled in your PorerHishab settings."
        severity_labels = {
            "critical": "Critical",
            "high": "High",
            "medium": "Medium",
            "low": "Low",
            "info": "Info",
        }

    # Group items deterministically by severity
    groups: dict[str, list[NotificationDigestItem]] = {}
    for itm in items:
        groups.setdefault(itm.severity.lower(), []).append(itm)

    # Plain text construction
    text_sections: list[str] = [
        heading,
        "",
        summary_line,
        "",
    ]

    for sev in SEVERITY_ORDER:
        sev_items = groups.get(sev, [])
        if not sev_items:
            continue
        label = severity_labels.get(sev, sev.capitalize())
        text_sections.append(f"{label}:")
        for si in sev_items:
            text_sections.append(f"• {si.title}")
        text_sections.append("")

    text_sections.append(privacy_note)
    text_sections.append("")
    text_sections.append(f"{cta_text}: {app_url}")
    text_sections.append("")
    text_sections.append("— Team PorerHishab")

    body_text = "\n".join(text_sections)

    # HTML construction
    html_items_markup = []
    for sev in SEVERITY_ORDER:
        sev_items = groups.get(sev, [])
        if not sev_items:
            continue
        label = severity_labels.get(sev, sev.capitalize())
        color = "#dc2626" if sev == "critical" else ("#ea580c" if sev == "high" else "#0284c7")
        html_items_markup.append(
            f'<div style="margin-bottom: 16px;">'
            f'<div style="font-weight: 600; font-size: 14px; text-transform: uppercase; color: {color}; margin-bottom: 6px;">{label}</div>'
            f'<ul style="margin: 0; padding-left: 20px; color: #334155; font-size: 15px;">'
        )
        for si in sev_items:
            html_items_markup.append(f'<li style="margin-bottom: 4px;">{si.title}</li>')
        html_items_markup.append('</ul></div>')

    grouped_html = "\n".join(html_items_markup)

    body_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{subject}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; color: #1e293b; padding: 24px; background-color: #f8fafc;">
  <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; padding: 32px;">
    <div style="margin-bottom: 20px;">
      <h2 style="margin: 0; color: #0f172a; font-size: 20px;">{heading}</h2>
    </div>
    <p style="font-size: 16px; margin: 0 0 20px 0; color: #334155; font-weight: 500;">
      {summary_line}
    </p>
    <div style="margin-bottom: 24px; background: #f8fafc; border-radius: 6px; padding: 16px; border: 1px solid #f1f5f9;">
      {grouped_html}
    </div>
    <p style="font-size: 13px; margin: 0 0 24px 0; color: #64748b;">
      {privacy_note}
    </p>
    <div style="margin-bottom: 28px;">
      <a href="{app_url}" style="display: inline-block; background-color: #0f172a; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 500; font-size: 15px;">
        {cta_text}
      </a>
    </div>
    <hr style="border: 0; border-top: 1px solid #f1f5f9; margin: 24px 0 16px 0;" />
    <p style="font-size: 12px; color: #94a3b8; margin: 0;">
      {footer_text}
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
