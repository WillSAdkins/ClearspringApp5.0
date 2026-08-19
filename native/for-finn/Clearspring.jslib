// ============================================================
//  Clearspring.jslib
//
//  FOR FINN — put this file in your Unity project at:
//
//      Assets/Plugins/WebGL/Clearspring.jslib
//
//  The folder matters. Unity only picks up .jslib files from a
//  Plugins/WebGL folder. Create it if it isn't there.
//
//  Then rebuild for WebGL and send Will the new build folder.
// ============================================================

mergeInto(LibraryManager.library, {

  // Called from C# when a game finishes.
  // The page it's running in does the actual saving — Unity can't, because
  // it has no session cookie and no CSRF token of its own.
  ClearspringSubmitScore: function (score) {
    try {
      if (typeof window !== "undefined" &&
          window.ClearspringGame &&
          window.ClearspringGame.submitScore) {
        window.ClearspringGame.submitScore(score);
      }
      // If the page doesn't provide it — someone running the build on its
      // own, or an older version of the app — nothing happens and the game
      // carries on. Never let score reporting break play.
    } catch (e) {
      console.warn("Score submission failed:", e);
    }
  },

  // Optional. Lets the game know whether there's any point offering a
  // "save my score" button: returns 1 when someone is signed in, 0 when not.
  ClearspringIsSignedIn: function () {
    try {
      return (typeof window !== "undefined" &&
              window.ClearspringGame &&
              window.ClearspringGame.signedIn) ? 1 : 0;
    } catch (e) {
      return 0;
    }
  },

});
