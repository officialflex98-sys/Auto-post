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
import time
import requests
import edge_tts
from datetime import datetime
from moviepy.editor import (
    VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
)

# ---- Config from environment variables (set as GitHub Secrets) ----
def generate_script(topic):
    """Ask Gemini to write a short video script."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-3.5-flash:generateContent?key={GEMINI_API_KEY}"
    )
    prompt = (
        f"Write a 45-second video script (110-130 words) about {topic}. "
        "Punchy, no fluff, conversational tone, plain text only (no markdown, "
        "no stage directions). End with a short hook line encouraging people "
        "to follow for more free tips."
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}

    last_error = None
    for attempt in range(3):
        try:
            r = requests.post(url, json=body, timeout=30)
            r.raise_for_status()
            data = r.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return text
        except requests.exceptions.HTTPError as e:
            last_error = e
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                wait = 15 * (attempt + 1)
                print(f"[gemini] {r.status_code} error, retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise
    raise last_error
