"""Safeguarding screen for prayer requests.

Public prayer requests publish instantly, EXCEPT where the text suggests a
situation that a person should see before it goes on a public wall:
self-harm, abuse, safeguarding concerns involving children, or disclosure of
a named third party's private circumstances.

This is deliberately cautious. A false hold costs a short delay; a false
publish can expose someone in crisis or name a person who never consented.
It is a safety net, not a substitute for pastoral care or a safeguarding policy.
"""

import re

# Grouped so the admin queue can show *why* something was held.
RISK_PATTERNS = {
    "self-harm or suicide": [
        r"\bsuicid\w*", r"\bkill(?:ing)? (?:myself|herself|himself|themsel\w+)\b",
        r"\bend(?:ing)? (?:my|it all|my own)?\s*life\b", r"\bend(?:ing)? it all\b",
        r"\btak(?:e|ing) my (?:own )?life\b", r"\bself[- ]?harm\w*",
        r"\bcut(?:ting|s)? (?:myself|himself|herself|themselves|(?:my|his|her|their) (?:arm|wrist|leg)\w*)\b",
        r"\bdon'?t want to (?:be here|live|go on|wake up)\b",
        r"\bwant(?:ed)? to die\b", r"\boverdos\w*",
        r"\bno reason to live\b", r"\bbetter off without me\b",
        r"\bhurt(?:ing)? myself\b",
    ],
    "abuse or violence": [
        r"\babus\w*", r"\bassault\w*", r"\brape\w*", r"\bmolest\w*",
        r"\bbeat(?:s|en|ing)? me\b", r"\bhit(?:s|ting)? me\b", r"\bhurt(?:s|ing)? me\b",
        r"\bdomestic violence\b", r"\bviolent\b", r"\bthreaten\w*",
        r"\btrafficked?\b", r"\bgroom(?:ed|ing)\b",
    ],
    "child safeguarding": [
        r"\bmy (?:son|daughter|child|kid)\b.{0,40}\b(?:hurt|abus\w*|scared|afraid|unsafe|touch\w*)",
        r"\bchild(?:ren)?\b.{0,30}\b(?:abus\w*|unsafe|at risk|neglect\w*)",
        r"\bsocial services\b", r"\bsafeguarding\b", r"\bfoster care\b",
    ],
    "mental health crisis": [
        r"\bcrisis\b", r"\bsectioned\b", r"\bpsychiatric (?:ward|hospital)\b",
        r"\bbreakdown\b", r"\bcan'?t cope\b", r"\bdesperate\b",
    ],
    "possible third-party disclosure": [
        # Naming a person plus a sensitive circumstance.
        r"\b(?:his|her|their) (?:affair|addiction|arrest|divorce|cancer|drinking|debt)\b",
        r"\bhaving an affair\b", r"\bcheating on\b", r"\bin prison\b", r"\barrested\b",
    ],
}

_COMPILED = {
    label: [re.compile(p, re.IGNORECASE) for p in pats]
    for label, pats in RISK_PATTERNS.items()
}


def screen(text):
    """Return a reason string if this should be held for review, else None."""
    if not text:
        return None
    hits = []
    for label, patterns in _COMPILED.items():
        if any(p.search(text) for p in patterns):
            hits.append(label)
    return ", ".join(hits) if hits else None
