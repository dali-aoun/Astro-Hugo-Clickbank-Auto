"""
publish_youtube.py - YouTube Shorts generator + uploader
Pipeline: script -> edge-tts (free TTS) -> Pillow background -> FFmpeg assembly -> YouTube upload
Zero cost: edge-tts uses Microsoft Edge TTS API, FFmpeg is pre-installed on GitHub Actions
"""

import os, sys, json, time, traceback, subprocess, asyncio, tempfile
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DONE_FILE       = os.path.join(BASE_DIR, "yt_published_done.json")
PRODUCTS_FILE   = os.path.join(BASE_DIR, "products.json")
POST_INDEX_FILE = os.path.join(BASE_DIR, "yt_post_index.json")

YT_CLIENT_ID     = os.environ.get("YT_CLIENT_ID", "")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", "")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN", "")

SITE_URL = "https://reviews.thehappy-healthy-life.com"

TITLE_TEMPLATES = [
    "{name} Review 2026 — Worth It? #shorts",
    "Is {name} a Scam? Honest Review #shorts",
    "{name}: What They Don't Tell You #shorts",
    "I Analyzed {name} — Here's the Truth #shorts",
    "{name} Review — {rating}/5 Stars #shorts",
]

DESCRIPTION_TEMPLATE = """{name} Review 2026 — Does It Really Work?

{desc}

Our rating: {rating}/5

Full review: {site_url}/{cat_slug}/{slug}/

#{cat_tag} #supplementreview #healthsupplement #honestreviews #shorts
"""

CATEGORY_TAGS = {
    "dental-health":    "dentalhealth",
    "prostate-health":  "prostatehealth",
    "male-performance": "menshealth",
    "brain-and-senses": "brainhealth",
    "weight-loss":      "weightloss",
    "beauty-skin":      "skincare",
    "womens-health":    "womenshealth",
    "blood-sugar":      "bloodsugar",
    "joint-pain":       "jointpain",
    "sleep":            "sleepbetter",
    "heart-health":     "hearthealth",
    "general-health":   "wellness",
}

CATEGORY_COLORS = {
    "dental-health":    ((16, 185, 129),  (4, 120, 87)),
    "prostate-health":  ((59, 130, 246),  (29, 78, 216)),
    "male-performance": ((239, 68, 68),   (185, 28, 28)),
    "brain-and-senses": ((139, 92, 246),  (91, 33, 182)),
    "weight-loss":      ((245, 158, 11),  (180, 83, 9)),
    "beauty-skin":      ((236, 72, 153),  (190, 24, 93)),
    "womens-health":    ((168, 85, 247),  (126, 34, 206)),
    "blood-sugar":      ((6, 182, 212),   (14, 116, 144)),
    "joint-pain":       ((20, 184, 166),  (13, 148, 136)),
    "sleep":            ((99, 102, 241),  (67, 56, 202)),
    "heart-health":     ((244, 63, 94),   (190, 18, 60)),
    "general-health":   ((34, 197, 94),   (21, 128, 61)),
}


# ── Logging ──────────────────────────────────────────────────────────────────

def log(msg):
    print(msg, flush=True)


# ── State ─────────────────────────────────────────────────────────────────────

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


# ── Products ──────────────────────────────────────────────────────────────────

def load_products():
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    products = []
    for cat in data["categories"]:
        for p in cat["products"]:
            if p.get("status") == "ok":
                products.append({**p, "category_slug": cat["slug"]})
    return products


# ── Script generation ─────────────────────────────────────────────────────────

def make_voiceover_script(product):
    name     = product["name"]
    desc     = product.get("description", "a popular health supplement")
    audience = product.get("audience", "health-conscious adults")
    gravity  = product.get("gravity", 0)
    rating   = min(4.9, max(3.8, 3.5 + gravity / 50))
    cat_slug = product.get("category_slug", "general-health")
    cat_name = cat_slug.replace("-", " ")

    script = f"""
{name}. My honest review.

{name} is {desc}

It's specifically designed for {audience}

So, does it actually deliver results?

With a market popularity score of {int(gravity)}, {name} is currently
one of the most-purchased supplements in the {cat_name} space.
That kind of traction doesn't happen without real results behind it.

Here is the breakdown.

{name} works by addressing the root cause, not just the symptoms.
Customers consistently report noticeable improvements within the first few weeks.
It uses natural, research-backed ingredients with no harsh side effects.

My honest rating? {rating:.1f} stars out of five.

If you're serious about your health and tired of products that overpromise and underdeliver,
{name} is absolutely worth considering.

For the full review — ingredients, dosage, pros and cons, and where to get it at the best price —
check the link in the description below.

Follow for more honest supplement reviews. See you in the next one.
""".strip()
    return script


# ── Background image ──────────────────────────────────────────────────────────

def wrap_text(text, max_chars):
    words = text.split()
    lines, current = [], ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = (current + " " + word).strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def make_background_image(product, width=1080, height=1920):
    cat_slug = product.get("category_slug", "general-health")
    color_top, color_bot = CATEGORY_COLORS.get(cat_slug, ((34, 197, 94), (21, 128, 61)))

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # Gradient background
    for y in range(height):
        t = y / height
        r = int(color_top[0] + (color_bot[0] - color_top[0]) * t)
        g = int(color_top[1] + (color_bot[1] - color_top[1]) * t)
        b = int(color_top[2] + (color_bot[2] - color_top[2]) * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Dark overlay for readability
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 120))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Load fonts
    font_paths = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    def get_font(size):
        for fp in font_paths:
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
        return ImageFont.load_default()

    f_huge   = get_font(100)
    f_big    = get_font(72)
    f_med    = get_font(52)
    f_small  = get_font(40)
    f_tag    = get_font(34)

    # ── Top badge ──
    badge_y = 160
    draw.rounded_rectangle(
        [(width//2 - 240, badge_y - 36), (width//2 + 240, badge_y + 36)],
        radius=30, fill=(255, 255, 255, 40)
    )
    draw.text((width//2, badge_y), "HONEST REVIEW", font=f_tag,
              fill=(255, 255, 255), anchor="mm")

    # ── Product name ──
    name_lines = wrap_text(product["name"].upper(), 12)
    name_y = height // 2 - len(name_lines) * 60
    for i, line in enumerate(name_lines):
        draw.text((width//2, name_y + i * 115), line, font=f_huge,
                  fill=(255, 255, 255), anchor="mm")

    # ── Category label ──
    cat_label = cat_slug.replace("-", " ").title()
    draw.text((width//2, height // 2 + len(name_lines) * 60 + 20),
              cat_label, font=f_small, fill=(255, 255, 255, 180), anchor="mm")

    # ── Stars + rating ──
    rating = min(4.9, max(3.8, 3.5 + product.get("gravity", 0) / 50))
    full_stars = int(round(rating))
    stars = "★" * full_stars + "☆" * (5 - full_stars)
    star_y = height // 2 + len(name_lines) * 60 + 120
    draw.text((width//2, star_y), stars, font=f_big, fill=(255, 215, 0), anchor="mm")
    draw.text((width//2, star_y + 80), f"{rating:.1f} / 5.0",
              font=f_med, fill=(255, 255, 255), anchor="mm")

    # ── Divider ──
    div_y = height - 380
    draw.line([(120, div_y), (width - 120, div_y)], fill=(255, 255, 255, 80), width=2)

    # ── Website ──
    draw.text((width//2, div_y + 60), "thehappy-healthy-life.com",
              font=f_tag, fill=(255, 255, 255), anchor="mm")

    # ── CTA ──
    draw.text((width//2, height - 220), "FULL REVIEW IN DESCRIPTION",
              font=f_small, fill=(255, 255, 0), anchor="mm")
    draw.text((width//2, height - 140), "FOLLOW FOR MORE REVIEWS",
              font=f_tag, fill=(255, 255, 255), anchor="mm")

    return img


# ── TTS ───────────────────────────────────────────────────────────────────────

async def _tts_async(script, audio_path, voice):
    import edge_tts
    communicate = edge_tts.Communicate(script, voice=voice, rate="+8%", volume="+10%")
    await communicate.save(audio_path)

def generate_tts(script, audio_path, voice="en-US-GuyNeural"):
    asyncio.run(_tts_async(script, audio_path, voice))


# ── FFmpeg ────────────────────────────────────────────────────────────────────

def get_audio_duration(audio_path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True
    )
    try:
        return float(result.stdout.strip())
    except Exception:
        return 55.0

def assemble_video(bg_path, audio_path, output_path):
    duration = get_audio_duration(audio_path)
    log(f"  Audio duration: {duration:.1f}s")
    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-framerate", "30",
        "-i", bg_path,
        "-i", audio_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-t", str(duration + 1.5),
        "-shortest",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
        output_path
    ], check=True, capture_output=True)


# ── Full generation pipeline ───────────────────────────────────────────────────

def generate_short(product, output_path):
    log(f"  Generating script...")
    script = make_voiceover_script(product)

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = os.path.join(tmp, "audio.mp3")
        bg_path    = os.path.join(tmp, "bg.jpg")

        log(f"  Generating TTS audio (edge-tts)...")
        generate_tts(script, audio_path)

        log(f"  Generating background image...")
        bg = make_background_image(product)
        bg.save(bg_path, "JPEG", quality=95)

        log(f"  Assembling video (FFmpeg)...")
        assemble_video(bg_path, audio_path, output_path)

    size_kb = os.path.getsize(output_path) // 1024
    log(f"  Video ready: {size_kb} KB at {output_path}")


# ── YouTube upload ─────────────────────────────────────────────────────────────

def get_access_token():
    import requests
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id":     YT_CLIENT_ID,
        "client_secret": YT_CLIENT_SECRET,
        "refresh_token": YT_REFRESH_TOKEN,
        "grant_type":    "refresh_token",
    }, timeout=30)
    if r.status_code == 200:
        return r.json().get("access_token")
    log(f"OAuth erreur {r.status_code}: {r.text[:200]}")
    return None

def upload_short(video_path, title, description, tags, access_token):
    import requests

    metadata = {
        "snippet": {
            "title":       title[:100],
            "description": description[:5000],
            "tags":        tags,
            "categoryId":  "26",
        },
        "status": {
            "privacyStatus":          "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

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
        upload_url, data=video_data,
        headers={"Content-Type": "video/mp4", "Content-Length": str(len(video_data))},
        timeout=300,
    )
    return r2.status_code, r2.json() if r2.status_code == 200 else {"error": r2.text[:200]}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import random

    if not YT_CLIENT_ID or not YT_CLIENT_SECRET or not YT_REFRESH_TOKEN:
        log("ERREUR: secrets YouTube non definis")
        sys.exit(1)

    tz_tunis  = timezone(timedelta(hours=1))
    today_key = datetime.now(timezone.utc).astimezone(tz_tunis).strftime("%Y-%m-%d")

    done = load_done()
    if done.get(today_key):
        log(f"YouTube deja publie pour {today_key}")
        sys.exit(0)

    products = load_products()
    if not products:
        log("Aucun produit OK")
        sys.exit(0)

    post_state = load_post_index()
    idx        = post_state["idx"] % len(products)
    product    = products[idx]

    log(f"=== YouTube Shorts Generator {today_key} ===")
    log(f"  Produit: {product['name']} ({product['category_slug']})")

    access_token = get_access_token()
    if not access_token:
        log("Impossible d'obtenir access token YouTube")
        sys.exit(1)

    rating  = min(4.9, max(3.8, 3.5 + product.get("gravity", 0) / 50))
    cat_tag = CATEGORY_TAGS.get(product["category_slug"], "health")

    title = random.choice(TITLE_TEMPLATES).format(
        name=product["name"], rating=f"{rating:.1f}"
    )
    description = DESCRIPTION_TEMPLATE.format(
        name=product["name"],
        desc=product["description"][:300],
        rating=f"{rating:.1f}",
        site_url=SITE_URL,
        cat_slug=product["category_slug"],
        slug=product["slug"],
        cat_tag=cat_tag,
    )
    tags = [product["name"], "supplement review", "honest review",
            "health supplement", "2026", cat_tag, "shorts"]

    with tempfile.TemporaryDirectory() as tmp:
        video_path = os.path.join(tmp, f"{product['slug']}.mp4")
        generate_short(product, video_path)

        log(f"  Uploading to YouTube...")
        status, resp = upload_short(video_path, title, description, tags, access_token)

    if status == 200:
        video_id = resp.get("id", "")
        log(f"  OK: {product['name']} -> https://youtube.com/shorts/{video_id}")
        result_status = "ok"
    else:
        log(f"  ERREUR {status}: {resp}")
        result_status = "error"

    post_state["idx"] = idx + 1
    save_post_index(post_state)

    done[today_key] = {
        "product": product["name"],
        "status":  result_status,
        "at":      datetime.utcnow().isoformat(),
    }
    save_done(done)
    log("=== Termine ===")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log(f"EXCEPTION:\n{traceback.format_exc()}")
        sys.exit(1)
