# Clearspring App — setup

## Running it on your PC

**First time only:**

1. Double-click **`setup.bat`**

   It installs what's needed, generates your admin password and notification
   keys, and saves them to `settings.bat`.

   **Write the password down** — it's shown on screen and saved in that file,
   but nowhere else.

**Every time after that:**

2. Double-click **`run.bat`**

   The app starts and opens in your browser automatically. Leave the black
   window open while you use it; closing it stops the app.

That's it. No typing commands.

---

## Where things live

| File | What it is | Safe to replace? |
|---|---|---|
| `run.bat` | The launcher | Yes — no secrets in it |
| `setup.bat` | First-time setup | Yes |
| `settings.bat` | **Your passwords and keys** | **No — keep this** |
| `../church-data/` | **Your events, sermons, prayers** | **No — keep this** |

When a new version of the app arrives, you can safely replace everything
*except* `settings.bat` and the `church-data` folder.

---

## Adding the Bible study assistant

The AI study helper needs a free key from Google.

1. Go to [aistudio.google.com](https://aistudio.google.com) and create an API key
2. Open `settings.bat` in Notepad
3. Find the last line and remove the `REM ` from the start, then paste your key:

   ```
   set GEMINI_API_KEY=your-key-here
   ```

4. Save, and restart with `run.bat`

---

## Putting it on the web

Until the app is online, only your own PC can see it. Getting it online means
your pastor and church can use it on their phones, and it makes notifications
work (they need HTTPS, which is why they don't work locally).

This is a one-off job at a computer. Afterwards you can manage everything from
your phone.

### Step 1 — Put the code on GitHub

You do **not** need to type any commands. Two options — pick either.

---

#### Option A: Drag and drop (nothing to install)

**1. Make a safe copy of the files**

Double-click **`prepare-upload.bat`**.

It creates a folder called `clearspring-upload` on your Desktop and opens it.
This copy has your password, keys and church data removed, so nothing private
can be uploaded by mistake.

**2. Create the repository**

- Go to [github.com/new](https://github.com/new)
- **Repository name:** `clearspring-app`
- Choose **Private**
- Tick **Add a README file**
- Click **Create repository**

**3. Upload the files**

- On the repository page, click **Add file** → **Upload files**
- Open your `clearspring-upload` folder
- Select everything inside it (click one file, then press **Ctrl+A**)
- Drag it all onto the GitHub page
- Wait for the files to finish uploading
- Scroll down and click **Commit changes**

Done. Your code is on GitHub.

---

#### Option B: GitHub Desktop (better if you'll update it often)

This is worth doing if you expect to send updates regularly, because
afterwards each update is a single click.

**1.** Download **GitHub Desktop** from [desktop.github.com](https://desktop.github.com)
and sign in with your GitHub account.

**2.** Click **File → Add local repository**, then **Choose...** and select your
`church_app` folder. If it says it isn't a Git repository, click
**create a repository** on that same screen.

**3.** Give it the name `clearspring-app` and click **Create repository**.

**4.** Click **Publish repository** at the top. **Make sure "Keep this code
private" is ticked.** Click **Publish repository**.

GitHub Desktop reads the `.gitignore` file automatically, so your `settings.bat`
and church data are excluded for you.

**To send an update later:** open GitHub Desktop, type a short note in the
Summary box, click **Commit to main**, then **Push origin**. That's it.

### Step 2 — Deploy on Render

1. Go to [render.com](https://render.com) and sign up using your GitHub account
2. Click **New → Blueprint**
3. Choose your repository

   Render reads the `render.yaml` file included here and sets everything up
   itself — the web server, the persistent disk for your data, HTTPS.

4. It will ask you for **ADMIN_PASSWORD**. Use the one from `settings.bat`.
5. Click **Apply** and wait about three minutes.

You'll get an address like `clearspring-app.onrender.com`.

### Step 3 — Add your notification keys

In Render, open your service → **Environment** → add these three, copying the
values from your `settings.bat`:

- `VAPID_PUBLIC_KEY`
- `VAPID_PRIVATE_KEY`
- `VAPID_SUBJECT`

And `GEMINI_API_KEY` if you're using the study assistant.

### Step 4 — Put it on phones

Share the address. Then:

- **iPhone:** open in Safari → Share button → **Add to Home Screen**
- **Android:** open in Chrome → menu (⋮) → **Install app**

It gets its own icon and opens full screen, with no browser bars.

---

## Things worth knowing

**The free Render plan sleeps.** After about 15 minutes of nobody using it, the
first visit takes ~30 seconds to wake up. Open it yourself before showing
anyone. Their paid plan (around £5/month) removes this.

**Moving your existing data across.** Your local data doesn't automatically
appear on the website. To move it: in your local app go to **Admin → Data →
Download backup**, then on the deployed site go to **Admin → Data → Restore**
and upload that file.

**Back up before anything big.** Admin → Data → Download backup. Keep a copy
somewhere other than the computer running the app.
