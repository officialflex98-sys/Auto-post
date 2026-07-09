"""
Content automation pipeline.
Generates: script (Gemini) -> voiceover (edge-tts) -> background footage (Pexels)
-> combined video with captions -> logs result to Supabase.

Run manually with: python generate_video.py
Or triggered automatically via GitHub Actions on a schedule.
"""

import os
import json
import random
import asyncio
import requests
import edge_tts
from datetime import datetime
from moviepy.editor import (
    VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
)

# ---- Config from environment variables (set as GitHub Secrets) ----
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
PEXELS_API_KEY = os.environ["PEXELS_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
WHATSAPP_LINK = os.environ.get("WHATSAPP_LINK", "https://chat.whatsapp.com/your-invite-link")

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TOPICS = [
    "one practical way people use AI to save time at work",
    "a free AI tool that helps with everyday tasks",
    "how AI can help organize your day",
    "a beginner-friendly way to start learning AI",
    "one AI feature most people don't know exists",
]


def log_to_supabase(status, details):
    """Log what happened to the Supabase 'runs' table."""
    url = f"{SUPABASE_URL}/rest/v1/runs"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    payload = {
        "status": status,
        "details": details,
        "created_at": datetime.utcnow().isoformat(),
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        print(f"[supabase] logged status={status} response={r.status_code}")
    except Exception as e:
        print(f"[supabase] logging failed: {e}")


def generate_script(topic):
    """Ask Gemini to write a short video script."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}")
    prompt = (
        f"Write a 45-second video script (110-130 words) about {topic}. "
        "Punchy, no fluff, conversational tone, plain text only (no markdown, "
        "no stage directions). End with a short hook line encouraging people "
        "to follow for more free tips."
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    r = requests.post(url, json=body, timeout=30)
    r.raise_for_status()
    data = r.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    return text


async def _tts(text, out_path):
    voice = "en-US-GuyNeural"  # natural-sounding free voice
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_path)


def generate_voiceover(text, out_path):
    asyncio.run(_tts(text, out_path))


def fetch_background_video(query, out_path):
    """Download a relevant vertical stock video from Pexels."""
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": query, "orientation": "portrait", "per_page": 5}
    r = requests.get(url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    results = r.json().get("videos", [])
    if not results:
        raise RuntimeError(f"No Pexels results for query: {query}")

    video = random.choice(results)
    # pick the best portrait file available
    files = sorted(video["video_files"], key=lambda f: f.get("width", 0), reverse=True)
    video_url = files[0]["link"]

    resp = requests.get(video_url, stream=True, timeout=60)
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def combine_video(background_path, audio_path, caption_text, out_path):
    """Overlay voiceover + captions + WhatsApp link onto background footage."""
    audio = AudioFileClip(audio_path)
    duration = audio.duration

    bg = VideoFileClip(background_path).without_audio()
    # loop or trim background to match audio length
    if bg.duration < duration:
        n_loops = int(duration // bg.duration) + 1
        bg = bg.loop(n=n_loops)
    bg = bg.subclip(0, duration)
    bg = bg.set_audio(audio)

    # Simple caption (full script, small font, bottom-center)
    caption = TextClip(
        caption_text, fontsize=40, color="white", font="DejaVu-Sans-Bold",
        method="caption", size=(bg.w * 0.9, None), align="center"
    ).set_position(("center", bg.h * 0.65)).set_duration(duration)

    footer = TextClip(
        f"Join our free WhatsApp community: {WHATSAPP_LINK}",
        fontsize=28, color="yellow", font="DejaVu-Sans-Bold",
        method="caption", size=(bg.w * 0.9, None), align="center"
    ).set_position(("center", bg.h * 0.9)).set_duration(duration)

    final = CompositeVideoClip([bg, caption, footer])
    final.write_videofile(out_path, fps=30, codec="libx264", audio_codec="aac")


def main():
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    topic = random.choice(TOPICS)

    try:
        print(f"[1/4] Generating script for topic: {topic}")
        script = generate_script(topic)
        print(script)

        print("[2/4] Generating voiceover...")
        audio_path = f"{OUTPUT_DIR}/voice_{timestamp}.mp3"
        generate_voiceover(script, audio_path)

        print("[3/4] Fetching background footage...")
        bg_path = f"{OUTPUT_DIR}/bg_{timestamp}.mp4"
        fetch_background_video(topic.split()[0], bg_path)

        print("[4/4] Combining final video...")
        final_path = f"{OUTPUT_DIR}/final_{timestamp}.mp4"
        combine_video(bg_path, audio_path, script, final_path)

        print(f"Done. Output: {final_path}")
        log_to_supabase("success", {"topic": topic, "script": script, "file": final_path})

    except Exception as e:
        print(f"ERROR: {e}")
        log_to_supabase("error", {"topic": topic, "error": str(e)})
        raise


if __name__ == "__main__":
    main()
