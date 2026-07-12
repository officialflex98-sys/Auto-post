"""
Content automation pipeline.
Generates: script (Gemini) -> voiceover with word timings (edge-tts) ->
background footage (Pexels, multiple clips joined) -> combined video with
hook caption + synced burst captions + CTA banner -> logs result to Supabase.

Run manually with: python generate_video.py
Or triggered automatically via GitHub Actions on a schedule.
"""

import os
import json
import random
import asyncio
import time
import requests
import edge_tts
from datetime import datetime
from moviepy.editor import (
    VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
)
from moviepy.video.fx.all import crop as vfx_crop

# ---- Config from environment variables (set as GitHub Secrets) ----
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
PEXELS_API_KEY = os.environ["PEXELS_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TARGET_W, TARGET_H = 1080, 1920

HOOK_TEXT = "💸 STOP SCROLLING!\nTHIS SKILL CAN CHANGE\nYOUR INCOME!"
CTA_TEXT = "Join the training now — link below\nor comment YOUTUBE and check the pin comment"
VOICE_INTRO_LINE = "Stop scrolling, this will change your income completely!!!"

WORDS_PER_CAPTION_CHUNK = 2

TOPICS = [
    "how faceless AI-generated YouTube channels are quietly earning creators money without ever showing their face",
    "the exact system behind faceless AI YouTube automation channels that are blowing up right now",
    "why more beginners are choosing faceless AI YouTube automation over filming themselves",
    "how AI tools now let anyone build a full YouTube channel without ever appearing on camera",
    "the faceless AI YouTube automation blueprint helping everyday people build a second income",
]

FOOTAGE_QUERIES = [
    "youtube homepage screen",
    "youtube studio dashboard",
    "adsense earnings dashboard",
    "youtube analytics dashboard",
]

FOOTAGE_FALLBACK_QUERY = "youtube analytics dashboard"


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
    """Ask Gemini to write a short video script promoting the training."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-3.5-flash:generateContent?key={GEMINI_API_KEY}"
    )
    prompt = (
        f"Write a 45-second video script (110-130 words) about {topic}. "
        "Punchy, no fluff, conversational tone, plain text only (no markdown, "
        "no stage directions). This script is promoting a paid training/class "
        "on faceless AI YouTube automation. End the script with exactly this "
        "call to action, word for word: 'Join the training now using the link "
        "below, or comment YOUTUBE and check the pinned comment.'"
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}

    last_error = None
    for attempt in range(3):
        try:
            r = requests.post(url, json=body, timeout=90)
            r.raise_for_status()
            data = r.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return text
        except requests.exceptions.Timeout as e:
            last_error = e
            if attempt < 2:
                wait = 15 * (attempt + 1)
                print(f"[gemini] timeout, retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise
        except requests.exceptions.HTTPError as e:
            last_error = e
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                wait = 15 * (attempt + 1)
                print(f"[gemini] {r.status_code} error, retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise
    raise last_error


async def _tts_with_timings(text, out_path):
    """Generate voiceover audio and capture per-word timing as we go."""
    voice = "en-US-GuyNeural"
    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    words = []
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 10_000_000  # 100ns units -> seconds
                dur = chunk["duration"] / 10_000_000
                words.append({"text": chunk["text"], "start": start, "end": start + dur})
    print(f"[tts] captured {len(words)} word-boundary timings")
    return words


def generate_voiceover(text, out_path):
    """Returns list of {text, start, end} word timings."""
    words = asyncio.run(_tts_with_timings(text, out_path))
    if not words:
        print("[tts] No word-boundary timing data returned; using estimated even timing instead.")
        words = estimate_word_timings(text, out_path)
    return words


def estimate_word_timings(text, audio_path):
    """Fallback: evenly distribute words across the real audio duration.
    Used only if the TTS engine doesn't return precise word-boundary events."""
    probe = AudioFileClip(audio_path)
    duration = probe.duration
    probe.close()
    tokens = text.split()
    if not tokens:
        return []
    per_word = duration / len(tokens)
    words = []
    t = 0.0
    for tok in tokens:
        words.append({"text": tok, "start": t, "end": t + per_word})
        t += per_word
    return words


def build_caption_chunks(words, chunk_size=WORDS_PER_CAPTION_CHUNK):
    """Group word timings into short bursts of a few words each, so captions
    pop in and out in sync with speech instead of one static block of text."""
    chunks = []
    for i in range(0, len(words), chunk_size):
        group = words[i:i + chunk_size]
        if not group:
            continue
        chunks.append({
            "text": " ".join(w["text"] for w in group).upper(),
            "start": group[0]["start"],
            "end": group[-1]["end"],
        })
    return chunks


def fetch_pexels_clip(query, out_path, min_duration=4):
    """Download one relevant vertical stock clip from Pexels."""
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": query, "orientation": "portrait", "per_page": 15}
    r = requests.get(url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    results = [v for v in r.json().get("videos", []) if v.get("duration", 0) >= min_duration]
    if not results:
        raise RuntimeError(f"No Pexels results for query: {query}")

    video = random.choice(results[:8])
    files = sorted(video["video_files"], key=lambda f: f.get("width", 0), reverse=True)
    video_url = files[0]["link"]

    resp = requests.get(video_url, stream=True, timeout=60)
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def fetch_background_clips(out_dir, timestamp):
    """Download 2-3 different YouTube-themed clips (homepage/studio/AdSense/
    analytics) for visual variety instead of looping a single clip."""
    n_clips = random.choice([2, 3])
    queries = random.sample(FOOTAGE_QUERIES, min(n_clips, len(FOOTAGE_QUERIES)))
    paths = []
    for i, q in enumerate(queries):
        p = f"{out_dir}/bgclip_{timestamp}_{i}.mp4"
        try:
            fetch_pexels_clip(q, p)
        except RuntimeError:
            print(f"[pexels] no results for '{q}', falling back to '{FOOTAGE_FALLBACK_QUERY}'")
            fetch_pexels_clip(FOOTAGE_FALLBACK_QUERY, p)
        paths.append(p)
    return paths


def normalize_clip(clip):
    """Resize+crop a clip to fill a consistent vertical frame."""
    clip = clip.without_audio()
    w, h = clip.size
    target_ratio = TARGET_W / TARGET_H
    current_ratio = w / h
    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        clip = vfx_crop(clip, x_center=w / 2, width=new_w)
    else:
        new_h = int(w / target_ratio)
        clip = vfx_crop(clip, y_center=h / 2, height=new_h)
    return clip.resize((TARGET_W, TARGET_H))


def combine_video(background_paths, audio_path, word_timings, out_path):
    """Join multiple background clips + voiceover + hook/burst-captions/CTA."""
    audio = AudioFileClip(audio_path)
    duration = audio.duration

    clips = [normalize_clip(VideoFileClip(p)) for p in background_paths]

    sequence = []
    t_used = 0.0
    i = 0
    while t_used < duration:
        c = clips[i % len(clips)]
        remaining = duration - t_used
        seg = c if c.duration <= remaining else c.subclip(0, remaining)
        sequence.append(seg)
        t_used += seg.duration
        i += 1

    bg = concatenate_videoclips(sequence, method="compose")
    bg = bg.subclip(0, duration).set_audio(audio)

    layers = [bg]

    # Opening hook (first 4 seconds)
    hook_duration = min(4, duration)
    hook = TextClip(
        HOOK_TEXT, fontsize=54, color="yellow", font="DejaVu-Sans-Bold",
        method="caption", size=(bg.w * 0.85, None), align="center",
        stroke_color="black", stroke_width=2
    ).set_position(("center", bg.h * 0.35)).set_start(0).set_duration(hook_duration)
    layers.append(hook)

    # Synced burst captions (4 words at a time, timed to the voiceover,
    # alternating red/yellow, quick pop-in like CapCut-style templates)
    caption_colors = ["red", "yellow", "green"]
    for idx, chunk in enumerate(build_caption_chunks(word_timings)):
        start = chunk["start"]
        dur = max(chunk["end"] - start, 0.3)
        if start >= duration:
            continue
        dur = min(dur, duration - start)
        tc = TextClip(
            chunk["text"], fontsize=52, color=caption_colors[idx % 2], font="DejaVu-Sans-Bold",
            method="caption", size=(bg.w * 0.85, None), align="center",
            stroke_color="black", stroke_width=3
        ).set_position(("center", bg.h * 0.72)).set_start(start).set_duration(dur).fx(
            lambda c: c.fadein(min(0.08, dur / 3))
        )
        layers.append(tc)

    # Persistent CTA footer
    footer = TextClip(
        CTA_TEXT, fontsize=26, color="yellow", font="DejaVu-Sans-Bold",
        method="caption", size=(bg.w * 0.9, None), align="center"
    ).set_position(("center", bg.h * 0.92)).set_duration(duration)
    layers.append(footer)

    final = CompositeVideoClip(layers)
    final.write_videofile(out_path, fps=30, codec="libx264", audio_codec="aac")


def main():
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    topic = random.choice(TOPICS)

    try:
        print(f"[1/4] Generating script for topic: {topic}")
        script = generate_script(topic)
        full_script = f"{VOICE_INTRO_LINE} {script}"
        print(full_script)

        print("[2/4] Generating voiceover...")
        audio_path = f"{OUTPUT_DIR}/voice_{timestamp}.mp3"
        word_timings = generate_voiceover(full_script, audio_path)

        print("[3/4] Fetching background footage clips...")
        bg_paths = fetch_background_clips(OUTPUT_DIR, timestamp)

        print("[4/4] Combining final video...")
        final_path = f"{OUTPUT_DIR}/final_{timestamp}.mp4"
        combine_video(bg_paths, audio_path, word_timings, final_path)

        print(f"Done. Output: {final_path}")
        log_to_supabase("success", {"topic": topic, "script": full_script, "file": final_path})

    except Exception as e:
        print(f"ERROR: {e}")
        log_to_supabase("error", {"topic": topic, "error": str(e)})
        raise


if __name__ == "__main__":
    main()
