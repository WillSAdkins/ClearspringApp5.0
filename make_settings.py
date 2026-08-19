"""Creates settings.bat with a fresh admin password and notification keys.

Run via setup.bat rather than directly.
"""

import base64
import os
import secrets

WORDS = """anchor beacon canyon cedar clover compass copper cotton crimson
dawn delta ember falcon forest garnet gentle granite harbour harvest hazel
iron ivory jasper juniper kettle lantern laurel linen meadow mineral north
oakwood orchard pebble pilgrim quarry quiet rowan saffron sandstone shelter
silver spruce stanza summit thistle timber vessel violet walnut willow winter"""\
    .split()


def make_password(words=4):
    return "-".join(secrets.choice(WORDS) for _ in range(words))


def make_vapid_keys():
    """Returns (public, private), or (None, None) if cryptography is missing."""
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        return None, None

    def b64url(raw):
        return base64.urlsafe_b64encode(raw).decode("utf8").rstrip("=")

    private_key = ec.generate_private_key(ec.SECP256R1())
    public = b64url(private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    ))
    private = b64url(
        private_key.private_numbers().private_value.to_bytes(32, "big")
    )
    return public, private


def main():
    password = make_password()
    secret_key = secrets.token_urlsafe(48)
    vapid_public, vapid_private = make_vapid_keys()

    lines = [
        "@echo off",
        "REM  Your private settings. Keep this file off GitHub.",
        "REM  Created by setup.bat - re-run that to start fresh.",
        "",
        f"set ADMIN_PASSWORD={password}",
        f"set SECRET_KEY={secret_key}",
        "",
    ]

    if vapid_public:
        lines += [
            "REM  Notification keys. Changing these signs everyone out of",
            "REM  notifications, so keep them as they are.",
            f"set VAPID_PUBLIC_KEY={vapid_public}",
            f"set VAPID_PRIVATE_KEY={vapid_private}",
            "set VAPID_SUBJECT=mailto:hello@clearspringchurch.com",
            "",
        ]

    lines += [
        "REM  Bible study assistant. Get a free key from",
        "REM  https://aistudio.google.com then remove the REM below.",
        "REM  set GEMINI_API_KEY=your-key-here",
        "",
    ]

    with open("settings.bat", "w") as f:
        f.write("\n".join(lines))

    print()
    print("   Your admin password is:")
    print()
    print(f"       {password}")
    print()
    print("   Saved to settings.bat")
    if vapid_public:
        print("   Notification keys generated too.")
    else:
        print("   (Notification keys skipped - packages not installed yet.)")


if __name__ == "__main__":
    main()
