#!/usr/bin/env python3
"""
Instagram Engagement Bot — @hhl.reviews
Replies to comments on recent posts to boost engagement signals.
Strategy: comment-reply threads increase comment count + notify commenter → return visit.
Max 20 replies/day (well within Graph API rate limits).
"""

import json
import os
import sys
import time
import random
import traceback
from datetime import datetime, timezone, timedelta

# ── Config ────────────────────────────────────────────────────────────────────

IG_USER_ID   = os.environ.get("INSTAGRAM_USER_ID", "")
ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
BASE_URL     = "https://graph.instagram.com/v21.0"

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DONE_FILE = os.path.join(BASE_DIR, "ig_engagement_done.json")
LOG_FILE  = os.path.join(BASE_DIR, "ig_engagement_log.txt")

MAX_REPLIES_PER_RUN = 20
LOOKBACK_DAYS       = 7   # only process posts from last N days
DELAY_BETWEEN       = (4, 9)  # seconds between replies (random range)

# ── Reply Templates ───────────────────────────────────────────────────────────
# Buckets matched by keywords in comment text. First match wins.
# {name} is replaced by commenter username.

REPLY_TEMPLATES = {
    "thanks": [
        "Thank you so much @{name}! 🙏 Really appreciate your support!",
        "Thanks @{name}! 💚 Glad this resonated with you!",
        "So kind of you @{name} 🙏 That means a lot!",
    ],
    "love": [
        "Love your energy @{name}! 💚 Stay healthy!",
        "Aww thanks @{name}! 🌿 So glad you love it!",
        "That makes us so happy @{name}! 💪 Keep thriving!",
    ],
    "question": [
        "Great question @{name}! 🙌 Check the link in bio for the full breakdown!",
        "Good one @{name}! 💡 We actually have a full review in our bio link — worth a look!",
        "Hey @{name}! Drop us a DM and we'll point you to the right info 📩",
    ],
    "price": [
        "Hey @{name}! Best deals are always through our bio link 🔗 They run promos regularly!",
        "Great question @{name}! Current pricing + any discounts are on the official page — link in bio 💚",
    ],
    "where": [
        "Hey @{name}! You can find it through the link in our bio 🔗 Ships worldwide!",
        "Hi @{name}! Best place to grab it is the official site — link in bio 💪",
    ],
    "work": [
        "Great question @{name}! Results can vary but the reviews we've seen are really encouraging 💚 Full breakdown in bio!",
        "Hey @{name}! Consistency is key with most supplements 💡 Check our full review at the link in bio!",
    ],
    "wow": [
        "Right?! @{name} 🤩 This stuff is pretty eye-opening!",
        "Exactly @{name}! 💥 More good stuff coming — stay tuned!",
    ],
    "need": [
        "We've got you @{name}! 💚 Check the link in bio for everything you need to know!",
        "Hey @{name}! Start with our bio link — has all the info to help you decide 🌿",
    ],
    "default": [
        "Thank you @{name}! 💚 Happy this reached you — stay healthy!",
        "Appreciate you @{name}! 🙏 Follow for more health tips!",
        "Thanks @{name}! 🌿 So glad you're here!",
        "Hey @{name}! 💪 Thanks for being part of our community!",
        "Love having you here @{name}! 🙌 More content coming soon!",
    ],
}

KEYWORD_BUCKETS = {
    "thanks":   ["thank", "thanks", "merci", "gracias", "thx", "tysm"],
    "love":     ["love", "love it", "❤", "🥰", "💕", "amazing", "awesome", "great", "excellent", "fantastic", "wonderful"],
    "question": ["?", "how", "what", "when", "why", "which", "tell me", "explain"],
    "price":    ["price", "cost", "how much", "expensive", "cheap", "afford", "buy"],
    "where":    ["where", "find it", "get it", "available", "ship", "order"],
    "work":     ["work", "does it", "effective", "result", "benefit", "help"],
    "wow":      ["wow", "omg", "whoa", "incredible", "mind", "blown", "😱", "🤯"],
    "need":     ["need", "want", "interested", "try", "recommend"],
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_done():
    if not os.path.exists(DONE_FILE):
        return {}
    with open(DONE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_done(done):
    with open(DONE_FILE, "w", encoding="utf-8") as f:
        json.dump(done, f, indent=2)


def ig_get(path, params=None):
    import urllib.request, urllib.parse
    p = {"access_token": ACCESS_TOKEN}
    if params:
        p.update(params)
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(p)}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def ig_post(path, data):
    import urllib.request, urllib.parse
    data["access_token"] = ACCESS_TOKEN
    encoded = urllib.parse.urlencode(data).encode()
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, data=encoded, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def pick_reply(comment_text, username):
    text_lower = comment_text.lower()
    for bucket, keywords in KEYWORD_BUCKETS.items():
        if any(kw in text_lower for kw in keywords):
            template = random.choice(REPLY_TEMPLATES[bucket])
            return template.replace("{name}", username)
    return random.choice(REPLY_TEMPLATES["default"]).replace("{name}", username)


def is_own_comment(comment, own_id):
    return comment.get("from", {}).get("id") == own_id


def cutoff_ts():
    return (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).timestamp()

# ── Core logic ────────────────────────────────────────────────────────────────

def get_recent_media():
    cutoff = cutoff_ts()
    media = []
    resp = ig_get(f"/{IG_USER_ID}/media", {
        "fields": "id,timestamp,media_type",
        "limit": 20,
    })
    for item in resp.get("data", []):
        ts = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")).timestamp()
        if ts >= cutoff:
            media.append(item)
    return media


def get_comments(media_id):
    try:
        resp = ig_get(f"/{media_id}/comments", {
            "fields": "id,text,username,timestamp,replies{id,username}",
            "limit": 50,
        })
        return resp.get("data", [])
    except Exception as e:
        log(f"  WARN: could not fetch comments for {media_id}: {e}")
        return []


def already_replied(comment, own_username):
    replies = comment.get("replies", {}).get("data", [])
    return any(r.get("username") == own_username for r in replies)


def post_reply(comment_id, message):
    return ig_post(f"/{comment_id}/replies", {"message": message})


def get_own_username():
    resp = ig_get(f"/{IG_USER_ID}", {"fields": "username"})
    return resp.get("username", "hhl.reviews")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not ACCESS_TOKEN or not IG_USER_ID:
        log("ERREUR: INSTAGRAM_ACCESS_TOKEN ou INSTAGRAM_USER_ID non defini")
        sys.exit(1)

    log("=== Instagram Engagement Bot START ===")

    done = load_done()
    own_username = get_own_username()
    log(f"  Account: @{own_username}")

    media_list = get_recent_media()
    log(f"  Posts recents ({LOOKBACK_DAYS}j): {len(media_list)}")

    replied = 0
    skipped = 0
    errors  = 0

    for media in media_list:
        if replied >= MAX_REPLIES_PER_RUN:
            log(f"  Limite {MAX_REPLIES_PER_RUN} replies/run atteinte")
            break

        media_id = media["id"]
        comments = get_comments(media_id)

        for comment in comments:
            if replied >= MAX_REPLIES_PER_RUN:
                break

            cid = comment.get("id", "")
            if not cid:
                continue

            # Skip already processed
            if done.get(cid):
                skipped += 1
                continue

            username = comment.get("username", "friend")
            text     = comment.get("text", "")

            # Skip our own comments
            if username == own_username:
                done[cid] = {"skipped": "own", "at": datetime.utcnow().isoformat()}
                continue

            # Skip if we already replied in this thread
            if already_replied(comment, own_username):
                done[cid] = {"skipped": "replied", "at": datetime.utcnow().isoformat()}
                continue

            # Skip very short/emoji-only if text is empty
            if not text.strip():
                done[cid] = {"skipped": "empty", "at": datetime.utcnow().isoformat()}
                continue

            reply_text = pick_reply(text, username)

            try:
                resp = post_reply(cid, reply_text)
                reply_id = resp.get("id", "?")
                log(f"  REPLIED comment={cid} reply={reply_id} @{username}: {reply_text[:60]}")
                done[cid] = {
                    "replied_id": reply_id,
                    "reply": reply_text,
                    "to": username,
                    "at": datetime.utcnow().isoformat(),
                }
                replied += 1
                time.sleep(random.uniform(*DELAY_BETWEEN))
            except Exception as e:
                log(f"  ERREUR reply comment={cid}: {e}")
                errors += 1
                done[cid] = {"error": str(e), "at": datetime.utcnow().isoformat()}

    save_done(done)
    log(f"=== Termine: {replied} replies | {skipped} deja fait | {errors} erreurs ===")

    if errors > 0 and replied == 0:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log(f"EXCEPTION:\n{traceback.format_exc()}")
        sys.exit(1)
