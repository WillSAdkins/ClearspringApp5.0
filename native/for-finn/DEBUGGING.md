# Rock Slinger — the crash on losing your last life

## What's happening

When the player runs out of lives, the game stops with:

```
RuntimeError: null function
```

That's a WebAssembly error, not a website one. Something in the game calls a
function pointer that isn't there.

I checked the build: it contains only Unity's standard `_JS_*` functions and
no custom externs, so this isn't the leaderboard bridge — it happens without
that. It's inside the game's own code.

## The most likely cause: managed code stripping

Unity's IL2CPP builds strip out code it thinks is unused. It works that out
statically, so anything reached only through **reflection, a delegate, or a
UnityEvent wired up in the Inspector** can look unused and get removed. Then
calling it at runtime lands on a null function pointer.

Game over is a classic place for this, because it's often the one path that
uses an event or a callback nothing else calls.

### Try this first

**Player Settings → Other Settings → Managed Stripping Level → Minimal**
(or Disabled), rebuild, and see if it goes away. It's a thirty-second test
and it either confirms the diagnosis or rules it out.

If that fixes it, you can either leave it on Minimal — the build gets a bit
larger, which given it's already 11 MB is not the end of the world — or keep
High and add a `link.xml` to preserve the specific types involved.

## If that isn't it

**Build a Development build.** Player Settings → check *Development Build*.
The error will then name the actual C# method instead of a hex address, which
usually makes it obvious. Don't ship that build — just use it to find the
problem.

**Look for a null reference on the game-over path.** A `UnityEvent` with a
missing target, a `static` event nothing subscribed to, an `Action` invoked
without a `?.`, or a `Destroy()`d object being called afterwards.

## Also worth knowing

**Sound sometimes triggers this.** Unity WebGL audio behaves differently from
the editor, and playing a clip on a destroyed AudioSource at game over can
present this way.

**Test in the browser, not the editor.** WebGL-only problems don't reproduce
in play mode. Unity's *Build and Run* serves it locally so you can reproduce
it quickly.

## On our side

The website no longer throws a browser alert when this happens. Runtime
errors are logged to the console and, if the game genuinely stops, a small
message appears at the bottom of the canvas instead. That makes it less
alarming for a child, but it doesn't fix the underlying crash — that needs
the Unity project.

## When you rebuild

Send Will the whole `Build` folder. He needs these four files:

```
2DDGWebgl.loader.js
2DDGWebgl.framework.js.br
2DDGWebgl.wasm.br
2DDGWebgl.data.br
```

The `BurstDebugInformation_DoNotShip` folder isn't needed.
