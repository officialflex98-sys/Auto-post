"""
Uploads the most recently generated video to YouTube as PRIVATE (for manual
review before publishing). Uses a long-lived refresh token so no interactive
login is needed during automated runs.

Run manually with: python upload_youtube.py
Or triggered automatically via GitHub Actions after generate_video.py succeeds.
"""

import os
import glob
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

CLIENT_ID = os.environ["YOUTUBE_CLIENT_ID"]
CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["YOUTUBE_REFRESH_TOKEN"]

OUTPUT_DIR = "output"
PRIVACY_STATUS = "private"  # you review and publish manually in YouTube Studio

TITLE = "AI Faceless YouTube Automation Training Class | Step-by-Step Blueprint to Build a Profitable Channel"

DESCRIPTION = """Are you ready to learn how to build a successful YouTube channel without showing your face? This AI Faceless YouTube Automation Training Class is designed for beginners and anyone who wants to create a profitable online business using the power of artificial intelligence.

Join the training now 😄😇.
     👇👇👇👇👇👇
https://wa.link/bt8ytu

In this step-by-step blueprint, you'll discover how to choose high-demand niches, find viral video ideas, write engaging AI-generated scripts, create professional voiceovers, design eye-catching thumbnails, edit videos quickly, optimize your content for YouTube SEO, and grow your channel consistently. You'll also learn the best AI tools that can save you time and help you produce high-quality videos with little or no experience.

Whether you're a student, employee, entrepreneur, or someone looking for an extra source of income, this training gives you practical strategies to start and scale a faceless YouTube channel from scratch. No expensive equipment, advanced editing skills, or previous experience is required.

By following this proven blueprint, you'll understand how to upload videos the right way, increase views, grow subscribers, and work toward YouTube monetization. The goal is to help you build a long-term digital asset that can generate income over time through YouTube ads and other monetization methods.

If you're serious about learning AI-powered YouTube automation, this training is for you.

👉 Enroll today and start your journey toward building a successful faceless YouTube channel.

Join the training now 😄😇.
     👇👇👇👇👇👇
https://wa.link/bt8ytu

Keywords: AI YouTube Automation, Faceless YouTube Channel, YouTube Automation Training, AI Video Creation, Make Money Online, YouTube SEO, AI Voice, AI Video Editing, Passive Income, Content Creation, Beginner YouTube Course."""

TAGS = [
    "AI YouTube Automation", "Faceless YouTube Channel", "YouTube Automation Training",
    "AI Video Creation", "Make Money Online", "YouTube SEO", "AI Voice",
    "AI Video Editing", "Passive Income", "Content Creation", "Beginner YouTube Course",
]


def get_youtube_client():
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("youtube", "v3", credentials=creds)


def find_latest_video(output_dir=OUTPUT_DIR):
    files = sorted(glob.glob(f"{output_dir}/final_*.mp4"))
    if not files:
        raise RuntimeError("No generated video found to upload.")
    return files[-1]


def upload_video(path):
    youtube = get_youtube_client()
    body = {
        "snippet": {
            "title": TITLE[:100],  # YouTube title limit
            "description": DESCRIPTION,
            "tags": TAGS,
            "categoryId": "27",  # Education
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[youtube] upload progress: {int(status.progress() * 100)}%")

    print(f"[youtube] uploaded video ID: {response['id']} (privacy: {PRIVACY_STATUS})")
    return response["id"]


if __name__ == "__main__":
    video_path = find_latest_video()
    print(f"[youtube] uploading {video_path}...")
    upload_video(video_path)
