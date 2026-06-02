import json
import os
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(BASE_DIR, "illustrations")
SCHEDULE_FILE = os.path.join(BASE_DIR, "deviantart_schedule.json")
TOKENS_FILE = os.path.join(BASE_DIR, "deviantart_tokens.json")

API_BASE = "https://www.deviantart.com/api/v1/oauth2"
TOKEN_URL = "https://www.deviantart.com/oauth2/token"
USER_AGENT = "elite-gomi-portfolio-scheduler/0.1"


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def normalize_da_tags(tags):
    result = []
    for tag in tags or []:
        clean = "".join(ch for ch in str(tag).replace(" ", "_") if ch.isalnum() or ch == "_")
        if clean and clean.lower() != "other":
            result.append(clean[:50])
    return result[:30]


def get_access_token():
    tokens = load_json(TOKENS_FILE, {})
    expires_at = float(tokens.get("expires_at", 0) or 0)
    if tokens.get("access_token") and expires_at > time.time() + 120:
        return tokens["access_token"]

    refresh_token = tokens.get("refresh_token") or os.getenv("DEVIANTART_REFRESH_TOKEN")
    client_id = os.getenv("DEVIANTART_CLIENT_ID")
    client_secret = os.getenv("DEVIANTART_CLIENT_SECRET")
    if not refresh_token or not client_id:
        raise RuntimeError("DeviantArt OAuth token is not configured.")

    payload = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }
    if client_secret:
        payload["client_secret"] = client_secret

    res = requests.post(TOKEN_URL, data=payload, headers={"User-Agent": USER_AGENT}, timeout=30)
    res.raise_for_status()
    data = res.json()
    if "access_token" not in data:
        raise RuntimeError(f"Token refresh failed: {data}")

    tokens.update(data)
    tokens["expires_at"] = time.time() + int(data.get("expires_in", 3600))
    save_json(TOKENS_FILE, tokens)
    return tokens["access_token"]


def submit_to_stash(access_token, job):
    image_path = os.path.join(IMAGE_DIR, job["filename"])
    if not os.path.exists(image_path):
        raise FileNotFoundError(image_path)

    data = {
        "access_token": access_token,
        "title": job["title"][:50],
        "artist_comments": job.get("description", ""),
        "is_dirty": "false",
        "is_ai_generated": "true",
        "noai": "true",
    }
    for tag in normalize_da_tags(job.get("tags", [])):
        data.setdefault("tags[]", [])
        data["tags[]"].append(tag)

    with open(image_path, "rb") as f:
        files = {"file": (os.path.basename(image_path), f)}
        res = requests.post(
            f"{API_BASE}/stash/submit",
            data=data,
            files=files,
            headers={"User-Agent": USER_AGENT},
            timeout=120,
        )
    res.raise_for_status()
    result = res.json()
    if result.get("status") != "success":
        raise RuntimeError(f"Sta.sh submit failed: {result}")
    return result["itemid"], result


def publish_stash_item(access_token, itemid, job):
    data = {
        "access_token": access_token,
        "itemid": itemid,
        "is_mature": "true" if job.get("is_mature") else "false",
        "feature": "true",
        "allow_comments": "true",
        "display_resolution": "5",
        "allow_free_download": "false",
        "is_ai_generated": "true",
        "noai": "true",
    }
    gallery_id = job.get("galleryid")
    if gallery_id:
        data["galleryids[]"] = gallery_id

    res = requests.post(
        f"{API_BASE}/stash/publish",
        data=data,
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    res.raise_for_status()
    result = res.json()
    if result.get("status") != "success":
        raise RuntimeError(f"Sta.sh publish failed: {result}")
    return result


def run_job(job):
    access_token = get_access_token()
    itemid, stash_result = submit_to_stash(access_token, job)
    publish_result = publish_stash_item(access_token, itemid, job)
    return {"stash": stash_result, "publish": publish_result}


def is_due(job, now=None):
    if job.get("status") != "queued":
        return False
    scheduled_at = job.get("scheduled_at")
    if not scheduled_at:
        return False
    now = now or datetime.now(timezone.utc)
    due_at = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
    return due_at <= now


def process_due_posts(dry_run=True):
    queue = load_json(SCHEDULE_FILE, [])
    processed = []
    for job in queue:
        if not is_due(job):
            continue
        job["last_checked_at"] = datetime.now(timezone.utc).isoformat()
        if dry_run:
            job["status"] = "ready"
            job["message"] = "Dry run: ready to publish."
        else:
            try:
                result = run_job(job)
                job["status"] = "published"
                job["published_at"] = datetime.now(timezone.utc).isoformat()
                job["result"] = result
            except Exception as exc:
                job["status"] = "error"
                job["message"] = str(exc)
        processed.append(job)
    save_json(SCHEDULE_FILE, queue)
    return processed


if __name__ == "__main__":
    dry_run = os.getenv("DEVIANTART_DRY_RUN", "true").lower() != "false"
    for item in process_due_posts(dry_run=dry_run):
        print(f"{item.get('id')}: {item.get('status')} {item.get('message', '')}")
