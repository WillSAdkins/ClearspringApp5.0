# Editing Clearspring — where everything lives

A map of what you can change, and where. Roughly easiest first.

---

## 1. From the admin area — no code, takes effect immediately

Sign in at `/admin`.

| What | Where |
|---|---|
| The big statement on the home page | Admin → **Home** |
| Directions, parking, service times, what to expect | Admin → **Visit** |
| Sermons and talks | Admin → Sermons |
| Events and the calendar | Admin → Events |
| Devotionals | Admin → Devotionals |
| Prayer requests (approve, hide, review) | Admin → Prayers |
| Questions people have asked | Admin → Questions |
| Store products | Admin → Store |
| Giving campaigns | Admin → Giving |
| Ministries and groups | Admin → Ministries |
| Resources | Admin → Resources |
| Which features are on, and what each needs | Admin → **Status** |
| Send a test email; prayer review reminder | Admin → **Email** |
| Database size, disk space, backup and restore | Admin → **Data** |

**The home page statement** supports `*asterisks*` around one phrase, which
sets it in the italic serif. That contrast is the app's signature — use it
once per heading, not three times.

---

## 2. From environment variables — a redeploy, no code

In Render: your service → **Environment**. Locally: `settings.bat`.

| Variable | Does what |
|---|---|
| `CLEARSPRING_THEME=classic` | Switches back to the original warm cream design |
| `GEMINI_API_KEY` | Turns on the Bible study assistant |
| `API_BIBLE_KEY` | Adds NIV and other licensed translations |
| `SMTP_HOST`, `SMTP_FROM`, `SMTP_USER`, `SMTP_PASSWORD` | Outgoing email |
| `VAPID_*` | Web push notifications |
| `FCM_SERVER_KEY` | Push notifications in the native apps |
| `ADMIN_PASSWORD` | The admin password |
| `CHURCH_DB` | Where the database file lives — don't change on a live site |

Render redeploys automatically when you save. Wait for green before testing.

---

## 3. Colours and fonts — editing a file

Open `static/style.css`. The first ~70 lines are the design tokens: colours
for light and dark, the three corner radii, the four font families. Changing
a value there changes it everywhere.

To experiment safely, open `theme-editor.html` in a browser. It lets you drag
colour pickers against real components and shows contrast ratios as you go,
then gives you CSS to paste in.

The original warm design is kept intact at `static/style-classic.css`.

---

## 4. Page layout and wording in templates

`templates/` holds one file per page. `home.html` is the home page,
`bible_reader.html` the chapter reader, and so on. `base.html` is the shell
every page sits inside — the tab bar, the fonts, the back button.

Text sitting directly in these files is fixed until someone edits the file.
If you find yourself editing a template repeatedly, that's a sign the content
should move into the admin area instead.

---

## 5. New features — code

`app.py` holds the routes. This is where a genuinely new capability goes.

---

## Rule of thumb

If it changes weekly, it should be in admin. If it changes yearly, an
environment variable or the stylesheet is fine. If it's never changed, leave
it in the template.
