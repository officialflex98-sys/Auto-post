"""
Uploads the most recently generated video to YouTube as PRIVATE (for manual
review before publishing). Uses a long-lived refresh token so no interactive
login is needed during automated runs.

After a successful upload, also posts an auto-comment on the video with the
CTA link. NOTE: pinning a comment is NOT supported by the YouTube Data API —
there is no endpoint for it. Pinning must still be done manually in YouTube
Studio (Comments tab -> ... -> Pin) after each upload if you want that.

Run manually with: python upload_youtube.py
Or triggered automatically via GitHub Actions after generate_video.py succeeds.
"""

import os
import glob
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Channel 1 (required)
CLIENT_ID = os.environ["YOUTUBE_CLIENT_ID"]
CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["YOUTUBE_REFRESH_TOKEN"]

# Channel 2 (optional — same Client ID/Secret, different Google account +
# refresh token). If YOUTUBE_REFRESH_TOKEN_2 isn't set, this channel is
# simply skipped, so this stays backward-compatible with single-channel setups.
REFRESH_TOKEN_2 = os.environ.get("YOUTUBE_REFRESH_TOKEN_2")

# Each entry is (label, client_id, client_secret, refresh_token).
CHANNELS = [("channel 1", CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)]
if REFRESH_TOKEN_2:
    CHANNELS.append(("channel 2", CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN_2))

# --- Scheduling ---
# Set SCHEDULE_HOURS_FROM_NOW to a number to have the video uploaded as
# private and automatically go public at that many hours from now (YouTube
# handles the actual flip to public itself — no extra call needed).
# Set it to None to publish immediately as PRIVACY_STATUS (the old behavior).
SCHEDULE_HOURS_FROM_NOW = 24  # e.g. 6 to schedule 6 hours out

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

# Auto-posted as a top-level comment on every upload.
COMMENT_TEXT = """Join the training now 😄😇 — link below 👇
https://wa.link/bt8ytu

(Comment YOUTUBE if the link doesn't work for you and I'll send it directly!)"""


def get_youtube_client(client_id, client_secret, refresh_token):
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("youtube", "v3", credentials=creds)


def find_latest_video(output_dir=OUTPUT_DIR):
    files = sorted(glob.glob(f"{output_dir}/final_*.mp4"))
    if not files:
        raise RuntimeError("No generated video found to upload.")
    return files[-1]


def upload_video(youtube, path):
    status = {
        "privacyStatus": PRIVACY_STATUS,
        "selfDeclaredMadeForKids": False,
    }

    if SCHEDULE_HOURS_FROM_NOW is not None:
        # YouTube requires privacyStatus=private when publishAt is set; it
        # automatically flips the video to public at that timestamp.
        publish_at = datetime.now(timezone.utc) + timedelta(hours=SCHEDULE_HOURS_FROM_NOW)
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"[youtube] scheduling video to go public at {status['publishAt']} (UTC)")

    body = {
        "snippet": {
            "title": TITLE[:100],  # YouTube title limit
            "description": DESCRIPTION,
            "tags": TAGS,
            "categoryId": "27",  # Education
        },
        "status": status,
    }
    media = MediaFileUpload(path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[youtube] upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"[youtube] uploaded video ID: {video_id} (privacy: {PRIVACY_STATUS})")
    return video_id


def post_comment(youtube, video_id, comment_text=COMMENT_TEXT):
    """Post a top-level comment on the given video.

    Note: the YouTube Data API has no endpoint to pin a comment. If you want
    the comment pinned, you still need to do that manually in YouTube Studio
    after this runs.
    """
    body = {
        "snippet": {
            "videoId": video_id,
            "topLevelComment": {
                "snippet": {
                    "textOriginal": comment_text,
                }
            },
        }
    }
    try:
        response = youtube.commentThreads().insert(part="snippet", body=body).execute()
        comment_id = response["snippet"]["topLevelComment"]["id"]
        print(f"[youtube] posted comment ID: {comment_id}")
        return comment_id
    except Exception as e:
        # Don't fail the whole run just because the comment couldn't post
        # (e.g. comments disabled while video is still private on some channels).
        print(f"[youtube] failed to post comment: {e}")
        return None


if __name__ == "__main__":
    video_path = find_latest_video()
    print(f"[youtube] found video to upload: {video_path}")

    for label, client_id, client_secret, refresh_token in CHANNELS:
        print(f"[youtube] --- uploading to {label} ---")
        try:
            youtube_client = get_youtube_client(client_id, client_secret, refresh_token)
            uploaded_video_id = upload_video(youtube_client, video_path)
            post_comment(youtube_client, uploaded_video_id)
        except Exception as e:
            # Don't let one channel's failure stop the other channel's upload.
            print(f"[youtube] upload to {label} failed: {e}")
