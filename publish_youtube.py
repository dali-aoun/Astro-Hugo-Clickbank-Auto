"""
publish_youtube.py — YouTube Shorts uploader pour reviews
Utilise l'API YouTube Data v3 via OAuth2
Credentials via env vars: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
"""

import os, sys, json, time, traceback
from datetime import date, datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DONE_FILE = os.path.join(BASE_DIR, "yt_published_done.json")
LOG_FILE = os.path.join(BASE_DIR, "yt_publish_log.txt")
PRODUCTS_FILE = os.path.join(BASE_DIR, "products.json")
POST_INDEX_FILE = os.path.join(BASE_DIR, "yt_post_index.json")

YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID", "")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", "")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN", "")

TITLE_TEMPLATES = [
    "{name} Review 2026 — Worth It? #shorts",
    "Is {name} a Scam? Honest Review #shorts",
    "{name}: What They Don't Tell You #shorts",
    "I Analyzed {name} — Here's the Truth #shorts",
    "{name} Review — {rating}/5 Rating #shorts",
]

DESCRIPTION_TEMPLATE = """{name} Review 2026 — Does It Really Work?

{desc}

Our rating: {rating}/5

Full review: https://reviews.thehappy-healthy-life.com/{cat_slug}/{slug}/

#shorts #{cat_tag} #supplementreview #healthsupplement #honestreviews
"""

CATEGORY_TAGS = {
    "dental-health": "dentalhealth",
    "prostate-health": "prostatehealth",
    "male-performance": "menshealth",
    "brain-and-senses": "brainhealth",
    "weight-loss": "weightloss",
    "beauty-skin": "skincare",
    "womens-health": "womenshealth",
    "blood-sugar": "bloodsugar",
    "joint-pain": "jointpain",
    "sleep": "sleepbetter",
    "heart-health": "hearthealth",
    "general-health": "wellness",
}


def log(msg):
    print(msg, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC] {msg}\n")
    except Exception:
        pass


def load_done():
    if not os.path.exists(DONE_FILE):
        return {}
    try:
        with open(DONE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_done(done):
    with open(DONE_FILE, "w", encoding="utf-8") as f:
        json.dump(done, f, indent=2)


def load_post_index():
    try:
        with open(POST_INDEX_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"idx": 0}


def save_post_index(state):
    with open(POST_INDEX_FILE, "w") as f:
        json.dump(state, f)


def load_products():
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    products = []
    for cat in data["categories"]:
        for p in cat["products"]:
            if p.get("status") == "ok":
                products.append({**p, "category_slug": cat["slug"]})
    return products


def get_access_token():
    import requests
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": YT_CLIENT_ID,
        "client_secret": YT_CLIENT_SECRET,
        "refresh_token": YT_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }, timeout=30)
    if r.status_code == 200:
        return r.json().get("access_token")
    log(f"OAuth refresh erreur {r.status_code}: {r.text[:200]}")
    return None


def upload_short(video_path, title, description, tags, access_token):
    import requests

    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags,
            "categoryId": "26",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    r = requests.post(init_url, json=metadata, headers=headers, timeout=30)

    if r.status_code != 200:
        return r.status_code, {"error": r.text[:200]}

    upload_url = r.headers.get("Location")
    if not upload_url:
        return 0, {"error": "no upload URL"}

    with open(video_path, "rb") as f:
        video_data = f.read()

    r2 = requests.put(
        upload_url,
        data=video_data,
        headers={"Content-Type": "video/mp4", "Content-Length": str(len(video_data))},
        timeout=300,
    )
    return r2.status_code, r2.json() if r2.status_code == 200 else {"error": r2.text[:200]}


def main():
    if not YT_CLIENT_ID or not YT_CLIENT_SECRET or not YT_REFRESH_TOKEN:
        log("ERREUR: YT_CLIENT_ID, YT_CLIENT_SECRET ou YT_REFRESH_TOKEN non defini")
        sys.exit(1)

    import random

    tz_tunis = timezone(timedelta(hours=1))
    now_tunis = datetime.now(timezone.utc).astimezone(tz_tunis)
    today_key = now_tunis.strftime("%Y-%m-%d")

    done = load_done()
    if done.get(today_key):
        log(f"YouTube deja publie pour {today_key}")
        sys.exit(0)

    products = load_products()
    if not products:
        log("Aucun produit OK")
        sys.exit(0)

    post_state = load_post_index()
    idx = post_state["idx"] % len(products)
    product = products[idx]

    shorts_dir = os.path.join(BASE_DIR, "yt_shorts")
    if not os.path.isdir(shorts_dir):
        log("Dossier yt_shorts/ introuvable — skip YouTube")
        sys.exit(0)

    video_file = os.path.join(shorts_dir, f"{product['slug']}.mp4")
    if not os.path.exists(video_file):
        available = [f for f in os.listdir(shorts_dir) if f.endswith(".mp4")]
        if not available:
            log("Aucun fichier .mp4 dans yt_shorts/")
            sys.exit(0)
        video_file = os.path.join(shorts_dir, available[idx % len(available)])

    log(f"=== YouTube Shorts Publisher {today_key} ===")

    access_token = get_access_token()
    if not access_token:
        log("Impossible d'obtenir un access token YouTube")
        sys.exit(1)

    rating = min(4.9, max(3.8, 3.5 + (product.get("gravity", 0) / 50)))
    cat_tag = CATEGORY_TAGS.get(product["category_slug"], "health")

    title = random.choice(TITLE_TEMPLATES).format(
        name=product["name"],
        rating=f"{rating:.1f}",
    )
    description = DESCRIPTION_TEMPLATE.format(
        name=product["name"],
        desc=product["description"][:300],
        rating=f"{rating:.1f}",
        cat_slug=product["category_slug"],
        slug=product["slug"],
        cat_tag=cat_tag,
    )
    tags = [product["name"], "supplement review", "honest review", "health supplement", "2026", cat_tag]

    status, resp = upload_short(video_file, title, description, tags, access_token)
    if status == 200:
        video_id = resp.get("id", "")
        log(f"  OK: {product['name']} — https://youtube.com/shorts/{video_id}")
    else:
        log(f"  ERREUR {status}: {resp}")

    post_state["idx"] = idx + 1
    save_post_index(post_state)

    done[today_key] = {
        "product": product["name"],
        "status": "ok" if status == 200 else "error",
        "at": datetime.utcnow().isoformat()
    }
    save_done(done)
    log(f"=== Termine ===")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log(f"EXCEPTION:\n{traceback.format_exc()}")
        sys.exit(1)
