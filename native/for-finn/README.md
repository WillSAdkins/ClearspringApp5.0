# Rock Slinger — adding the leaderboard

Two files to add to your Unity project, then one line of code. Everything on
the website side is already done and tested.

---

## 1. Add the plugin

Copy **`Clearspring.jslib`** into your Unity project at:

```
Assets/Plugins/WebGL/Clearspring.jslib
```

The folder matters — Unity only picks up `.jslib` files from a
`Plugins/WebGL` folder. Create it if it isn't there.

## 2. Add the script

Copy **`ClearspringScore.cs`** anywhere under `Assets/`, for example
`Assets/Scripts/ClearspringScore.cs`.

## 3. Call it when a game ends

```csharp
ClearspringScore.Submit(playerScore);
```

That's the whole integration. Call it once, on game over, with the final
score as an `int`.

Optionally, if you want to show a "save my score" prompt only when it would
actually do something:

```csharp
if (ClearspringScore.IsSignedIn) {
    // show the prompt
}
```

## 4. Rebuild and send the folder

Build for WebGL as normal and send Will the new build folder. He only needs
the `Build` directory.

---

## Notes

**It's safe to call in the editor.** Outside a WebGL build it just logs the
score to the console, so it won't break your normal testing.

**It can't break the game.** If the page doesn't provide the bridge — someone
running the build on its own, or an older version of the app — the call does
nothing and play carries on. Score reporting should never interrupt a game.

**Higher is better.** The leaderboard is set up so a bigger number wins. If
your game is actually "fewest shots" or "fastest time", say so and Will can
flip it — it's a one-word change on his side.

**The score must be a whole number, 0 or above.** Anything else is ignored
rather than saved. Decimals get truncated, so send `Mathf.RoundToInt(...)` if
your score is a float.

**Signing in is optional for players.** Anyone can play; signing in is only
needed to appear on the leaderboard. Someone signed out still sees their
score, with a note about signing in.
