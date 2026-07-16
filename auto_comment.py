
"""
Posts one comment per day on EVERY public video on the channel (old and new),
intended to run once daily via GitHub Actions.

Quota note: each comment costs 50 units, and the daily quota is 10,000 units,
so this comfortably supports up to ~200 public videos per day. If the channel
grows past that, some videos will get skipped once quota runs out for the day
(the script just stops and reports how many it got through).

Run manually with: python auto_comment.py
Or triggered automatically via GitHub Actions on a schedule.
"""

import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

CLIENT_ID = os.environ["YOUTUBE_CLIENT_ID"]
CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["YOUTUBE_REFRESH_TOKEN"]

# Single daily comment, posted identically on every public video.
COMMENT_TEXT = (
    "Ready to build a faceless YouTube channel with AI? "
    "Join our free training group: https://wa.link/bt8ytu"
)


def get_youtube_client():
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("youtube", "v3", credentials=creds)


def get_uploads_playlist_id(youtube):
    """Every channel has an auto-generated 'uploads' playlist containing all its videos."""
    resp = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError("Could not find channel for the authenticated account.")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def list_all_video_ids(youtube, playlist_id):
    """Get every video ID from the uploads playlist (paginates through all of them)."""
    video_ids = []
    page_token = None
    while True:
        resp = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        video_ids.extend(item["contentDetails"]["videoId"] for item in resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return video_ids


def filter_public_video_ids(youtube, video_ids):
    """videos.list only accepts up to 50 IDs per call, so batch it."""
    public_ids = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        resp = youtube.videos().list(part="status", id=",".join(batch)).execute()
        for item in resp.get("items", []):
            if item["status"]["privacyStatus"] == "public":
                public_ids.append(item["id"])
    return public_ids


def post_comment(youtube, video_id, comment_text):
    """Returns 'ok', 'quota_exceeded', or 'failed'."""
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
        print(f"[auto-comment] posted on video {video_id}: comment ID {comment_id}")
        return "ok"
    except HttpError as e:
        if e.resp.status == 403 and "quotaExceeded" in str(e):
            print(f"[auto-comment] daily quota exceeded, stopping for today.")
            return "quota_exceeded"
        print(f"[auto-comment] failed on video {video_id}: {e}")
        return "failed"
    except Exception as e:
        print(f"[auto-comment] failed on video {video_id}: {e}")
        return "failed"


def main():
    youtube = get_youtube_client()

    playlist_id = get_uploads_playlist_id(youtube)
    all_ids = list_all_video_ids(youtube, playlist_id)
    public_ids = filter_public_video_ids(youtube, all_ids)

    print(f"[auto-comment] found {len(public_ids)} public videos (old and new). "
          f"Posting one comment on each.")

    success_count = 0
    for video_id in public_ids:
        result = post_comment(youtube, video_id, COMMENT_TEXT)
        if result == "ok":
            success_count += 1
        elif result == "quota_exceeded":
            break

    print(f"[auto-comment] done. {success_count}/{len(public_ids)} comments posted successfully.")


if __name__ == "__main__":
    main()
