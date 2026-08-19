// Shared "publish score" helper used by every game's end screen.
// Nothing is sent anywhere unless the player taps the publish button —
// there is no automatic score reporting.
window.ChurchLeaderboard = (function () {
  function csrfToken() {
    return document
      .querySelector('meta[name="csrf-token"]')
      ?.getAttribute("content");
  }

  function isSignedIn() {
    return (
      document.querySelector('meta[name="member-signed-in"]')?.getAttribute("content") === "true"
    );
  }

  async function publish(gameKey, score, resultEl, button) {
    if (!isSignedIn()) {
      resultEl.innerHTML =
        'Sign in to publish your score. <a href="/account/signin">Sign in</a>';
      return;
    }

    if (button) button.disabled = true;
    resultEl.textContent = "Publishing…";
    try {
      const res = await fetch(`/games/${gameKey}/score`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken() || "",
        },
        body: JSON.stringify({ score }),
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        resultEl.textContent = data.error || "Couldn't publish your score. Try again.";
        if (button) button.disabled = false;
        return;
      }
      if (data.signed_in === false) {
        resultEl.innerHTML =
          'Sign in to publish your score. <a href="/account/signin">Sign in</a>';
        if (button) button.disabled = false;
        return;
      }
      resultEl.textContent = data.improved
        ? "Published to the leaderboard!"
        : `Saved — your best is still ${data.best}.`;
      if (button) button.textContent = "Published ✓";
    } catch (e) {
      resultEl.textContent = "Couldn't publish your score — check your connection.";
      if (button) button.disabled = false;
    }
  }

  return { publish };
})();
