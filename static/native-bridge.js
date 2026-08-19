/*
 * native-bridge.js
 *
 * Loaded on every page. Does nothing at all in a normal browser.
 *
 * When the site is running inside the Capacitor native shell (the iOS/Android
 * app), this adapts the page for it:
 *   - marks <html> with data-native so CSS can target the app build
 *   - swaps web push for native push registration
 *   - sends payment/giving links out to the system browser (App Store rules)
 *   - hides "install this app" prompts, which make no sense once installed
 */
(function () {
  "use strict";

  const isNative = !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());

  if (!isNative) return;

  const platform = window.Capacitor.getPlatform(); // "ios" | "android"
  const root = document.documentElement;
  root.setAttribute("data-native", platform);

  /* ------------------------------------------------------------------ *
   * 1. Hide anything that only makes sense on the web
   * ------------------------------------------------------------------ */
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-web-only]").forEach(function (el) {
      el.hidden = true;
    });
  });

  /* ------------------------------------------------------------------ *
   * 2. External + payment links open in the system browser
   *
   * Apple rejects apps that take payment through an embedded webview.
   * Routing giving/store out to Safari or Chrome keeps the flow compliant
   * and also means saved cards and wallet autofill actually work.
   * ------------------------------------------------------------------ */
  const EXTERNAL_PREFIXES = ["/giving", "/store"];

  document.addEventListener("click", function (event) {
    const link = event.target.closest("a[href]");
    if (!link) return;

    const href = link.getAttribute("href") || "";
    if (href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) return;

    let url;
    try {
      url = new URL(href, window.location.origin);
    } catch (e) {
      return;
    }

    const isOffsite = url.origin !== window.location.origin;
    const isPayment = EXTERNAL_PREFIXES.some(function (p) {
      return url.pathname.startsWith(p);
    });
    const isFlagged = link.hasAttribute("data-external");

    if (isOffsite || isPayment || isFlagged) {
      event.preventDefault();
      if (window.Capacitor.Plugins.Browser) {
        window.Capacitor.Plugins.Browser.open({ url: url.href, presentationStyle: "popover" });
      } else {
        window.open(url.href, "_system");
      }
    }
  }, true);

  /* ------------------------------------------------------------------ *
   * 3. Native push notifications
   *
   * The web build uses the Push API with a VAPID key. That does not exist
   * inside a native webview, so we register with APNs/FCM instead and post
   * the resulting token to the same endpoint, tagged by platform.
   * ------------------------------------------------------------------ */
  const Push = window.Capacitor.Plugins.PushNotifications;

  window.ClearspringNative = {
    platform: platform,

    enablePush: async function () {
      if (!Push) throw new Error("Push plugin unavailable");

      let perm = await Push.checkPermissions();
      if (perm.receive === "prompt" || perm.receive === "prompt-with-rationale") {
        perm = await Push.requestPermissions();
      }
      if (perm.receive !== "granted") return { ok: false, reason: "denied" };

      await Push.register();
      return { ok: true };
    },

    disablePush: async function () {
      const token = sessionStorage.getItem("cs_native_push_token");
      if (!token) return;
      await fetch("/api/push/unsubscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ native_token: token, platform: platform }),
      });
      sessionStorage.removeItem("cs_native_push_token");
    },
  };

  if (Push) {
    Push.addListener("registration", function (token) {
      sessionStorage.setItem("cs_native_push_token", token.value);
      fetch("/api/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ native_token: token.value, platform: platform }),
      }).catch(function () { /* retried next launch */ });
    });

    Push.addListener("registrationError", function (err) {
      console.warn("Push registration failed", err);
    });

    // Tapping a notification should land you on the relevant page.
    Push.addListener("pushNotificationActionPerformed", function (action) {
      const path = action.notification && action.notification.data && action.notification.data.url;
      if (path) window.location.assign(path);
    });
  }

  /* ------------------------------------------------------------------ *
   * 4. Android hardware back button
   * ------------------------------------------------------------------ */
  const App = window.Capacitor.Plugins.App;
  if (App && platform === "android") {
    App.addListener("backButton", function (info) {
      if (info.canGoBack) {
        window.history.back();
      } else {
        App.exitApp();
      }
    });
  }
})();
