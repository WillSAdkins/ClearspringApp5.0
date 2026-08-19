// ============================================================
//  ClearspringScore.cs
//
//  FOR FINN — put this anywhere in your Unity project's Assets folder,
//  for example:  Assets/Scripts/ClearspringScore.cs
//
//  Then call it once, when a game ends:
//
//      ClearspringScore.Submit(playerScore);
//
//  That's the whole integration. Everything else is handled by the page.
// ============================================================

using UnityEngine;
using System.Runtime.InteropServices;

public static class ClearspringScore
{
#if UNITY_WEBGL && !UNITY_EDITOR
    [DllImport("__Internal")]
    private static extern void ClearspringSubmitScore(int score);

    [DllImport("__Internal")]
    private static extern int ClearspringIsSignedIn();
#endif

    /// <summary>
    /// Send a final score to the Clearspring leaderboard.
    /// Safe to call from the editor or a non-WebGL build — it just logs.
    /// </summary>
    public static void Submit(int score)
    {
        if (score < 0) score = 0;

#if UNITY_WEBGL && !UNITY_EDITOR
        try
        {
            ClearspringSubmitScore(score);
        }
        catch (System.Exception e)
        {
            // Never let score reporting interrupt the game.
            Debug.LogWarning("Clearspring score submit failed: " + e.Message);
        }
#else
        Debug.Log("[Clearspring] Would submit score: " + score);
#endif
    }

    /// <summary>
    /// True when someone is signed in to the church app. Optional — use it
    /// if you want to show or hide a "save my score" prompt in-game.
    /// </summary>
    public static bool IsSignedIn
    {
        get
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            try { return ClearspringIsSignedIn() == 1; }
            catch { return false; }
#else
            return false;
#endif
        }
    }
}
