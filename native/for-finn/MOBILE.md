# Making Rock Slinger work on phones

## What we're up against

Unity's own documentation says WebGL "is not currently supported on mobile
devices — it may still work, especially on high-end devices, but many current
devices are not powerful enough and don't have enough memory."

So this isn't a bug we've introduced. But the build is also carrying a lot it
doesn't need, and that's fixable.

## What we measured

Decompressing your build:

| File | Download | In memory |
|---|---|---|
| `2DDGWebgl.wasm.br` | 6.5 MB | **25.4 MB** |
| `2DDGWebgl.data.br` | 4.2 MB | **11.6 MB** |

**~37 MB before the game has allocated anything.** For a 2D game that's
roughly double what's typical — 10–16 MB of code would be normal.

Looking inside the WebAssembly, it contains references to engine modules the
game can't be using:

```
Terrain      79     Cloth        13
AR          207     VR           44
Navigation    1     ParticleSystem 42
```

Terrain and Cloth in a 2D sling game is pure dead weight. That points at one
setting.

---

## The changes worth making, roughly in order of payoff

### 1. Strip engine code

**Player Settings → Other Settings → Strip Engine Code: ✓ enabled**

This is what removes Terrain, Cloth, VR, AR and the rest. On a build carrying
this much unused engine, it's usually the single biggest saving.

### 2. Managed stripping — but carefully

**Player Settings → Other Settings → Managed Stripping Level: Medium**

You'll remember High is what we suspected for the game-over crash. Medium is
a reasonable middle ground. If it reintroduces the crash, drop to Minimal and
add a `link.xml` preserving only the types involved.

### 3. Code optimisation for size

**Build Settings → Code Optimization: Size** (rather than Speed or Runtime
Speed). Slightly slower execution, meaningfully smaller download.

### 4. Disable exceptions

**Player Settings → Publishing Settings → Enable Exceptions: None**

Worth checking — your build already looks clean here, so this may already be
set. If it isn't, it's a large saving.

### 5. Textures — this is where the 11.6 MB of data goes

- **Max Size 1024** (or 512) on sprites that don't need more. A phone screen
  can't show the difference.
- **Compression: ASTC** rather than uncompressed or RGBA32.
- Check the **Sprite Atlas** — if sprites aren't atlased, they're costing far
  more memory than they need to.

Unity's **Build Report** (Window → Analysis → Build Report, or the Editor log
after a build) lists assets by size. That will tell you in a minute where the
11.6 MB actually is, rather than guessing.

### 6. Audio

Set clips to **Compressed In Memory**, or **Streaming** for anything long.
Uncompressed audio is a common hidden cost.

### 7. Memory settings

**Player Settings → Publishing Settings:**
- **Initial Memory Size:** try 32 MB rather than higher
- **Memory Growth Mode:** Geometric

The build currently declares a 2 GB ceiling. iOS Safari will never grant that,
and asking for less up front makes Safari far more likely to say yes.

---

## A realistic expectation

Doing all of the above might get the code from 25 MB to somewhere around
12–15 MB, and the assets down meaningfully too. That's a real improvement and
may well be enough for a recent iPhone.

It probably won't make it work on an older or budget phone. That's a hardware
limit rather than a settings problem.

## The honest alternative

Rock Slinger is a 2D game with sprites and simple physics. The other nine
games in the app are plain HTML and JavaScript — they're a few kilobytes each
and run perfectly on every phone, including old ones.

Rebuilding it that way would be a genuine piece of work, but it would be
maybe 100 KB instead of 11 MB, would load instantly, and would never hit any
of this. If you'd enjoy that, it's worth considering — and Will has the whole
pattern to copy from in the existing games.

If you'd rather stay in Unity, that's completely reasonable. The settings
above are the right path, and the game can simply be the one that's best on a
tablet or computer.

## Either way

There's now a "Will it work on this device?" check on the game page. It runs
the same tests Unity's loader runs and says which one fails. Worth using it
before and after a rebuild — it'll tell you whether you've actually moved the
needle.
