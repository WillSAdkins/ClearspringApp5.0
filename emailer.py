"""Email sending.

Uses plain SMTP, which works with almost any provider — a Gmail or Outlook
account, your church's own mail host, or a transactional service like Mailgun.

If it isn't configured the app runs normally and simply doesn't send. Features
that depend on email say so plainly rather than failing silently.

Configuration (in settings.bat locally, or your host's environment):

    SMTP_HOST      smtp.gmail.com
    SMTP_PORT      587
    SMTP_USER      you@yourchurch.com
    SMTP_PASSWORD  an app password, not your normal login password
    SMTP_FROM      "Clearspring Church <hello@clearspringchurch.com>"
    SMTP_SECURITY  starttls (default), ssl, or none
"""

import os
import re
import smtplib
import ssl as ssl_module
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or 587)
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.environ.get("SMTP_FROM", "").strip()
SMTP_SECURITY = os.environ.get("SMTP_SECURITY", "starttls").strip().lower()

# Sending is capped per run so a bug can't empty a mail quota overnight.
MAX_RECIPIENTS_PER_SEND = 200


def is_configured():
    """True if we have enough to actually send."""
    return bool(SMTP_HOST and SMTP_FROM)


def config_problems():
    """Human-readable reasons sending won't work, for the admin check page."""
    problems = []
    if not SMTP_HOST:
        problems.append("SMTP_HOST isn't set.")
    if not SMTP_FROM:
        problems.append("SMTP_FROM isn't set.")
    elif not parseaddr(SMTP_FROM)[1]:
        problems.append("SMTP_FROM doesn't contain a valid address.")
    if SMTP_HOST and not SMTP_USER:
        problems.append("SMTP_USER isn't set — most providers require it.")
    if SMTP_USER and not SMTP_PASSWORD:
        problems.append("SMTP_PASSWORD isn't set.")
    if SMTP_SECURITY not in ("starttls", "ssl", "none"):
        problems.append(f"SMTP_SECURITY is '{SMTP_SECURITY}' — expected starttls, ssl or none.")
    return problems


def _connect():
    """Open an authenticated SMTP connection."""
    if SMTP_SECURITY == "ssl":
        context = ssl_module.create_default_context()
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=context)
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
        if SMTP_SECURITY == "starttls":
            server.starttls(context=ssl_module.create_default_context())
    if SMTP_USER and SMTP_PASSWORD:
        server.login(SMTP_USER, SMTP_PASSWORD)
    return server


def send(to, subject, body_text, body_html=None, reply_to=None):
    """Send one email. Returns (ok, message) and never raises."""
    if not is_configured():
        return False, "Email isn't set up on this server."

    if not parseaddr(to)[1]:
        return False, "That doesn't look like a valid email address."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    try:
        with _connect() as server:
            server.send_message(msg)
        return True, "Sent."
    except smtplib.SMTPAuthenticationError:
        return False, ("The mail server rejected the username or password. "
                       "If you're using Gmail, you need an app password rather "
                       "than your normal one.")
    except smtplib.SMTPRecipientsRefused:
        return False, "The mail server refused that recipient address."
    except smtplib.SMTPException as e:
        return False, f"The mail server refused the message: {type(e).__name__}"
    except (OSError, ssl_module.SSLError):
        return False, ("Couldn't reach the mail server. Check the host, port "
                       "and security setting.")
    except Exception:
        return False, "Something went wrong sending that email."


# ---------- Message templates ----------

def _shell(church_name, heading, body_html, footer=None):
    """Shared HTML wrapper. Deliberately simple — email clients are fussy,
    and plain, well-spaced text renders reliably everywhere."""
    foot = footer or f"Sent by {church_name}."
    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:24px;background:#FBF8F3;
  font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#2B2622;">
  <div style="max-width:520px;margin:0 auto;background:#FFFFFF;border-radius:12px;
       padding:28px 26px;border:1px solid #E4DBCC;">
    <p style="margin:0 0 18px;font-size:12px;letter-spacing:0.14em;
       text-transform:uppercase;color:#8A5A2B;font-weight:600;">{church_name}</p>
    <h1 style="margin:0 0 16px;font-size:21px;line-height:1.3;">{heading}</h1>
    {body_html}
  </div>
  <p style="max-width:520px;margin:16px auto 0;font-size:12px;color:#7A6E60;
     text-align:center;line-height:1.5;">{foot}</p>
</body></html>"""


def send_sign_in_link(church_name, to, name, link, minutes=20):
    greeting = f"Hello {name}," if name else "Hello,"
    subject = f"Your sign-in link for {church_name}"

    text = f"""{greeting}

Here's your link to sign in to the {church_name} app:

{link}

It works once and expires in {minutes} minutes.

If you didn't ask for this, you can safely ignore this email — nobody can
sign in without opening the link above.
"""

    html = _shell(
        church_name,
        "Your sign-in link",
        f"""<p style="margin:0 0 18px;font-size:15px;line-height:1.6;">{greeting}</p>
        <p style="margin:0 0 22px;font-size:15px;line-height:1.6;">
          Tap the button below to sign in. It works once, and expires in
          {minutes} minutes.
        </p>
        <p style="margin:0 0 24px;">
          <a href="{link}" style="display:inline-block;background:#8A5A2B;color:#ffffff;
             text-decoration:none;padding:13px 26px;border-radius:999px;
             font-weight:600;font-size:15px;">Sign in</a>
        </p>
        <p style="margin:0 0 8px;font-size:13px;color:#7A6E60;line-height:1.6;">
          If the button doesn't work, copy this into your browser:
        </p>
        <p style="margin:0;font-size:12px;color:#7A6E60;word-break:break-all;">{link}</p>""",
        footer=("If you didn't ask for this, you can ignore this email. "
                "Nobody can sign in without opening the link."),
    )
    return send(to, subject, text, html)


def send_prayer_digest(church_name, to, held_count, pending_items, admin_url):
    """Daily nudge so the safeguarding queue isn't forgotten."""
    subject = (f"{held_count} prayer request{'s' if held_count != 1 else ''} "
               f"waiting for review")

    lines = "\n".join(f"  - {item}" for item in pending_items[:10])
    text = f"""There {'are' if held_count != 1 else 'is'} {held_count} prayer request{'s' if held_count != 1 else ''} held for review.

{lines}

Review them here: {admin_url}

These were held because of what they mention, so please read them personally.
"""

    items_html = "".join(
        f'<li style="margin:0 0 8px;line-height:1.5;">{item}</li>'
        for item in pending_items[:10]
    )
    html = _shell(
        church_name,
        f"{held_count} request{'s' if held_count != 1 else ''} waiting",
        f"""<p style="margin:0 0 18px;font-size:15px;line-height:1.6;">
          These were held back from the prayer wall because of what they
          mention. Please read them personally.
        </p>
        <ul style="margin:0 0 22px;padding-left:18px;font-size:14px;color:#2B2622;">{items_html}</ul>
        <p style="margin:0;">
          <a href="{admin_url}" style="display:inline-block;background:#8A5A2B;color:#ffffff;
             text-decoration:none;padding:12px 24px;border-radius:999px;
             font-weight:600;font-size:15px;">Review requests</a>
        </p>""",
    )
    return send(to, subject, text, html)


def send_test(church_name, to):
    subject = f"Test email from {church_name}"
    text = ("This is a test email from your church app.\n\n"
            "If you're reading this, email is working correctly.")
    html = _shell(
        church_name,
        "Email is working",
        """<p style="margin:0;font-size:15px;line-height:1.6;">
             If you're reading this, your app can send email. Sign-in links and
             prayer notifications will now reach people.
           </p>""",
    )
    return send(to, subject, text, html)
