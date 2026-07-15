"""
Uploads the most recently generated video to a Facebook Page as UNPUBLISHED
(for manual review before it goes live). Uses a long-lived Page Access Token,
so no interactive login is needed during automated runs.

Setup required (one-time, in Meta for Developers):
  1. Create a Facebook App (or use an existing one) at developers.facebook.com
  2. Get a Page Access Token for the target Page with these permissions:
       - pages_manage_posts
       - pages_read_engagement
       - publish_video
  3. Exchange it for a long-lived Page Access Token (60+ days, and Page tokens
     derived from a long-lived User token don't expire at all) so this
     workflow doesn't break every few hours.
  4. Store the Page ID and the long-lived Page Access Token as GitHub secrets:
       - FACEBOOK_PAGE_ID
       - FACEBOOK_PAGE_ACCESS_TOKEN

Run manually with: python upload_facebook.py
Or triggered automatically via GitHub Actions after generate_video.py succeeds.
"""

import os
import glob
import requests

PAGE_ID = os.environ["FACEBOOK_PAGE_ID"]
PAGE_ACCESS_TOKEN = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]

OUTPUT_DIR = "output"
GRAPH_API_VERSION = "v19.0"
PUBLISHED = False  # keep unpublished so you can review before it goes live

DESCRIPTION = """Are you ready to learn how to build a successful YouTube channel without showing your face? This AI Faceless YouTube Automation Training Class is designed for beginners and anyone who wants to create a profitable online business using the power of artificial intelligence.

Join the training now 😄😇.
     👇👇👇👇👇👇
https://wa.link/bt8ytu

In this step-by-step blueprint, you'll discover how to choose high-demand niches, find viral video ideas, write engaging AI-generated scripts, create professional voiceovers, design eye-catching thumbnails, edit videos quickly, optimize your content for SEO, and grow your audience consistently.

Whether you're a student, employee, entrepreneur, or someone looking for an extra source of income, this training gives you practical strategies to start and scale a faceless content channel from scratch. No expensive equipment, advanced editing skills, or previous experience is required.

If you're serious about learning AI-powered content automation, this training is for you.

👉 Enroll today and start your journey.

Join the training now 😄😇.
     👇👇👇👇👇👇
https://wa.link/bt8ytu"""


def find_latest_video(output_dir=OUTPUT_DIR):
    files = sorted(glob.glob(f"{output_dir}/final_*.mp4"))
    if not files:
        raise RuntimeError("No generated video found to upload.")
    return files[-1]


def upload_video(path):
    url = f"https://graph-video.facebook.com/{GRAPH_API_VERSION}/{PAGE_ID}/videos"

    data = {
        "access_token": PAGE_ACCESS_TOKEN,
        "description": DESCRIPTION,
        "published": "true" if PUBLISHED else "false",
    }

    with open(path, "rb") as f:
        files = {"source": f}
        r = requests.post(url, data=data, files=files, timeout=600)

    if not r.ok:
        # Facebook returns error details as JSON; surface them clearly in logs.
        try:
            err = r.json()
        except ValueError:
            err = r.text
        raise RuntimeError(f"Facebook upload failed ({r.status_code}): {err}")

    result = r.json()
    video_id = result.get("id")
    print(f"[facebook] uploaded video ID: {video_id} (published={PUBLISHED})")
    return video_id


if __name__ == "__main__":
    video_path = find_latest_video()
    print(f"[facebook] uploading {video_path}...")
    upload_video(video_path)
