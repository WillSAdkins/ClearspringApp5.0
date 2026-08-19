"""Web push notifications.

Sending requires the `pywebpush` package and a VAPID key pair. Both are optional:
if either is missing the app runs normally and simply doesn't send. That means a
church can deploy without notifications and switch them on later.

Setup on the server:
    pip install pywebpush
    python -c "from notifications import generate_vapid_keys; generate_vapid_keys()"
then set VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY / VAPID_SUBJECT in the environment.
"""

import json
import os

import requests

try:
    from pywebpush import webpush, WebPushException
    PUSH_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on deployment
    webpush = None
    WebPushException = Exception
    PUSH_AVAILABLE = False


def _clean_key(raw):
    """Environment variables often arrive with stray quotes or whitespace,
    especially when pasted into a Windows Command Prompt. A single trailing
    space is enough to make a VAPID key invalid, so normalise it here."""
    if not raw:
        return ""
    return raw.strip().strip('"').strip("'").strip()


VAPID_PUBLIC_KEY = _clean_key(os.environ.get("VAPID_PUBLIC_KEY", ""))
VAPID_PRIVATE_KEY = _clean_key(os.environ.get("VAPID_PRIVATE_KEY", ""))
VAPID_SUBJECT = _clean_key(os.environ.get("VAPID_SUBJECT", "mailto:hello@clearspringchurch.com"))


def validate_public_key(key=None):
    """Check the public key is the 65-byte uncompressed point browsers require.

    Returns (ok, message). The browser's own error for a bad key is opaque,
    so this gives a usable explanation instead.
    """
    import base64

    key = VAPID_PUBLIC_KEY if key is None else key
    if not key:
        return False, "No public key set."
    if len(key) != 87:
        return False, (f"Public key is {len(key)} characters, expected 87. "
                       "It was probably cut short when copying, or has extra "
                       "characters on the end.")
    try:
        padded = key + "=" * ((4 - len(key) % 4) % 4)
        raw = base64.urlsafe_b64decode(padded)
    except Exception:
        return False, "Public key isn't valid base64 — check for stray spaces or quotes."
    if len(raw) != 65:
        return False, f"Public key decodes to {len(raw)} bytes, expected 65."
    if raw[0] != 4:
        return False, "Public key isn't in the uncompressed-point format browsers need."
    return True, "Public key looks valid."


# Notification types. Everything is opt-in — nothing is enabled by default.
NOTIFICATION_TYPES = [
    {
        "key": "service",
        "name": "Service reminders",
        "blurb": "A nudge before Sunday services and midweek meetings",
    },
    {
        "key": "sermon",
        "name": "New sermons",
        "blurb": "When a new message is added to the archive",
    },
    {
        "key": "event",
        "name": "Event reminders",
        "blurb": "The day before events you might want to attend",
    },
    {
        "key": "prayer",
        "name": "Prayer wall",
        "blurb": "When new requests are shared publicly. Private requests never trigger these.",
    },
    {
        "key": "emergency",
        "name": "Urgent announcements",
        "blurb": "Cancellations, closures and anything genuinely urgent",
    },
    {
        "key": "encouragement",
        "name": "Daily encouragement",
        "blurb": "A verse or short thought each morning",
    },
]

TYPE_KEYS = {t["key"] for t in NOTIFICATION_TYPES}


def is_configured():
    """True if push can actually be sent."""
    return bool(PUSH_AVAILABLE and VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)


def generate_vapid_keys():
    """Print a fresh VAPID key pair for the server environment."""
    try:
        import base64
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        print("Missing dependency. Run:  pip install pywebpush")
        return None

    def b64url(raw):
        return base64.urlsafe_b64encode(raw).decode("utf8").rstrip("=")

    # Generate a P-256 key pair directly. py_vapid wraps this same primitive,
    # but its helper API has changed between versions, so we do it ourselves.
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    # Public key as an uncompressed point — the form browsers expect for
    # applicationServerKey (65 raw bytes, 87 chars once base64url encoded).
    public = b64url(
        public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
    )

    # Private key as the raw 32-byte scalar, which is what pywebpush accepts.
    private = b64url(private_key.private_numbers().private_value.to_bytes(32, "big"))

    print("VAPID keys generated.\n")
    print("Windows (this session only):")
    print(f'  set VAPID_PUBLIC_KEY={public}')
    print(f'  set VAPID_PRIVATE_KEY={private}')
    print('  set VAPID_SUBJECT=mailto:you@clearspringchurch.com')
    print("\nMac/Linux:")
    print(f'  export VAPID_PUBLIC_KEY={public}')
    print(f'  export VAPID_PRIVATE_KEY={private}')
    print('  export VAPID_SUBJECT=mailto:you@clearspringchurch.com')
    print("\nKeep the private key secret. Never commit it to GitHub.")
    return public, private


def native_is_configured():
    """True when a Firebase server key is present for the native apps."""
    return bool(os.environ.get("FCM_SERVER_KEY"))


def send_to_native(token, platform, title, body, url="/", tag=None):
    """Send to an iOS/Android device via Firebase Cloud Messaging.

    FCM fronts APNs for iOS, so one key covers both stores. Returns
    (ok, should_remove_subscription) to match the Web Push signature.
    """
    key = os.environ.get("FCM_SERVER_KEY")
    if not key:
        return False, False

    try:
        resp = requests.post(
            "https://fcm.googleapis.com/fcm/send",
            headers={
                "Authorization": f"key={key}",
                "Content-Type": "application/json",
            },
            json={
                "to": token,
                "notification": {"title": title, "body": body},
                "data": {"url": url, "tag": tag or "clearspring"},
                "priority": "high",
            },
            timeout=10,
        )
    except Exception:
        return False, False

    if resp.status_code == 200:
        try:
            result = resp.json()
        except ValueError:
            return True, False
        # A failure naming an unregistered token means the app was deleted.
        for item in result.get("results", []):
            if item.get("error") in ("NotRegistered", "InvalidRegistration"):
                return False, True
        return result.get("success", 0) > 0, False

    return False, resp.status_code in (400, 404)


def send_to_subscription(subscription_info, title, body, url="/", tag=None):
    """Send one notification. Returns (ok, should_remove_subscription)."""
    # Native app tokens take a different path entirely — no VAPID involved.
    if isinstance(subscription_info, dict) and subscription_info.get("native"):
        return send_to_native(
            subscription_info.get("token", ""),
            subscription_info.get("platform", ""),
            title, body, url, tag,
        )

    if not is_configured():
        return False, False

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "tag": tag or "clearspring",
    })

    try:
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_SUBJECT},
            timeout=10,
        )
        return True, False
    except WebPushException as e:
        # 404/410 mean the subscription is dead and should be cleaned up.
        status = getattr(getattr(e, "response", None), "status_code", None)
        return False, status in (404, 410)
    except Exception:
        return False, False
