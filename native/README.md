# Clearspring — native app shell

This wraps the live Flask site at `https://clearspringapp3-0.onrender.com` in a
real iOS and Android app that can be submitted to the App Store and Google Play.

The Flask app is unchanged in how it works. The shell loads it, and
`static/native-bridge.js` detects the shell and adapts a few behaviours
(native push instead of web push, payments out to the system browser).

---

## What you need before starting

| Requirement | For | Cost |
|---|---|---|
| Apple Developer Program account | iOS | £79/year |
| Google Play Developer account | Android | £20 one-off |
| A Mac with Xcode | iOS builds only | — |
| Android Studio | Android builds | free |
| Node.js 18+ | both | free |
| Firebase project | push notifications | free |

iOS cannot be built without a Mac. If you don't have one, options are a
cloud Mac service (MacStadium, MacInCloud) or GitHub Actions with a macOS
runner.

---

## First-time setup

```bash
cd native
npm install
npx cap add ios
npx cap add android
npx cap sync
```

That generates `ios/` and `android/` folders containing real Xcode and
Gradle projects.

### App icons and splash screen

```bash
npm install -D @capacitor/assets
# put a 1024x1024 icon.png and 2732x2732 splash.png in native/assets/
npx capacitor-assets generate
```

You can start from `static/icons/icon-512.png`, but 1024×1024 is required
for App Store submission.

---

## Opening and running

```bash
npx cap open ios       # opens Xcode
npx cap open android   # opens Android Studio
```

Build and run onto a simulator or a plugged-in device from there.

Because `server.url` points at Render, you do **not** need to rebuild the app
when you change the website. Deploy to Render and the app picks it up on next
launch. Only changes to native config or plugins need `npx cap sync` and a
resubmission.

---

## Push notifications

The web app uses VAPID web push. That API doesn't exist inside a native
webview, so the shell registers with Firebase Cloud Messaging instead and
posts the token to your existing `/api/push/subscribe` endpoint.

1. Create a Firebase project at console.firebase.google.com
2. Add an iOS app and an Android app using the bundle ID
   `uk.org.clearspring.app`
3. Download `google-services.json` → `native/android/app/`
4. Download `GoogleService-Info.plist` → add to the Xcode project
5. For iOS, upload your APNs auth key to Firebase under
   Project Settings → Cloud Messaging
6. Set `FCM_SERVER_KEY` in your Render environment variables

Web push keeps working for browser users. The two run side by side.

---

## Things Apple will check

**Guideline 4.2 — Minimum Functionality.** This is the real risk. Apple
rejects apps that are "just a website in a wrapper." Clearspring has a
reasonable case because it has offline Bible reading, saved verses,
notifications, games, and a prayer journal — but you must make that case in
the review notes, not assume it's obvious. Write a short paragraph in App
Store Connect listing the features that behave like an app rather than a page.

**Guideline 3.2.1 — Donations.** Charitable donations must not run through
in-app purchase, and must not be collected inside the app's own webview.
`native-bridge.js` already routes `/giving` and `/store` out to the system
browser, which is the compliant path. Do not undo that.

**Sign in with Apple.** If you offer any third-party login, Apple requires
Sign in with Apple as an option too. Your magic-link email login is
first-party, so this does not currently apply.

**Privacy nutrition labels.** You collect email addresses and prayer
requests. Declare these in App Store Connect. You also need a privacy policy
URL that is reachable without logging in.

**Account deletion.** Apple requires apps with account creation to offer
in-app account deletion. Check whether `/account` has this — if not, it
needs adding before submission.

---

## Google Play notes

Play is considerably more relaxed about webview apps. The main requirements
are a privacy policy, a data safety form, and a target API level that is
current (Capacitor 6 handles this).

Play now requires new personal developer accounts to run a 14-day closed
test with 12+ testers before production release. Organisation accounts are
exempt. A church registering as an organisation avoids this.

---

## Updating

| Changed | Action |
|---|---|
| Website content, templates, routes | Deploy to Render. Nothing else. |
| Capacitor plugins or config | `npx cap sync`, rebuild, resubmit |
| App icon or name | rebuild, resubmit |

This is the main advantage of this approach — almost all of your ongoing
work needs no store review at all.
