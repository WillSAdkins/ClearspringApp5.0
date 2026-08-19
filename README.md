# Clearspring — Service Times

A mobile-friendly church scheduling app. Visitors see upcoming services and
events on their phone; staff sign in to add or edit them. It's a Progressive
Web App (PWA), so people can add it to their home screen and it behaves like
a real app — no App Store needed.

## Run it locally

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:5000** in your browser.

The default admin password is `changeme`. Set your own before going live:

```bash
export ADMIN_PASSWORD="your-real-password"
export SECRET_KEY="some-random-string"
python app.py
```

Staff sign in at **/admin/login**, then manage events at **/admin**.

## Rename it for your church

1. Open `templates/base.html` and `templates/index.html` if you ever want
   to rename it again — just replace "Clearspring" with the new name.
2. Open `static/manifest.json` — update `name` and `short_name` too.
3. Optional: swap `static/icons/icon-192.png` and `icon-512.png` for your
   own logo (same file names and sizes).

## Put it on people's phones

Once the app is deployed somewhere with a real URL (see below), anyone who
visits the site on their phone can:

- **iPhone (Safari):** tap Share → "Add to Home Screen"
- **Android (Chrome):** tap the menu (⋮) → "Install app" (or you'll see an
  automatic install banner)

It'll then open full-screen with its own icon, just like a normal app.

## Deploying so the public can reach it

This runs on any host that supports Python/Flask. Easiest free-tier options:

- **[Render](https://render.com)** or **[Railway](https://railway.app)** —
  connect your GitHub repo, they detect Flask automatically.
- **[PythonAnywhere](https://www.pythonanywhere.com)** — good for smaller
  , low-traffic sites, has a free tier.

For any of these:
1. Push this folder to a GitHub repo.
2. Connect the repo on the host.
3. Set the `ADMIN_PASSWORD` and `SECRET_KEY` environment variables in their
   dashboard (don't leave the defaults!).
4. Set the start command to `python app.py` (or `gunicorn app:app` if the
   host asks for one — you'll want to add `gunicorn` to requirements.txt).

Once deployed you'll have a real URL (e.g. `gracechapel.onrender.com`) to
share — put it on your church's existing website, social media, and bulletin.

## How the data is stored

Events live in a small SQLite database file (`church.db`), created
automatically the first time you run the app. No separate database server
needed. Each event has: title, type (service/event), date, time, location,
description, and whether it repeats weekly/monthly.

## Project structure

```
app.py                  Flask app: routes, database, admin auth
templates/               HTML pages (public list, admin dashboard, forms)
static/style.css         All visual styling
static/manifest.json     PWA install config
static/service-worker.js Offline caching for the public page
static/icons/            App icons
```
