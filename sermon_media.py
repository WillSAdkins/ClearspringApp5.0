"""Helpers for sermon media: turning share URLs into embeddable players,
and generating a podcast RSS feed from the sermon archive."""

import re
from datetime import datetime
from xml.sax.saxutils import escape


# ---------- Video embeds ----------

_YT_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/live/)([A-Za-z0-9_-]{6,})"),
    re.compile(r"youtube\.com/embed/([A-Za-z0-9_-]{6,})"),
]
_VIMEO = re.compile(r"vimeo\.com/(?:video/)?(\d+)")
_FB = re.compile(r"facebook\.com/.+/videos/(\d+)")


def embed_url(url):
    """Return an embeddable player URL, or None if we don't recognise it."""
    if not url:
        return None
    url = url.strip()

    for pat in _YT_PATTERNS:
        m = pat.search(url)
        if m:
            # Standard youtube.com/embed is the most permissive host. The
            # nocookie variant blocks playback for some videos and contexts.
            return f"https://www.youtube.com/embed/{m.group(1)}"

    m = _VIMEO.search(url)
    if m:
        return f"https://player.vimeo.com/video/{m.group(1)}"

    m = _FB.search(url)
    if m:
        from urllib.parse import quote
        return f"https://www.facebook.com/plugins/video.php?href={quote(url, safe='')}"

    return None


def thumbnail_url(url):
    """Best-effort poster image for a sermon video."""
    if not url:
        return None
    for pat in _YT_PATTERNS:
        m = pat.search(url)
        if m:
            return f"https://i.ytimg.com/vi/{m.group(1)}/hqdefault.jpg"
    return None


def format_duration(seconds):
    if not seconds:
        return None
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ---------- Podcast feed ----------

def _rfc2822(date_str):
    """Convert YYYY-MM-DD to an RFC-2822 date for RSS."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        d = datetime.now()
    return d.strftime("%a, %d %b %Y 09:00:00 +0000")


def build_podcast_feed(sermons, church_name, site_url, feed_url, description=None):
    """Generate an iTunes-compatible podcast RSS feed from sermon rows.

    Only sermons with an audio_url are included — a podcast item needs an
    enclosure, so video-only sermons are skipped.
    """
    desc = description or f"Sermons from {church_name}."
    items = []

    for s in sermons:
        if not s["audio_url"]:
            continue
        title = escape(s["title"] or "Sermon")
        speaker = escape(s["speaker"] or church_name)
        summary_bits = []
        if s["passage"]:
            summary_bits.append(str(s["passage"]))
        if s["summary"]:
            summary_bits.append(str(s["summary"]))
        summary = escape(" — ".join(summary_bits)) if summary_bits else title

        duration = format_duration(s["duration_seconds"]) or ""
        dur_tag = f"<itunes:duration>{duration}</itunes:duration>" if duration else ""

        items.append(f"""    <item>
      <title>{title}</title>
      <description>{summary}</description>
      <itunes:author>{speaker}</itunes:author>
      <itunes:summary>{summary}</itunes:summary>
      {dur_tag}
      <enclosure url="{escape(s['audio_url'])}" type="audio/mpeg" length="0"/>
      <guid isPermaLink="false">sermon-{s['id']}@{escape(site_url)}</guid>
      <pubDate>{_rfc2822(s['preached_on'])}</pubDate>
    </item>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{escape(church_name)} Sermons</title>
    <link>{escape(site_url)}</link>
    <language>en-gb</language>
    <description>{escape(desc)}</description>
    <itunes:author>{escape(church_name)}</itunes:author>
    <itunes:summary>{escape(desc)}</itunes:summary>
    <itunes:category text="Religion &amp; Spirituality"/>
    <itunes:explicit>false</itunes:explicit>
    <atom:link xmlns:atom="http://www.w3.org/2005/Atom" href="{escape(feed_url)}" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>"""
