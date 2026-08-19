# Clearspring App — vision, goals and plan

*Written August 2026. Doubles as a context file: paste this at the start of a
new Claude chat and you won't have to re-explain the project.*

---

## Where it actually stands

- **115 routes, ~7,000 lines of Python, 76 templates.** Deployed on Render
  Starter with SQLite on a persistent disk.
- **Working:** Bible reading with multiple translations, reading plans,
  devotionals, prayer wall, Q&A, sermon archive, events calendar, giving,
  store, nine games, member accounts, streaks and badges, AI study assistant.
- **Built but not live:** native iOS/Android shell (Capacitor), the visit page
  (empty), NIV support (needs a licence decision).
- **Not configured:** outgoing email. This blocks more than it looks —
  sign-in links don't send, so nothing account-based works for anyone.

**The number worth staring at: 50 of the 115 routes are admin pages.** Nearly
half this app exists for whoever maintains it. For a volunteer-run church
that's a real ongoing cost, and it's the strongest argument against adding
more features.

---

## The strategic choice

Reading your church's site, Clearspring has two distinct audiences already:

1. **The Cheltenham congregation** — Sunday 11am, Kids Church, Teen Church,
   uni students, young adults, men, Vibrant Women.
2. **A national apologetics audience** — Paul is a certified apologist with
   Reasonable Faith, seven books, teaching that's reached millions, events in
   cities across the UK.

**The app currently serves only the first.** The second is arguably the
church's most distinctive asset, and nothing in the app touches it.

That's the fork. Three honest options:

### A. The congregation's weekly companion
Depth for the people already there. Bible reading, prayer, giving, kids.
*This is what you've built.* Finishing it well is the lowest-risk path.

### B. The front door
Optimised for the person who hasn't come yet. Visit page, service times,
what to expect, the latest talk — everything else secondary.
*Cheapest to achieve; the visit page is already built and empty.*

### C. The teaching platform
Paul's apologetics content, structured and searchable, for an audience well
beyond Cheltenham. Bible College material, talk archive, courses.
*Highest ceiling, biggest build, and it changes what the app is for.*

These aren't mutually exclusive, but they imply different priorities, and
trying to be all three at once is how the admin burden doubles again.

**My honest read:** B is nearly free and you're one afternoon of typing from
it. A is mostly done. C is a genuine project and worth deciding deliberately
rather than drifting into.

---

## Goals worth setting

Church app metrics are a trap — daily active users is the wrong measure for
something people should use *less* than social media, not more. Better ones:

| Goal | How you'd know |
|---|---|
| A visitor can find service time, address and parking without asking anyone | The visit page is filled in and reachable in two taps |
| Members can actually sign in | Email configured; someone outside your household completes a magic-link sign-in |
| The app is on their home screen, not in a browser tab | Published to both stores |
| Sunday content reaches people who missed it | Talks posted within 48 hours, consistently |
| Maintaining it takes under an hour a week | Honest self-assessment after a month |

That last one matters most. An app that needs three hours a week will quietly
stop being updated, and a stale church app is worse than none.

---

## Action plan

Sequenced so each phase unblocks the next. **Most of this isn't Claude work** —
that's deliberate, and it's the point of the last section.

### Phase 1 — Make what exists actually work
*Nothing new. Everything here is finishing something already built.*

1. **Configure email** (you) — get SMTP credentials, set the five variables,
   send a test from admin → Email. Unblocks every account feature.
2. **Fill in the visit page** (you) — address, parking, service time, what to
   expect. Twenty minutes. It's the destination of your most prominent button.
3. **Correct the service time** (you) — your site says 11am; the app defaulted
   to 10:30 in places.
4. **Take a database backup** (you) — admin → Data. Then do it monthly.
5. **Gather photography** (you) — the new design needs 10–15 dark-friendly
   images: congregation, worship, the building, kids work. Without these the
   redesign looks like placeholder rectangles.

### Phase 2 — Decide the direction
6. **Pick A, B or C above.** Write it down in a sentence. Everything after
   this gets measured against it.
7. **Decide on NIV** — ask API.Bible directly whether your store counts as
   commercial use. Their terms exclude NIV commercial use, and you have a shop.
8. **Decide on the redesign** — new dark design or `CLEARSPRING_THEME=classic`.
   Judge it once real photography is in.

### Phase 3 — Ship it
9. **Apple Developer account** (£79/yr) and **Google Play** (£20 one-off).
10. **Get access to a Mac** — required for iOS builds. Cloud Mac services work.
11. **Build and test on real devices** — `npx cap add ios && npx cap sync`.
12. **Write the guideline 4.2 justification** — Apple rejects "just a website
    in a wrapper". Your offline Bible reader, saved verses, journal, streaks
    and games are a real case, but it has to be argued in the review notes.
13. **Submit.** Expect at least one rejection; it's normal.

### Phase 4 — Only after all of the above
14. Whatever Phase 2 decided. If C, that's a proper project: talk archive with
    search, course structure, notes.

**What I'd resist:** more features before Phase 3. You have more surface than
one church can keep current, and an empty section reads worse than an absent
one.

---

## Working within Claude usage limits

Practical, and it matters more than people expect.

**The single biggest saving: start fresh chats.** Every message in a long
conversation re-reads the entire history, so a long thread costs dramatically
more per message than a short one — and gives worse answers, because the
signal gets buried. Our current conversation is very long. Starting clean is
cheaper *and* better.

**One work package per chat.** "Fix these four bugs" is one chat. "Add feature
X" is another. Don't run a month of work through a single thread.

**Open each new chat with:**
1. The current zip (upload it — don't ask Claude to reconstruct context)
2. This file
3. One clear task

That's a 30-second setup that replaces twenty messages of re-explaining.

**Batch requests.** "Fix A, B and C, then run the test suite" costs far less
than three separate exchanges. Ask for the change *and* the verification in
one go rather than iterating.

**Do the non-Claude work between sessions.** Look at Phase 1: five items, none
of them need Claude at all. Same for most of Phase 3. The critical path is
mostly you, and that work costs nothing against your limits.

**Don't use Claude to decide things only you can decide** — vision, whether
the design looks right, whether the photography works. Use it to build and to
check.

**When you hit a limit**, that's a good moment for the manual work rather than
waiting. There's always something in Phase 1 or 3 to be getting on with.

---

## The next three things

If you do nothing else this week:

1. Configure email
2. Fill in the visit page
3. Write your one-sentence vision

The first two are under an hour combined. The third is the one that makes
everything after it easier to decide.
