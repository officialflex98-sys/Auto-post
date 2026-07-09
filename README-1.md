# Content Bot Setup

## What this does
Every run: writes a short video script (Gemini) → converts it to voice (edge-tts, free)
→ downloads matching background footage (Pexels) → combines them into one video with
captions and your WhatsApp link → logs the result to Supabase.

Runs automatically every 6 hours once deployed via GitHub Actions.

## Setup steps (do these in order)

### 1. Create the Supabase table
- Go to your Supabase project → **SQL Editor** → **New query**
- Paste the contents of `supabase_setup.sql` → click **Run**

### 2. Create a new GitHub repository
- Go to github.com → **New repository** → name it e.g. `content-bot` → **Create**

### 3. Upload these files to the repo
Using GitHub's web interface (no command line needed):
- Click **Add file → Upload files**
- Drag in: `generate_video.py`, `requirements.txt`, `supabase_setup.sql`, `README.md`
- For the workflow file, you need the exact folder structure `.github/workflows/automate.yml` —
  click **Add file → Create new file**, type that full path as the filename, paste the
  workflow contents in, then commit.

### 4. Add your secrets
Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**.
Add each of these one at a time:

| Secret name | Value |
|---|---|
| `GEMINI_API_KEY` | your Gemini key |
| `PEXELS_API_KEY` | your Pexels key |
| `SUPABASE_URL` | `https://udypqyacecpknprzjcts.supabase.co` |
| `SUPABASE_KEY` | your Supabase publishable key |
| `WHATSAPP_LINK` | your WhatsApp community invite link |

### 5. Test it manually
- Go to your repo → **Actions** tab → click **Generate Video** workflow → **Run workflow**
- Wait a few minutes, then click into the run to see logs
- If it succeeds, scroll down to **Artifacts** and download the generated video to check it

### 6. Let it run automatically
Once a manual test succeeds, do nothing else — the `cron` schedule in the workflow file
already runs it every 6 hours automatically.

## Notes
- This produces the **video file only**. Auto-uploading to YouTube/Instagram/Facebook is a
  separate, more involved step (each platform requires its own developer app approval) —
  we'll set that up once video generation is confirmed working.
- Check the **Actions** tab occasionally for failed runs (red X) — most common cause is an
  expired or incorrect API key.
