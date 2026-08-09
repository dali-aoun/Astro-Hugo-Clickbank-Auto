"""
publish_youtube.py - YouTube Shorts generator + uploader
Pipeline: Pexels real-person video -> edge-tts voiceover -> FFmpeg overlay -> YouTube upload
Fallback: static Pillow gradient background when PEXELS_API_KEY is absent or search fails.
"""

import os, sys, json, time, traceback, subprocess, asyncio, tempfile, random
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DONE_FILE       = os.path.join(BASE_DIR, "yt_published_done.json")
PRODUCTS_FILE   = os.path.join(BASE_DIR, "products.json")
POST_INDEX_FILE = os.path.join(BASE_DIR, "yt_post_index.json")

YT_CLIENT_ID     = os.environ.get("YT_CLIENT_ID", "")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", "")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN", "")
PEXELS_API_KEY   = os.environ.get("PEXELS_API_KEY", "")

SITE_URL = "https://reviews.thehappy-healthy-life.com"

TITLE_TEMPLATES = [
    "Why {name} is the #1 {cat_label} supplement in 2026 #shorts",
    "I tested {name} for 30 days — the result shocked me #shorts",
    "The truth about {name} nobody tells you #shorts",
    "{name}: before you buy, watch this #shorts",
    "Doctors hate this — {name} exposed #shorts",
    "{name} — real results or total scam? #shorts",
    "3 reasons {name} actually works (and 1 reason it doesn't) #shorts",
    "What happened when I took {name} every day for a month #shorts",
]

CATEGORY_LABELS = {
    "dental-health":    "dental health",
    "prostate-health":  "prostate health",
    "male-performance": "male performance",
    "brain-and-senses": "brain health",
    "weight-loss":      "weight loss",
    "beauty-skin":      "skin care",
    "womens-health":    "women's health",
    "blood-sugar":      "blood sugar",
    "joint-pain":       "joint pain",
    "sleep":            "sleep",
    "heart-health":     "heart health",
    "general-health":   "wellness",
}

DESCRIPTION_TEMPLATE = """{hook}

{name} — does it actually work in 2026?

{desc}

Designed for: {audience}

Our independent rating: ⭐ {rating}/5

📋 Full review (ingredients, side effects, where to buy at best price):
{site_url}/{cat_slug}/{slug}/

#{cat_tag} #supplementreview #{name_tag}review #naturalhealth #honestreviews #shorts
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

CATEGORY_HOOKS = {
    "dental-health": [
        "Here's something dentists will never tell you. The bacteria destroying your gums right now cannot be fixed with brushing alone.",
        "Most people have no idea that 99% of dental problems start with one thing — the wrong bacteria in your mouth.",
        "If your gums bleed when you brush, it's not because you're brushing wrong. It's a sign of something much deeper.",
    ],
    "prostate-health": [
        "If you're waking up three or more times a night to use the bathroom, listen carefully. This is not normal aging.",
        "Most doctors don't tell men this. The real cause of prostate problems has nothing to do with age. It starts with something else entirely.",
        "The urge to urinate every two hours. The weak stream. The burning. Most men just accept this. They shouldn't.",
    ],
    "male-performance": [
        "If your energy and drive feel nothing like they did at 30, there's a specific reason — and it's not what you think.",
        "Low testosterone affects 1 in 4 men over 40. Most have no idea. And most doctors treat the symptom, not the cause.",
        "Men — your performance issues in the bedroom are almost never psychological. Here's what's actually happening.",
    ],
    "brain-and-senses": [
        "Scientists discovered that brain fog, poor memory, and tinnitus often share one hidden root cause most people never address.",
        "If you ever walk into a room and forget why you went there, this is your brain sending an urgent signal.",
        "The ringing in your ears is not a hearing problem. New research shows it originates in the brain — not the ear.",
    ],
    "weight-loss": [
        "Eating less and exercising more doesn't work for everyone. And there's now a scientific reason why — and it's not willpower.",
        "Doctors finally admitted it: the reason most people can't lose belly fat has nothing to do with calories. It's this instead.",
        "If you've tried every diet and still can't lose the weight, this video will explain exactly why — and what actually works.",
    ],
    "beauty-skin": [
        "Your skin is aging 3 times faster if you're missing this one thing. And it has nothing to do with what you put on your face.",
        "Wrinkles, dark spots, and sagging skin are not just about getting older. Researchers found a gut bacteria connection that changes everything.",
        "The real reason your skin looks tired and dull — it starts in your gut, not on your face.",
    ],
    "womens-health": [
        "One in three women over 40 deals with this every day and never talks about it. It's completely treatable — naturally.",
        "If you've ever laughed, sneezed, or exercised and felt that embarrassing leak — there's a specific bacterial imbalance causing it.",
        "Bladder leaks, urgency, and UTIs are not just aging. Research shows the urinary microbiome is the missing piece.",
    ],
    "blood-sugar": [
        "If you feel exhausted after meals, crave sugar constantly, or wake up tired — your blood sugar is doing something dangerous.",
        "The blood sugar crash that happens two hours after eating is sabotaging your energy, mood, and weight. Here's the fix.",
        "Pre-diabetes affects 96 million Americans — and most don't even know they have it. Here's what your body is telling you.",
    ],
    "joint-pain": [
        "Cartilage doesn't grow back on its own. But researchers found one compound that actually restores joint cushioning naturally.",
        "The pain you feel in your knees and hips every morning is not just aging. Something specific is causing the inflammation.",
        "Most joint supplements fail because they target inflammation. The real problem starts much deeper — in your synovial fluid.",
    ],
    "sleep": [
        "If you wake up at 3am and can't fall back asleep, your body is signaling a cortisol problem — not a sleep problem.",
        "The reason you wake up exhausted despite 8 hours of sleep: you're probably not reaching deep sleep at all.",
        "Most sleep supplements use melatonin. But melatonin only helps you fall asleep — not stay asleep. Here's what actually works.",
    ],
    "heart-health": [
        "Your heart beats 100,000 times per day. If your energy, blood pressure, or circulation is off — it's working even harder.",
        "High cholesterol is not caused by eating fat. The real cause is something most cardiologists don't test for.",
        "The silent inflammation in your arteries right now is far more dangerous than your cholesterol number. Here's how to fix it.",
    ],
    "general-health": [
        "There's a mineral almost every American is deficient in. It affects your energy, sleep, weight, and mood — and most doctors never test for it.",
        "The root cause of chronic fatigue, brain fog, and unexplained weight gain is often the same thing. And it's fixable.",
        "If you feel off but every blood test comes back normal — this is the video you need to watch.",
    ],
}

def make_voiceover_script(product):
    name     = product["name"]
    desc     = product.get("description", "a popular health supplement")
    audience = product.get("audience", "health-conscious adults")
    gravity  = product.get("gravity", 0)
    rating   = min(4.9, max(3.8, 3.5 + gravity / 50))
    cat_slug = product.get("category_slug", "general-health")

    hooks = CATEGORY_HOOKS.get(cat_slug, CATEGORY_HOOKS["general-health"])
    hook  = random.choice(hooks)

    script = f"""
{hook}

I'm going to tell you about {name} — and I'm going to be completely honest with you.

{name} is {desc}

It was specifically created for {audience}

Here's what makes it different from everything else out there.

Most supplements treat symptoms. {name} targets the root cause.
The formula uses clinically studied natural ingredients — no stimulants, no harsh chemicals.
And thousands of people are reporting real results within the first few weeks.

Is it perfect? No. Let me give you the honest breakdown.

What works: the ingredients are well-dosed and research-backed.
The feedback from real users is consistently positive.
And the company stands behind it with a money-back guarantee.

What to know: it takes 4 to 6 weeks for full results. Supplements are not magic.
You need to be consistent.

My rating? {rating:.1f} out of 5 stars.

If {name} sounds right for you, I've left the full review in the description —
ingredients breakdown, pricing, side effects, and where to get the best deal.

Follow for more honest health supplement reviews.
""".strip()
    return script, hook


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


# ── Pexels video integration ──────────────────────────────────────────────────

PEXELS_QUERIES = {
    "dental-health":    ["woman toothache pain jaw face", "person dental pain grimace", "man holding jaw tooth pain"],
    "prostate-health":  ["man bathroom night urgency", "older man tired fatigue sitting", "man discomfort lower abdomen"],
    "male-performance": ["man tired exhausted low energy desk", "man frustrated stressed middle age", "man fatigued sitting"],
    "brain-and-senses": ["woman headache brain fog stressed office", "person confused memory problem", "man headache work"],
    "weight-loss":      ["woman frustrated belly fat mirror", "person scale weight frustrated", "woman struggling belly fat"],
    "beauty-skin":      ["woman sad mirror aging wrinkles face", "woman unhappy skin aging", "person examining face wrinkles"],
    "womens-health":    ["woman pain cramps hormones stressed", "woman uncomfortable urge bathroom", "woman exhausted fatigue"],
    "blood-sugar":      ["person dizzy tired after meal", "woman fatigue sugar crash energy", "person exhausted afternoon"],
    "joint-pain":       ["person knee pain arthritis stairs", "elderly person joint pain walking", "man holding knee pain"],
    "sleep":            ["person insomnia awake night bed", "woman sleepless night tired", "man awake 3am dark room"],
    "heart-health":     ["person chest pain stress heart", "man holding chest pain worry", "person heart stress anxiety"],
    "general-health":   ["person chronic fatigue tired couch", "woman sick fatigue pain", "man exhausted daily life"],
}


def pexels_search_video(query):
    """Search Pexels for a portrait video. Returns a download URL or None."""
    import requests
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "orientation": "portrait", "per_page": 10, "size": "medium"},
            timeout=30,
        )
        if r.status_code != 200:
            log(f"    Pexels search failed {r.status_code}")
            return None
        videos = r.json().get("videos", [])
        if not videos:
            return None
        video = random.choice(videos[:5])
        files = video.get("video_files", [])
        files_sorted = sorted(
            [f for f in files if f.get("quality") in ("hd", "sd")],
            key=lambda x: x.get("width", 0), reverse=True,
        )
        for f in files_sorted:
            url = f.get("link")
            if url:
                return url
    except Exception as e:
        log(f"    Pexels exception: {e}")
    return None


def download_video(url, dest_path):
    import requests
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
    size_kb = os.path.getsize(dest_path) // 1024
    log(f"    Downloaded {size_kb} KB")


def get_font_paths():
    candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def process_pexels_video(raw_path, audio_path, output_path, product):
    """Crop Pexels video to 9:16, add text overlay, mix TTS audio."""
    name    = product["name"]
    gravity = product.get("gravity", 0)
    rating  = min(4.9, max(3.8, 3.5 + gravity / 50))
    stars   = "★" * int(round(rating)) + "☆" * (5 - int(round(rating)))

    audio_dur  = get_audio_duration(audio_path)
    target_dur = min(60.0, audio_dur + 1.5)

    font_path = get_font_paths()
    if font_path:
        safe_font   = font_path.replace(":", "\\:")
        name_escaped = name.replace("'", "\\'").replace(":", "\\:")
        font_filter = (
            f"drawbox=x=0:y=ih*0.62:w=iw:h=ih*0.38:color=black@0.65:t=fill,"
            f"drawtext=fontfile={safe_font}:text='HONEST REVIEW':fontsize=36"
            f":fontcolor=white@0.85:x=(w-text_w)/2:y=h*0.60:shadowx=1:shadowy=1,"
            f"drawtext=fontfile={safe_font}:text='{name_escaped}':fontsize=58:fontcolor=white"
            f":x=(w-text_w)/2:y=h*0.66:shadowx=2:shadowy=2,"
            f"drawtext=fontfile={safe_font}:text='{stars} {rating:.1f}/5':fontsize=44"
            f":fontcolor=gold:x=(w-text_w)/2:y=h*0.77:shadowx=1:shadowy=1,"
            f"drawtext=fontfile={safe_font}:text='thehappy-healthy-life.com':fontsize=32"
            f":fontcolor=white@0.9:x=(w-text_w)/2:y=h*0.86,"
            f"drawtext=fontfile={safe_font}:text='FULL REVIEW IN DESCRIPTION':fontsize=34"
            f":fontcolor=yellow:x=(w-text_w)/2:y=h*0.92:shadowx=1:shadowy=1"
        )
    else:
        font_filter = "drawbox=x=0:y=ih*0.7:w=iw:h=ih*0.3:color=black@0.7:t=fill"

    vf = (
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        f"{font_filter}"
    )
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", raw_path,
        "-i", audio_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-t", str(target_dur),
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"    FFmpeg error: {result.stderr[-300:]}")
        raise RuntimeError("ffmpeg failed on Pexels video")
    size_kb = os.path.getsize(output_path) // 1024
    log(f"    Video ready: {size_kb} KB, {target_dur:.1f}s")


# ── Full generation pipeline ───────────────────────────────────────────────────

def generate_short(product, output_path):
    log(f"  Generating script...")
    script, hook = make_voiceover_script(product)
    product["_hook"] = hook

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = os.path.join(tmp, "audio.mp3")

        log(f"  Generating TTS audio (edge-tts)...")
        generate_tts(script, audio_path)

        # Try Pexels real-person video first
        pexels_ok = False
        if PEXELS_API_KEY:
            cat_slug = product.get("category_slug", "general-health")
            queries  = PEXELS_QUERIES.get(cat_slug, ["healthy lifestyle"])
            for query in queries:
                log(f"  Pexels search: '{query}'")
                video_url = pexels_search_video(query)
                if video_url:
                    raw_path = os.path.join(tmp, "raw.mp4")
                    log(f"  Downloading Pexels video...")
                    try:
                        download_video(video_url, raw_path)
                        log(f"  Processing video with FFmpeg overlay...")
                        process_pexels_video(raw_path, audio_path, output_path, product)
                        pexels_ok = True
                    except Exception as e:
                        log(f"  Pexels video failed: {e} — falling back to static bg")
                    break

        if not pexels_ok:
            # Fallback: static gradient background
            bg_path = os.path.join(tmp, "bg.jpg")
            log(f"  Generating static background image...")
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

    with tempfile.TemporaryDirectory() as tmp:
        video_path = os.path.join(tmp, f"{product['slug']}.mp4")
        generate_short(product, video_path)

        hook       = product.get("_hook", "")
        cat_label  = CATEGORY_LABELS.get(product["category_slug"], "health")
        name_tag   = product["name"].lower().replace(" ", "").replace("-", "")

        title = random.choice(TITLE_TEMPLATES).format(
            name=product["name"], rating=f"{rating:.1f}", cat_label=cat_label
        )
        description = DESCRIPTION_TEMPLATE.format(
            name=product["name"],
            hook=hook,
            desc=product["description"][:250],
            audience=product.get("audience", "adults seeking better health"),
            rating=f"{rating:.1f}",
            site_url=SITE_URL,
            cat_slug=product["category_slug"],
            slug=product["slug"],
            cat_tag=cat_tag,
            name_tag=name_tag,
        )
        tags = [
            product["name"], "supplement review", "honest review",
            "health supplement", "natural health", "2026", cat_tag,
            cat_label, "does it work", "shorts",
        ]

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
