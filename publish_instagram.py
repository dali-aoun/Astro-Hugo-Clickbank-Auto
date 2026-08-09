"""
publish_instagram.py — Instagram educational content publisher
Strategy: informational health tips → followers → bio link clicks (no product photos)
Images generated with Pillow (1080x1350), committed to the repo, then served via
raw.githubusercontent.com as public URLs for Instagram Graph API.

Modes:
  --generate   Generate and save images to ig_content/ (run BEFORE commit)
  --publish    Publish using already-committed images (run AFTER commit+push)
  (no arg)     Full flow: generate + upload check + publish (local testing only)
"""

import os, sys, json, time, io, traceback, subprocess, asyncio, tempfile, random as _random
from datetime import datetime, timezone, timedelta

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
DONE_FILE      = os.path.join(BASE_DIR, "ig_published_done.json")
LOG_FILE       = os.path.join(BASE_DIR, "ig_publish_log.txt")
POST_IDX_FILE  = os.path.join(BASE_DIR, "ig_post_index.json")
CONTENT_DIR    = os.path.join(BASE_DIR, "ig_content")
PENDING_FILE      = os.path.join(BASE_DIR, "ig_pending.json")
REEL_IDX_FILE     = os.path.join(BASE_DIR, "ig_reel_idx.json")
REEL_PENDING_FILE = os.path.join(BASE_DIR, "ig_reel_pending.json")

IG_TOKEN   = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
IG_USER_ID = os.environ.get("INSTAGRAM_USER_ID", "")
ASSETS_REPO = "dali-aoun/ig-assets"  # Public repo — accessible by Meta crawlers

SITE_URL     = "https://reviews.thehappy-healthy-life.com"
POSTS_PER_DAY = 2
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

# ── Pexels search queries per category ───────────────────────────────────────
PEXELS_QUERIES = {
    "dental-health":    ["woman toothache jaw pain grimace", "person dental pain holding face", "man tooth pain suffering"],
    "prostate-health":  ["man bathroom urgency night discomfort", "older man tired low energy", "man sitting discomfort"],
    "male-performance": ["man exhausted tired low energy sitting", "man frustrated stressed bedroom", "man fatigue middle age"],
    "brain-and-senses": ["woman headache brain fog stressed", "person memory problem confused", "person tinnitus ear pain"],
    "weight-loss":      ["woman frustrated belly fat scale", "person stomach fat struggle mirror", "woman unhappy body weight"],
    "beauty-skin":      ["woman sad wrinkles aging mirror", "woman aging skin unhappy reflection", "person examine skin face"],
    "womens-health":    ["woman pain cramps hormones stressed", "woman discomfort pelvic bathroom urgency", "woman exhausted hormonal"],
    "blood-sugar":      ["person dizzy fatigue sugar crash meal", "woman tired energy crash afternoon", "person exhausted lunch"],
    "joint-pain":       ["person knee pain stairs arthritis", "elderly knee joint pain walking", "person holding knee pain"],
    "sleep":            ["person insomnia awake night dark room", "woman sleepless night tired exhausted", "man awake night bed"],
    "heart-health":     ["person chest pain heart worry stress", "man holding chest cardiovascular", "person heart anxiety"],
    "general-health":   ["person chronic fatigue sick tired couch", "woman ill pain daily life", "man exhausted energy"],
}

# ── Pexels + FFmpeg + TTS helpers ────────────────────────────────────────────

def pexels_search_video(query, api_key, orientation="portrait", per_page=10):
    import requests
    headers = {"Authorization": api_key}
    params  = {"query": query, "orientation": orientation, "per_page": per_page, "size": "medium"}
    try:
        r = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params, timeout=15)
        if r.status_code != 200:
            return None
        videos = r.json().get("videos", [])
        if not videos:
            return None
        pool = videos[:5]
        video = _random.choice(pool)
        files = video.get("video_files", [])
        hd = [f for f in files if f.get("width", 0) >= 720 and f.get("height", 0) >= f.get("width", 1)]
        chosen = hd[0] if hd else (files[0] if files else None)
        return chosen["link"] if chosen else None
    except Exception:
        return None


def download_video(url, dest_path):
    import requests
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)


def _reel_tts_async(script, audio_path):
    import edge_tts
    async def _run():
        comm = edge_tts.Communicate(script, voice="en-US-AriaNeural", rate="+5%", volume="+10%")
        await comm.save(audio_path)
    asyncio.run(_run())


def make_reel_voiceover(product, audio_path):
    name     = product["name"]
    desc     = product.get("description", "a health supplement")
    audience = product.get("audience", "people looking to improve their health")
    gravity  = float(product.get("gravity", 50))
    rating   = min(5.0, max(3.5, 3.5 + (gravity / 200.0)))
    slug     = product.get("slug", "")
    cat_slug = product.get("category_slug", "general-health")
    link     = f"{SITE_URL}/{cat_slug}/{slug}/"

    script = f"""
{name}. Is it really worth it?
{name} is {desc}.
It's designed for {audience}.
With a popularity score of {int(gravity)}, thousands of people are already using it.
My honest rating? {rating:.1f} out of 5 stars.
Want the full ingredient breakdown and real results?
Tap the link in my bio right now.
Follow me for more honest supplement reviews every day.
""".strip()
    _reel_tts_async(script, audio_path)


def get_audio_duration_ig(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, text=True, check=True,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 45.0


def process_reel_video(raw_path, audio_path, output_path, product):
    name    = product["name"]
    cat_slug = product.get("category_slug", "general-health")
    gravity = float(product.get("gravity", 50))
    rating  = min(5.0, max(3.5, 3.5 + (gravity / 200.0)))
    stars   = "★" * int(round(rating)) + "☆" * (5 - int(round(rating)))
    site    = "reviews.thehappy-healthy-life.com"
    cta     = "Link in bio → Full Review"

    target_dur = get_audio_duration_ig(audio_path) + 1.5

    font_paths = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    font_file = next((p for p in font_paths if os.path.exists(p)), "")
    safe_font = font_file.replace(":", "\\:")

    def esc(t):
        return t.replace("'", "’").replace(":", "\\:")

    if safe_font:
        vf = (
            f"scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,"
            f"drawbox=x=0:y=ih*0.60:w=iw:h=ih*0.40:color=black@0.70:t=fill,"
            f"drawtext=fontfile={safe_font}:text='{esc(name)}':fontsize=56:fontcolor=white"
            f":x=(w-text_w)/2:y=h*0.63:line_spacing=8,"
            f"drawtext=fontfile={safe_font}:text='{stars}  {rating:.1f}/5':fontsize=44"
            f":fontcolor=#FFD700:x=(w-text_w)/2:y=h*0.75,"
            f"drawtext=fontfile={safe_font}:text='{esc(site)}':fontsize=30"
            f":fontcolor=#AAAAAA:x=(w-text_w)/2:y=h*0.84,"
            f"drawtext=fontfile={safe_font}:text='{esc(cta)}':fontsize=34"
            f":fontcolor=white:x=(w-text_w)/2:y=h*0.90"
        )
    else:
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", raw_path,
        "-i", audio_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-t", str(target_dur),
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def load_all_products():
    """Load all products from products.json (no MP4 file check)."""
    products_file = os.path.join(BASE_DIR, "products.json")
    try:
        with open(products_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    result = []
    for cat in data.get("categories", []):
        for p in cat.get("products", []):
            if p.get("status") == "ok":
                result.append({**p, "category_slug": cat["slug"]})
    return result


# ── Category config ───────────────────────────────────────────────────────────
CATEGORIES = {
    "dental":   {"name": "Dental Health",       "accent": (16, 185, 129),  "cat_url": "dental-health",     "hashtags": "#OralHealth #DentalTips #GumHealth #TeethCare #OralCare #DentalHealth #SmileHealth #ToothCare #OralHygiene #HealthySmile"},
    "prostate": {"name": "Prostate Health",      "accent": (59, 130, 246),  "cat_url": "prostate-health",   "hashtags": "#ProstateHealth #MensHealth #BPH #ProstateSupport #MensWellness #ProstateCancer #MaleHealth #UrinaryHealth #MensNutrition #HealthyMen"},
    "male":     {"name": "Male Performance",     "accent": (239, 68, 68),   "cat_url": "male-performance",  "hashtags": "#Testosterone #MensHealth #MalePerformance #TestosteroneBoost #MaleVitality #MensWellness #HormoneHealth #MaleFitness #MensFitness #Vitality"},
    "brain":    {"name": "Brain & Cognitive",    "accent": (139, 92, 246),  "cat_url": "brain-and-senses",  "hashtags": "#BrainHealth #CognitiveHealth #Nootropics #MentalClarity #BrainFog #NeuroplasticityTraining #BrainFacts #MemoryBoost #FocusTips #BrainScience"},
    "weight":   {"name": "Weight Loss",          "accent": (245, 158, 11),  "cat_url": "weight-loss",       "hashtags": "#WeightLoss #FatBurner #MetabolismBoost #WeightLossTips #HealthyWeight #WeightLossJourney #Slim #FatLoss #WeightLossFacts #Metabolism"},
    "beauty":   {"name": "Beauty & Skin Care",   "accent": (236, 72, 153),  "cat_url": "beauty-skin",       "hashtags": "#SkinCare #Beauty #AntiAging #GlowingSkin #SkincareTips #HealthySkin #SkincareFacts #BeautyTips #NaturalBeauty #SkincareRoutine"},
    "womens":   {"name": "Women's Health",       "accent": (168, 85, 247),  "cat_url": "womens-health",     "hashtags": "#WomensHealth #PelvicFloor #BladderHealth #WomenWellness #WomensBodyHealth #PelvicHealthTips #UTIPrevention #WomensHormones #HormoneBalance #WomensFitness"},
    "blood":    {"name": "Blood Sugar Support",  "accent": (6, 182, 212),   "cat_url": "blood-sugar",       "hashtags": "#BloodSugar #Diabetes #PreDiabetes #MetabolicHealth #BloodSugarControl #InsulinResistance #DiabetesTips #GlucoseControl #DiabetesPrevention #HealthyBloodSugar"},
    "joint":    {"name": "Joint Pain Relief",    "accent": (20, 184, 166),  "cat_url": "joint-pain",        "hashtags": "#JointHealth #JointPain #Arthritis #JointCare #JointRelief #JointPainRelief #AntiInflammatory #BoneHealth #ArthritisTips #JointSupport"},
    "sleep":    {"name": "Sleep Supplements",    "accent": (99, 102, 241),  "cat_url": "sleep",             "hashtags": "#SleepTips #BetterSleep #SleepHealth #Insomnia #SleepScience #NaturalSleepAid #SleepBetter #SleepFacts #SleepSupport #HealthySleep"},
    "heart":    {"name": "Heart Health",         "accent": (244, 63, 94),   "cat_url": "heart-health",      "hashtags": "#HeartHealth #CardiovascularHealth #HeartDisease #HeartCare #HeartHealthTips #CardiovascularFitness #HealthyHeart #HeartFacts #BloodPressure #Cholesterol"},
    "general":  {"name": "General Health",       "accent": (34, 197, 94),   "cat_url": "general-health",    "hashtags": "#HealthTips #WellnessTips #NaturalHealth #HealthFacts #HealthyLiving #Supplements #NaturalRemedies #WellnessJourney #HealthAndWellness #DailyHealth"},
}

CAT_ROTATION = [
    "dental", "weight", "brain", "prostate", "beauty", "heart",
    "male", "blood", "sleep", "joint", "womens", "general",
]

# ── Content library (same as Pinterest) ───────────────────────────────────────
CONTENT = {
    "dental": [
        ("Did You Know?", "Your mouth contains over 700 species of bacteria.\nMost are harmless — but the bad ones cause gum disease, cavities, and bad breath.", "Protect your oral microbiome daily."),
        ("Warning Sign", "Bleeding gums when you brush is NOT normal.\nIt's an early sign of gingivitis — reversible if you act now.", "Don't ignore bleeding gums."),
        ("Fact", "Gum disease is linked to heart disease, diabetes, and Alzheimer's.\nYour oral health affects your whole body.", "Your mouth is a window to your health."),
        ("Daily Tip", "The best time to brush is 30 minutes AFTER eating.\nBrushing immediately after meals damages enamel.", "Timing your brushing matters."),
        ("Statistic", "47% of adults over 30 have some form of gum disease.\nThe earlier you treat it, the easier it is to reverse.", "Are you in the 47%?"),
        ("Did You Know?", "Your tongue holds more bacteria than any other part of your mouth.\nCleaning it daily can eliminate up to 70% of bad breath.", "Don't skip your tongue."),
        ("Tip", "Oil pulling with coconut oil for 10–15 minutes\nreduces harmful bacteria by up to 30%.\nAncient practice, modern science confirms it.", "Ancient wisdom meets modern research."),
        ("Warning", "Dry mouth is a silent tooth destroyer.\nSaliva neutralizes acids and remineralizes enamel.\nWithout it, cavities accelerate.", "Stay hydrated for healthier teeth."),
        ("Fact", "Vitamin D deficiency is directly linked to higher rates of tooth decay.\nYour teeth need vitamins too.", "Vitamin D = stronger teeth."),
        ("Tip", "Flossing removes plaque from 35% of tooth surfaces your brush can't reach.\nSkip floss, skip a third of your mouth.", "Flossing isn't optional."),
        ("Did You Know?", "Sugar doesn't directly rot your teeth.\nBacteria eat sugar and produce acid — the acid destroys enamel.", "The real culprit is acid, not sugar."),
        ("Fact", "Probiotics for oral health are the new frontier.\nCertain strains outcompete the harmful bacteria in your mouth.", "Your gut isn't the only place probiotics help."),
        ("Tip", "Green tea contains catechins that reduce oral inflammation\nand kill harmful bacteria.\nSwap one coffee for green tea daily.", "Green tea = natural dental protection."),
        ("Fact", "Stress causes dry mouth, teeth grinding, and gum inflammation.\nYour mental health directly impacts your oral health.", "Stress affects your teeth too."),
        ("Warning", "Many mouthwashes with alcohol kill good bacteria too.\nLook for alcohol-free formulas that preserve your oral microbiome.", "Choose your mouthwash wisely."),
        ("Did You Know?", "Your enamel is the hardest substance in your body — harder than bone.\nBut once it's gone, it doesn't grow back.", "Protect what you can't replace."),
        ("Tip", "Crunchy vegetables like celery and carrots naturally clean teeth.\nThey increase saliva flow and scrub away plaque.", "Food can clean your teeth too."),
        ("Statistic", "Americans spend $124 billion on dental care each year.\nMost problems are preventable with daily habits.", "Prevention is 100x cheaper than treatment."),
        ("Warning", "Grinding your teeth at night can wear down enamel by 0.2mm per year.\nOver a decade, that's irreversible damage.", "Bruxism is silently destroying teeth."),
        ("Fact", "Calcium alone won't strengthen teeth without adequate Vitamin D.\nThey work together — you need both.", "D3 and calcium are a team."),
    ],
    "weight": [
        ("Fact", "Your gut microbiome controls up to 30% of calories you absorb.\nA healthy gut means better weight management.", "Fix your gut, fix your weight."),
        ("Did You Know?", "Sleeping less than 6 hours per night increases hunger hormones by 28%.\nPoor sleep makes weight loss nearly impossible.", "Sleep is your secret weight loss tool."),
        ("Tip", "Drinking 500ml of water 30 minutes before meals reduces calorie intake by 13%.\nHydration is a free weight loss tool.", "Drink water before every meal."),
        ("Statistic", "People who eat breakfast lose 17% more weight than breakfast skippers.\nDon't skip your morning meal.", "Breakfast matters more than you think."),
        ("Warning", "'Diet' drinks still spike insulin and increase cravings.\nArtificial sweeteners can make weight loss harder.", "Diet drinks aren't the solution."),
        ("Fact", "Protein requires 25–30% of its own calories to be digested.\nEating more protein literally boosts your metabolism.", "Protein is the ultimate metabolism food."),
        ("Did You Know?", "Stress triggers cortisol, which directs your body to store fat around the belly.\nManaging stress is a weight loss strategy.", "Belly fat starts in your mind."),
        ("Tip", "A 10-minute walk after eating reduces blood sugar spikes by 22%.\nThis simple habit prevents fat storage.", "Walk after meals — it works."),
        ("Statistic", "70% of your weight loss results come from what you eat.\nExercise alone rarely works without diet changes.", "You can't out-exercise a bad diet."),
        ("Warning", "Skipping meals slows your metabolism by up to 30%.\nYour body goes into starvation mode and holds onto fat.", "Skipping meals is counterproductive."),
        ("Fact", "Green tea extract increases fat burning by 17% during exercise.\nThe EGCG compound activates fat oxidation enzymes.", "Green tea is a real fat burner."),
        ("Tip", "Eating slowly and chewing thoroughly reduces calorie intake by up to 10%.\nYour brain needs 20 minutes to register fullness.", "Slow down and chew your food."),
        ("Statistic", "People who track their food intake lose twice as much weight as those who don't.\nAwareness is the first step.", "Track it to hack it."),
        ("Fact", "Fiber expands in your stomach and slows digestion, keeping you full longer.\nAim for 25–35g of fiber per day.", "Fiber = natural appetite suppressant."),
        ("Warning", "Fad diets that eliminate entire food groups cause muscle loss, not just fat loss.\nMuscle burns calories even at rest.", "Protect your muscle mass."),
        ("Did You Know?", "Your liver is your primary fat-burning organ.\nNon-alcoholic fatty liver is found in 25% of adults — it kills metabolism.", "Liver health = fat-burning capacity."),
        ("Tip", "Resistance training builds muscle that burns calories 24/7.\n2 sessions per week is enough to boost resting metabolism.", "Lift weights to burn fat at rest."),
        ("Fact", "Eating spicy food with capsaicin burns an extra 50 calories per meal.\nSpice up your meals for free calorie burn.", "Spicy food burns calories."),
        ("Did You Know?", "Cold exposure activates brown fat — the type that burns calories for heat.\nCold showers can burn an extra 50–100 calories per session.", "Cold showers accelerate fat loss."),
        ("Statistic", "The average person makes 200+ food-related decisions per day.\nMost are unconscious — your environment shapes your choices.", "Design your environment for success."),
    ],
    "brain": [
        ("Fact", "Your brain is 60% fat by dry weight.\nThe type of fat you eat directly determines how well your brain functions.", "Feed your brain the right fats."),
        ("Did You Know?", "You have more neural connections than stars in the Milky Way.\nBut they weaken without the right nutrients.", "Your brain is extraordinary — protect it."),
        ("Tip", "Exercise increases BDNF by up to 3x.\nBDNF is like fertilizer for brain cells.", "Exercise is the most powerful brain supplement."),
        ("Warning", "Chronic stress physically shrinks the hippocampus — your memory center.\nStress management is literally brain protection.", "Chronic stress shrinks your brain."),
        ("Statistic", "65 million people worldwide live with dementia.\nLifestyle changes in your 40s reduce risk by up to 40%.", "Prevention starts now, not later."),
        ("Fact", "Omega-3 DHA makes up 40% of brain's polyunsaturated fats.\nLow DHA = slower thinking, worse memory.", "Low DHA = brain fog."),
        ("Did You Know?", "Your gut produces 95% of your body's serotonin.\nAn unhealthy gut means poor mood, brain fog, and anxiety.", "The gut-brain connection is real."),
        ("Tip", "Learning a new skill creates new neural pathways — literally changing your brain's structure.\nLearn something new every week.", "New skills = new brain connections."),
        ("Warning", "Even moderate drinking reduces brain volume over time.\nAlcohol kills brain cells and shrinks the prefrontal cortex.", "Alcohol shrinks your brain."),
        ("Fact", "Sleep is when your brain clears toxic waste through the glymphatic system.\nSkipping sleep lets toxins build up in your brain.", "Sleep is your brain's detox cycle."),
        ("Did You Know?", "Blueberries contain anthocyanins that cross the blood-brain barrier.\nStudies show they improve memory by 20% in older adults.", "Blueberries are brain food."),
        ("Tip", "Meditation increases gray matter in the prefrontal cortex.\n8 weeks of 10 min/day measurably changes brain structure.", "10 minutes of meditation changes your brain."),
        ("Fact", "Curcumin (in turmeric) crosses the blood-brain barrier and reduces amyloid plaques.\nOne of the most studied brain-protective compounds.", "Turmeric protects your brain."),
        ("Warning", "Just 1–2% dehydration impairs cognitive performance significantly.\nChronicdehydration reduces brain volume.", "Dehydration = slower thinking."),
        ("Statistic", "Bilingual people develop Alzheimer's 4–5 years later than monolinguals.\nYour brain can be trained to be more resilient.", "Speaking two languages protects your brain."),
        ("Did You Know?", "The brain uses 20% of your body's energy while being only 2% of body weight.\nBrain fog often means your brain is simply under-fueled.", "Brain fog = underfueled brain."),
        ("Tip", "Cold exposure releases norepinephrine in the brain, improving focus by up to 300%.\nCold showers boost brain performance.", "Cold showers sharpen your focus."),
        ("Fact", "Magnesium deficiency impairs learning and memory in both children and adults.\n68% of Americans don't get enough magnesium.", "Magnesium deficiency = memory problems."),
        ("Statistic", "People who read daily have a 32% lower rate of cognitive decline.\nReading is one of the best free brain exercises.", "Read every day to protect your brain."),
        ("Fact", "Saffron extract is as effective as low-dose antidepressants for mild depression without the side effects.", "Saffron is nature's mood booster."),
    ],
    "prostate": [
        ("Fact", "1 in 8 men will be diagnosed with prostate cancer in their lifetime.\nEarly detection is the key to survival.", "Get checked. Early detection saves lives."),
        ("Did You Know?", "The prostate is only the size of a walnut — but it surrounds the urethra.\nWhen it swells, it affects every bathroom trip.", "A walnut-sized gland with massive impact."),
        ("Tip", "Saw palmetto has been shown to reduce nighttime urination by 48%.\nIt's the most researched herb for prostate support.", "Saw palmetto is backed by science."),
        ("Warning", "Sitting for more than 8 hours per day increases prostate inflammation risk.\nTake a 5-minute standing break every hour.", "Sitting is killing your prostate."),
        ("Statistic", "Prostate problems affect 50% of men over 50, and 90% of men over 80.\nStarting prevention in your 40s makes a massive difference.", "Half of men over 50 have prostate issues."),
        ("Fact", "Lycopene from cooked tomatoes reduces prostate cancer risk by up to 35%.\nCook your tomatoes — heat releases lycopene.", "Cook your tomatoes for prostate protection."),
        ("Tip", "Pumpkin seeds are rich in zinc — the mineral most concentrated in healthy prostate tissue.\nA handful a day supports prostate function.", "Pumpkin seeds = prostate food."),
        ("Warning", "Red meat and dairy increase prostate cancer risk when consumed in excess.\nAim for 2 servings or less per week.", "Watch your red meat intake."),
        ("Fact", "Exercise reduces the risk of BPH by up to 25%.\nJust 30 minutes of walking daily is enough.", "Walking protects your prostate."),
        ("Statistic", "Men who drink 5+ cups of coffee per day have a 59% lower risk of lethal prostate cancer.\nCaffeine appears to slow cancer cell growth.", "Coffee is good for your prostate."),
        ("Tip", "Green tea catechins reduce PSA levels and slow prostate cell division.\n3 cups per day shows measurable effects in studies.", "Drink green tea for prostate health."),
        ("Warning", "Stress hormones (cortisol) worsen prostate inflammation directly.\nStress management isn't optional for men's health.", "Stress inflames your prostate."),
        ("Fact", "Beta-sitosterol improves urine flow and reduces urgency in men with BPH.\nIt works by blocking 5-alpha reductase.", "Beta-sitosterol for better urine flow."),
        ("Statistic", "Men who are overweight are 40% more likely to develop aggressive prostate cancer.\nBody weight directly influences prostate hormones.", "Lose weight, protect your prostate."),
        ("Did You Know?", "The PSA test isn't perfect — 75% of high PSA results are NOT cancer.\nDiscuss your PSA score with context.", "High PSA doesn't always mean cancer."),
        ("Tip", "Vitamin D3 deficiency is strongly linked to aggressive prostate cancer.\nOptimal levels are 60–80 ng/mL.", "Test your Vitamin D3 levels now."),
        ("Fact", "Nettle root extract reduces prostate symptoms and improves urine flow in clinical trials.\nOne of the most-used herbs in European urology.", "Nettle root is used by European urologists."),
        ("Warning", "Antihistamines and cold medications can trigger acute urinary retention in men with BPH.\nAlways check medications if you have prostate issues.", "Cold meds can worsen BPH symptoms."),
        ("Did You Know?", "Frequent ejaculation (21+ times per month) reduces prostate cancer risk by 31%.\nA real Harvard Medical School finding.", "This Harvard finding might surprise you."),
        ("Fact", "High DHT causes prostate growth in older men.\nHormonal balance is crucial for prostate health.", "DHT is the key hormone to watch."),
    ],
    "beauty": [
        ("Fact", "Your skin replaces itself every 27 days.\nWhat you eat this month is literally what your skin will be made of next month.", "You are what you eat — literally on your skin."),
        ("Did You Know?", "UV rays cause 90% of wrinkles.\nSunscreen is the most proven anti-aging product.", "Sunscreen is your #1 anti-aging product."),
        ("Tip", "Retinol stimulates collagen production faster than any other ingredient.\nStart at 0.025% and work up slowly.", "Retinol is the gold standard anti-aging ingredient."),
        ("Warning", "Hot showers strip your skin's natural oil barrier.\nShower in lukewarm water and moisturize within 3 minutes.", "Hot showers age your skin."),
        ("Statistic", "Collagen production decreases by 1% every year after age 20.\nBy 50, you've lost 30% of your skin's structural support.", "You're losing collagen every year after 20."),
        ("Fact", "Your gut microbiome directly influences acne, eczema, and rosacea.\nClear skin starts in the digestive system.", "Clear skin starts in your gut."),
        ("Did You Know?", "Silk pillowcases reduce sleep wrinkles and hair breakage significantly.\nSmall upgrade, big results.", "Switch to silk — your skin will thank you."),
        ("Tip", "Vitamin C serum (morning) + retinol (night) is the most effective anti-aging routine.\nThey work on different skin repair pathways.", "Morning C, night retinol — the ultimate combo."),
        ("Fact", "Hyaluronic acid holds up to 1000x its weight in water.\nThe most effective hydrating molecule for skin.", "One molecule holds 1000x its weight in water."),
        ("Statistic", "Women touch their face an average of 23 times per hour.\nEach touch transfers bacteria and causes breakouts.", "Stop touching your face — 23x per hour!"),
        ("Did You Know?", "Sleep is when your skin regenerates — growth hormone peaks at night.\nMissing sleep ages your skin faster than sun exposure.", "Sleep is your skin's repair time."),
        ("Tip", "Niacinamide (Vitamin B3) reduces pore size, fades dark spots, and controls oil.\nThe most versatile skincare ingredient.", "Niacinamide does everything for your skin."),
        ("Warning", "Fragrance is the #1 cause of skincare allergies.\nChoose fragrance-free for sensitive skin.", "Check your skincare for fragrance."),
        ("Fact", "Ceramides make up 50% of your skin's protective barrier.\nWithout them, moisture escapes and irritants enter.", "Ceramides are your skin's shield."),
        ("Statistic", "People who eat 5+ vegetable servings daily show measurably younger-looking skin at any age.\nYour plate is your skincare routine.", "Eat your way to younger skin."),
        ("Did You Know?", "The skin around your eyes is 10x thinner than the rest of your face.\nThis is why it shows aging first.", "Your eye area needs special protection."),
        ("Tip", "Gua sha massage increases lymphatic drainage and reduces puffiness by 25% in 4 weeks.\nInclude it in your morning routine.", "Gua sha deflates morning puffiness."),
        ("Fact", "Astaxanthin is 6000x more powerful than Vitamin C as an antioxidant.\nOne of the best natural skin protectors.", "6000x stronger than Vitamin C."),
        ("Warning", "Exfoliating more than 2–3 times per week damages your skin barrier.\nOver-exfoliation causes sensitivity and breakouts.", "Less exfoliation is more."),
        ("Fact", "Collagen supplements actually work when combined with Vitamin C.\nStudies show measurable skin thickness improvement after 8 weeks.", "Collagen supplements need Vitamin C to work."),
    ],
    "heart": [
        ("Fact", "Heart disease kills 1 person every 36 seconds in the US.\nIt remains the #1 killer worldwide.", "Heart disease is the #1 killer worldwide."),
        ("Did You Know?", "Your heart beats 100,000 times per day.\nOver a lifetime, that's 2.5 billion beats.", "2.5 billion beats in a lifetime."),
        ("Tip", "Omega-3 fatty acids reduce triglycerides by up to 30%.\nAim for 2 servings of fatty fish per week.", "Fatty fish 2x a week protects your heart."),
        ("Warning", "Trans fats increase LDL AND decrease HDL — doubling your heart disease risk.\nCheck labels for 'partially hydrogenated oils'.", "Trans fats double your heart disease risk."),
        ("Statistic", "50% of heart attacks occur in people with normal cholesterol.\nInflammation, not just cholesterol, is the real risk factor.", "Half of heart attacks happen to 'healthy' people."),
        ("Fact", "Exercise reduces heart attack risk by 35% — more than most medications.\n150 minutes of moderate activity per week is the target.", "Exercise protects your heart better than pills."),
        ("Tip", "Dark chocolate (70%+) lowers blood pressure by 5 points.\n1–2 squares daily is therapeutic.", "Dark chocolate is heart medicine."),
        ("Warning", "Loneliness raises cortisol chronically, increasing heart disease risk by 29%.\nSocial connection is literally heart medicine.", "Loneliness is as dangerous as smoking."),
        ("Fact", "Magnesium deficiency is linked to 7x higher risk of sudden cardiac death.\nIt regulates heart rhythm and blood pressure.", "Magnesium protects heart rhythm."),
        ("Statistic", "People who sleep 6–8 hours have a 48% lower risk of heart disease.\nSleep is cardiovascular medicine.", "Sleep duration is a heart health factor."),
        ("Did You Know?", "Gum disease bacteria have been found in arterial plaques.\nYour dental hygiene affects your heart.", "Gum disease is a heart disease risk factor."),
        ("Tip", "Walking just 30 minutes per day reduces heart disease risk by 19%.\nYou don't need a gym — just consistency.", "30 minutes a day protects your heart."),
        ("Warning", "Energy drinks can trigger arrhythmias even in healthy young adults.\nCaffeine overload stresses your heart.", "Energy drinks are dangerous for your heart."),
        ("Fact", "CoQ10 is essential for heart muscle energy production.\nStatins deplete CoQ10 — supplement if you're on statins.", "If you're on statins, you need CoQ10."),
        ("Statistic", "Reducing sodium by just 1g per day lowers blood pressure by 5 mmHg.\nSmall dietary changes have measurable impact.", "Less salt = lower blood pressure."),
        ("Did You Know?", "Women's heart attack symptoms are often different from men's.\nNausea, jaw pain, and fatigue — not just chest pain.", "Women's heart attacks feel different."),
        ("Tip", "The DASH diet reduces blood pressure as effectively as medication in some people.\nFocus on fruits, vegetables, and whole grains.", "DASH diet = drug-free blood pressure control."),
        ("Fact", "Berberine lowers LDL cholesterol by up to 20% and reduces arterial inflammation.", "Berberine is nature's cholesterol medication."),
        ("Warning", "Chronic anger increases heart attack risk by 2–3x.\nAnger management is a serious cardiovascular intervention.", "Chronic anger is killing your heart."),
        ("Fact", "Olive oil's oleocanthal has the same anti-inflammatory mechanism as ibuprofen.\n3–4 tablespoons of extra virgin olive oil per day is therapeutic.", "Olive oil is nature's anti-inflammatory."),
    ],
    "male": [
        ("Fact", "Testosterone levels decline 1–2% every year after age 30.\nBy 50, most men have 30–40% less than their peak.", "You're losing 1-2% testosterone per year after 30."),
        ("Did You Know?", "Zinc is the most critical mineral for testosterone production.\nOne oyster contains your entire daily zinc requirement.", "One oyster covers your daily zinc needs."),
        ("Tip", "Heavy compound lifts (squats, deadlifts) trigger the highest testosterone release.\n3 sessions per week increases T levels by 20%.", "Compound lifts are testosterone boosters."),
        ("Statistic", "1 in 4 men over 40 have clinically low testosterone.\nLow T causes fatigue, depression, weight gain, and muscle loss.", "1 in 4 men over 40 have low testosterone."),
        ("Fact", "Ashwagandha (KSM-66) raises testosterone by 17% and reduces cortisol by 27% in trials.", "Ashwagandha is clinically proven to raise T."),
        ("Did You Know?", "Estrogen dominance in men is now epidemic due to plastics, pesticides, and processed foods.\nXenoestrogens suppress testosterone silently.", "Plastics are suppressing male hormones."),
        ("Tip", "Cold therapy raises testosterone and reduces inflammatory cortisol.\nCold showers directly affect hormone production.", "Cold showers boost testosterone."),
        ("Warning", "Alcohol reduces testosterone by up to 23% per session.\nEven moderate drinking affects hormone levels for 24 hours.", "Every drink lowers your testosterone."),
        ("Statistic", "40% of men over 40 have some degree of erectile dysfunction.\nCardiovascular health and ED share the same root causes.", "40% of men over 40 experience ED."),
        ("Did You Know?", "Morning erection is a health indicator.\nIts absence may signal low T or vascular issues.", "Morning erection = hormone health marker."),
        ("Tip", "Intermittent fasting increases testosterone by 180% in one 24-hour fast.\nFood timing powerfully affects male hormones.", "Fasting raises testosterone 180%."),
        ("Warning", "Soy contains phytoestrogens that can suppress testosterone in high amounts.\nLimit processed soy products.", "Soy can lower testosterone in men."),
        ("Statistic", "Men with high Vitamin D have 25% higher testosterone than deficient men.\nSunlight is literally a testosterone booster.", "Sunlight boosts testosterone by 25%."),
        ("Did You Know?", "Tongkat Ali reduces SHBG — a protein that binds testosterone and makes it unavailable.\nFree testosterone is what matters.", "Free testosterone is what actually counts."),
        ("Tip", "7–9 hours of sleep is when your body produces 70% of its daily testosterone.\nSleep debt = testosterone debt.", "Sleep debt is testosterone debt."),
        ("Fact", "Fenugreek extract increases free and total testosterone by blocking conversion to estrogen.", "Fenugreek raises free testosterone."),
        ("Warning", "Stress is the #1 testosterone killer in modern men.\nCortisol and testosterone are inversely related.", "Stress is the #1 testosterone killer."),
        ("Fact", "L-Citrulline boosts nitric oxide more effectively than L-Arginine supplements alone.", "L-Citrulline > L-Arginine for nitric oxide."),
        ("Did You Know?", "Your body's DHT causes prostate growth in older men but is critical for strength and vitality in younger men.", "DHT is a double-edged hormone."),
        ("Tip", "Magnesium reduces SHBG and increases free testosterone.\nMost men are deficient — supplement magnesium glycinate.", "Magnesium frees up your testosterone."),
    ],
    "blood": [
        ("Fact", "Over 100 million Americans have diabetes or prediabetes.\n90% of prediabetics don't know they have it.", "90% of prediabetics don't know it."),
        ("Did You Know?", "A single night of poor sleep makes cells 25% less responsive to insulin.\nSleep deprivation is a diabetes risk factor.", "One bad night of sleep causes insulin resistance."),
        ("Tip", "Apple cider vinegar before meals reduces post-meal blood sugar spikes by 20%.\nThe acetic acid slows carbohydrate digestion.", "ACV before meals lowers blood sugar."),
        ("Warning", "White bread spikes blood sugar as fast as pure table sugar.\nChoose whole grain alternatives.", "White bread is worse than you think."),
        ("Statistic", "Reversing prediabetes is possible in 70% of cases through diet and exercise alone.", "70% of prediabetes cases are reversible."),
        ("Fact", "Berberine activates AMPK — acting like a 'metabolic switch' — lowering blood sugar as effectively as metformin in studies.", "Berberine is as effective as metformin."),
        ("Did You Know?", "Muscle tissue is your body's largest glucose storage depot.\nBuilding muscle is the most powerful long-term blood sugar tool.", "Muscle is your body's blood sugar buffer."),
        ("Tip", "Cinnamon (Ceylon) reduces fasting blood glucose by 11–29% in studies.\n1/2 tsp daily is the effective dose.", "Ceylon cinnamon lowers blood sugar."),
        ("Warning", "Fruit juice concentrates sugar — a glass of OJ has the sugar of 4 oranges.\nEat the whole fruit.", "Fruit juice is sugar water."),
        ("Fact", "Chromium picolinate improves insulin sensitivity and reduces sugar cravings.\nDeficiency is common in Western diets.", "Chromium controls sugar cravings."),
        ("Statistic", "A 7% reduction in body weight reduces diabetes risk by 58% in high-risk individuals.", "Lose 7% of body weight → 58% less diabetes risk."),
        ("Did You Know?", "Stress causes the liver to dump glucose into the bloodstream, even without eating.\nEmotional stress directly raises blood sugar.", "Stress raises blood sugar without eating."),
        ("Tip", "A 10-minute walk after eating is one of the most effective ways to lower post-meal blood sugar.", "10 minutes of walking after meals changes everything."),
        ("Fact", "Magnesium is a cofactor in every step of insulin signaling.\nDeficiency = insulin resistance.", "Magnesium deficiency causes insulin resistance."),
        ("Warning", "Diet sodas alter gut bacteria in ways that impair glucose metabolism.", "Diet sodas are not safe for blood sugar."),
        ("Did You Know?", "Your gut bacteria regulate how you metabolize carbohydrates.\nThe same food causes different blood sugar responses in different people.", "Same food, different blood sugar responses."),
        ("Tip", "Resistant starch (cooked-then-cooled rice) reduces blood sugar impact by 30%.", "Cool your rice before eating it."),
        ("Fact", "Alpha-lipoic acid reduces fasting blood sugar and protects nerves damaged by high glucose.", "ALA protects nerves from blood sugar damage."),
        ("Statistic", "People who eat 5+ vegetable servings daily have 23% lower risk of type 2 diabetes.", "Vegetables cut diabetes risk by 23%."),
        ("Fact", "Intermittent fasting improves insulin sensitivity significantly within 2–4 weeks of consistent practice.", "Intermittent fasting resets insulin sensitivity."),
    ],
    "joint": [
        ("Fact", "Cartilage has no blood supply — it gets nutrients from movement.\nSitting still literally starves your joints.", "Move to feed your joints."),
        ("Did You Know?", "Your knees absorb 3–5x your body weight with every step.\nLosing 10 lbs reduces knee stress by 40–80 lbs.", "10 lbs off = 40-80 lbs less knee stress."),
        ("Tip", "Collagen type II supplementation reduces joint pain by 40% in 6 months.\nIt's the main structural protein in cartilage.", "Collagen II rebuilds your joints."),
        ("Warning", "NSAIDs (ibuprofen) mask pain but accelerate cartilage breakdown with long-term use.", "Ibuprofen is destroying your cartilage."),
        ("Statistic", "350 million people worldwide live with arthritis.\nInflammatory diet is the most modifiable risk factor.", "Diet is the #1 modifiable arthritis risk."),
        ("Fact", "Turmeric's curcumin is as effective as 800mg ibuprofen for osteoarthritis pain.\nCombine with black pepper for 2000% better absorption.", "Turmeric + black pepper = natural pain relief."),
        ("Did You Know?", "Your joints contain synovial fluid — nature's lubricant.\nDehydration reduces it and causes friction and pain.", "Dehydration causes joint pain."),
        ("Tip", "Swimming reduces body weight impact by 90%.\nStrength and cardio without stress on the joints.", "Swimming is the perfect joint exercise."),
        ("Warning", "High-sugar diets trigger AGEs (advanced glycation end products) that damage cartilage.", "Sugar is destroying your cartilage."),
        ("Fact", "Boswellic acids block the specific enzyme that causes joint inflammation\nwithout the side effects of NSAIDs.", "Boswellia: anti-inflammatory without side effects."),
        ("Statistic", "150 minutes of moderate exercise per week lowers arthritis progression rate by 46%.", "Exercise slows arthritis by 46%."),
        ("Tip", "Glucosamine + chondroitin together reduce joint pain as effectively as Celebrex for moderate osteoarthritis.", "Glucosamine + chondroitin beat prescription meds."),
        ("Warning", "Running on hard surfaces increases knee joint degeneration risk.\nAlternate with swimming or grass running.", "Hard surfaces destroy your knees."),
        ("Fact", "Omega-3s reduce the systemic inflammation that drives arthritis pain.\nFish oil at 2–3g EPA/DHA shows measurable joint benefits.", "Omega-3s fight arthritis inflammation."),
        ("Did You Know?", "Your gut microbiome is directly linked to rheumatoid arthritis.\nCertain bacteria trigger the immune attack on joint tissue.", "Gut bacteria cause joint inflammation."),
        ("Tip", "Anti-inflammatory diet: fatty fish, walnuts, olive oil, berries, dark leafy greens.", "The anti-inflammatory diet for joint pain."),
        ("Fact", "Vitamin K2 directs calcium into bones and away from joints and arteries.\nK2 deficiency causes calcification around joints.", "Vitamin K2 keeps calcium in your bones."),
        ("Statistic", "People who sleep poorly report 2x higher pain sensitivity.\nPoor sleep amplifies joint pain in the brain.", "Poor sleep doubles pain sensitivity."),
        ("Warning", "Stress causes cortisol spikes that directly increase joint inflammation.", "Chronic stress inflames your joints."),
        ("Did You Know?", "Cold weather doesn't damage joints — it makes surrounding tissue stiffen.\nWarm up longer in winter before exercise.", "Cold stiffens tissue, not joints."),
    ],
    "sleep": [
        ("Fact", "Chronic sleep deprivation has been classified as a public health epidemic by the CDC.", "America has a sleep crisis."),
        ("Did You Know?", "Your body temperature must drop 1–2°F to fall asleep.\nA cool bedroom (65–68°F) is biological, not optional.", "Cool room = better sleep. Science explains why."),
        ("Tip", "Blue light from screens suppresses melatonin by up to 50%.\nStop screens 90 minutes before bed.", "Stop screens 90 minutes before bed."),
        ("Warning", "Alcohol ruins sleep quality even when it helps you fall asleep.\nIt suppresses REM — the most restorative stage.", "Alcohol kills your REM sleep."),
        ("Statistic", "People who sleep 7–9 hours live significantly longer than those who sleep less than 6.", "Sleep duration = lifespan."),
        ("Fact", "Magnesium glycinate relaxes the nervous system and increases GABA — your brain's 'off switch'.", "Magnesium glycinate = natural off switch for your brain."),
        ("Did You Know?", "During deep sleep, your brain flushes toxic waste — including amyloid plaques linked to Alzheimer's.", "Sleep is your brain's self-cleaning cycle."),
        ("Tip", "A consistent WAKE time is more important than a consistent bedtime.\nYour circadian rhythm anchors on wake time.", "Focus on your wake time, not bedtime."),
        ("Warning", "Naps longer than 30 minutes cause 'sleep inertia' and disrupt nighttime sleep.", "Keep naps under 30 minutes."),
        ("Fact", "Ashwagandha reduces cortisol by 27% and improves sleep quality scores by 72% in trials.", "Ashwagandha dramatically improves sleep quality."),
        ("Statistic", "Insomnia increases depression risk by 10x and anxiety risk by 17x.", "Insomnia causes depression and anxiety."),
        ("Tip", "L-theanine promotes relaxation without sedation.\nIt increases alpha brain waves — the same state as meditation.", "L-theanine: calm focus without drowsiness."),
        ("Warning", "Caffeine has a 5–7 hour half-life.\nA 3pm coffee still has 50% caffeine in your system at 9pm.", "Your 3pm coffee is still active at 9pm."),
        ("Fact", "Valerian root increases GABA, reducing sleep onset time by an average of 15 minutes.", "Valerian root = fall asleep 15 minutes faster."),
        ("Did You Know?", "Sleeping on your left side improves lymphatic drainage and reduces acid reflux.", "Left-side sleeping has real health benefits."),
        ("Tip", "5-HTP converts to serotonin, which converts to melatonin.\nAddressing the full chain works better than melatonin alone.", "5-HTP targets sleep at the source."),
        ("Statistic", "People with sleep apnea are 3x more likely to have a car accident.\n80% of cases go undiagnosed.", "80% of sleep apnea cases go undiagnosed."),
        ("Warning", "Melatonin supplements are 80% unregulated — many contain 400% more than labeled.\n0.3–1mg is effective; high doses disrupt natural production.", "Most melatonin supplements are overdosed."),
        ("Fact", "Exercise improves sleep quality by 65% — but avoid exercise 3+ hours before bed.", "Exercise is the best sleep supplement."),
        ("Did You Know?", "Your mattress should be replaced every 7–10 years.\nA poor mattress contributes to both back pain and poor sleep.", "Replace your mattress every 7-10 years."),
    ],
    "womens": [
        ("Fact", "70% of bladder leakage in women is caused by weakened pelvic floor muscles — and 85% respond to targeted exercises.", "Bladder leakage is often fixable with exercise."),
        ("Did You Know?", "Estrogen decline after 40 affects the bladder lining and urethra directly.\nHormonal changes cause 40% of urinary symptoms.", "Menopause directly affects your bladder."),
        ("Tip", "Kegel exercises done correctly reduce urinary leakage by up to 70%.\nTighten, hold 5 seconds, release — 3 sets of 10 daily.", "Kegels done right reduce leakage by 70%."),
        ("Warning", "Caffeine and alcohol irritate the bladder directly.\nReducing coffee to 1 cup per day improves urgency in 60% of women.", "Coffee directly irritates your bladder."),
        ("Statistic", "1 in 3 women over 45 experience some form of urinary incontinence.", "It's common — but not inevitable."),
        ("Fact", "D-Mannose prevents UTI-causing bacteria from adhering to the bladder wall.\nAs effective as antibiotics for uncomplicated UTIs in some studies.", "D-Mannose is nature's antibiotic for UTIs."),
        ("Did You Know?", "Estrogen and progesterone influence brain chemistry, bone density, cardiovascular health, and immune function.", "Your hormones control far more than reproduction."),
        ("Tip", "Pumpkin seed extract reduces overactive bladder symptoms by 40%.\nClinically studied for both frequency and urgency.", "Pumpkin seed extract calms an overactive bladder."),
        ("Fact", "Vitamin D deficiency is linked to overactive bladder and pelvic floor weakness.", "Vitamin D deficiency weakens your pelvic floor."),
        ("Statistic", "Women experience anxiety and depression at 2x the rate of men.\nHormonal fluctuations directly affect serotonin and GABA.", "Hormones drive women's mood disorders."),
        ("Did You Know?", "Cranberry PACs are the active compounds that prevent UTIs.\nJuice has too little — look for supplements with 36mg PAC daily.", "Cranberry juice is too diluted to work."),
        ("Tip", "Magnesium glycinate reduces PMS symptoms — cramps, mood swings, water retention — better than NSAIDs in some studies.", "Magnesium reduces PMS better than ibuprofen."),
        ("Warning", "Synthetic fragrance in feminine hygiene products disrupts vaginal pH and microbiome balance.", "Fragrance in feminine products is harmful."),
        ("Fact", "Probiotics with Lactobacillus strains protect vaginal microbiome and reduce recurrent UTIs by 50%.", "Probiotics cut UTI recurrence in half."),
        ("Statistic", "1 in 2 women over 50 will experience a bone fracture due to osteoporosis.\nThe window to build bone density closes in your 30s.", "Build bone density in your 30s or lose it."),
        ("Did You Know?", "The pelvic floor contains 3 layers of muscles supporting the uterus, bladder, and rectum.\nPregnancy, childbirth, and menopause all weaken these critical muscles.", "Your pelvic floor has 3 critical muscle layers."),
        ("Tip", "Reducing sodium to under 1500mg/day reduces water retention and bloating from hormonal shifts.", "Less sodium = less hormonal bloating."),
        ("Fact", "Saffron extract is as effective as low-dose Prozac for mild-to-moderate depression in women, without the sexual side effects.", "Saffron works as well as antidepressants."),
        ("Warning", "Hormonal birth control depletes B vitamins, zinc, magnesium, and CoQ10.\nSupplement these nutrients if you're on the pill.", "The pill depletes critical nutrients."),
        ("Fact", "High-impact exercise worsens stress incontinence without pelvic floor strengthening first.", "Strengthen pelvic floor before high-impact exercise."),
    ],
    "general": [
        ("Fact", "The gut contains 70% of the immune system.\nWhat you eat directly determines how well your body fights infection.", "Your gut IS your immune system."),
        ("Did You Know?", "Your body has 37 trillion cells — replaced within 7–15 years.\nYou are literally building yourself with what you eat.", "You replace yourself every 7-15 years."),
        ("Tip", "Walking 7,000–10,000 steps per day reduces all-cause mortality by 53%.\nNo gym required.", "7,000 steps/day cuts death risk by 53%."),
        ("Warning", "Chronic inflammation is the underlying driver of cancer, heart disease, diabetes, and Alzheimer's.\nYour lifestyle either inflames or protects.", "Inflammation drives every major disease."),
        ("Statistic", "Only 12% of Americans are considered metabolically healthy.", "88% of Americans have metabolic problems."),
        ("Fact", "Fasting for 16+ hours activates autophagy — your body's cellular recycling and repair system.", "Fasting activates your body's self-repair."),
        ("Tip", "Sunlight in the morning sets your circadian rhythm and boosts serotonin.\n10–15 minutes outside within 1 hour of waking.", "Morning sunlight is the best free health hack."),
        ("Warning", "Most Americans are deficient in Vitamin D, magnesium, Omega-3, and zinc.", "The 4 nutrients most Americans are missing."),
        ("Fact", "The liver processes over 500 functions — detoxification, hormone regulation, and cholesterol production.", "Your liver does 500 things — protect it."),
        ("Statistic", "People with strong social connections live an average of 7 years longer.", "Loneliness shortens your life by 7 years."),
        ("Tip", "Deep breathing for 5 minutes activates the vagus nerve and switches your nervous system to 'rest-and-digest'.", "5 minutes of deep breathing resets your nervous system."),
        ("Warning", "Processed foods contain endocrine disruptors that disrupt hormone function.\nEat whole foods at least 80% of the time.", "Processed food disrupts your hormones."),
        ("Fact", "Zinc is required for over 300 enzymatic reactions in the human body.", "Zinc is involved in 300 body processes."),
        ("Statistic", "People who meditate regularly have telomeres 10% longer than non-meditators.\nLonger telomeres = slower biological aging.", "Meditation slows aging at the cellular level."),
        ("Tip", "Cold + heat contrast therapy boosts growth hormone by 200–300% and improves cardiovascular resilience.", "Sauna + cold plunge = 300% growth hormone boost."),
        ("Fact", "Olive oil's oleocanthal has the same anti-inflammatory mechanism as ibuprofen.\n3–4 tablespoons of EVOO per day is therapeutic.", "Olive oil is ibuprofen in food form."),
        ("Warning", "Chronic stress shrinks the hippocampus, suppresses immunity, and accelerates aging at the cellular level.", "Chronic stress ages every cell in your body."),
        ("Did You Know?", "Laughter literally boosts NK cells that fight cancer and viruses.\nHumor is immune medicine.", "Laughter boosts your cancer-fighting cells."),
        ("Fact", "Fasting for 24 hours triggers stem cell regeneration in the immune system.\nYour body can rebuild its immune defense.", "One 24-hour fast regenerates your immune system."),
        ("Tip", "Gratitude practice increases activity in the prefrontal cortex and reduces the amygdala's fear response.", "Gratitude physically rewires your brain."),
    ],
}

# ── Image generation ──────────────────────────────────────────────────────────

def make_ig_image(cat_key, headline, body, cta):
    from PIL import Image, ImageDraw, ImageFont
    import textwrap

    W, H = 1080, 1350
    accent = CATEGORIES[cat_key]["accent"]
    cat_name = CATEGORIES[cat_key]["name"]

    img = Image.new("RGB", (W, H), (12, 12, 16))
    draw = ImageDraw.Draw(img)

    # Top accent bar
    draw.rectangle([0, 0, W, 10], fill=accent)

    # Background decorative circles
    for cx, cy, r, a in [(950, 250, 300, 0.06), (-80, 1150, 350, 0.05), (540, 675, 700, 0.025)]:
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(accent[0], accent[1], accent[2], int(255 * a)))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

    BOLD = [
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    REG = [
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]

    def _f(paths, size):
        for p in paths:
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
        return ImageFont.load_default()

    f_badge = _f(BOLD, 28)
    f_head  = _f(BOLD, 72)
    f_body  = _f(REG,  44)
    f_cta   = _f(BOLD, 34)
    f_url   = _f(BOLD, 30)
    f_sub   = _f(REG,  26)

    # Category badge
    badge = cat_name.upper()
    bb = draw.textbbox((0, 0), badge, font=f_badge)
    bw, bh = bb[2]-bb[0]+40, bb[3]-bb[1]+18
    draw.rounded_rectangle([60, 46, 60+bw, 46+bh], radius=bh//2, fill=accent)
    draw.text((80, 46 + (bh-(bb[3]-bb[1]))//2 - bb[1]), badge, fill=(255,255,255), font=f_badge)

    # Headline type label
    type_y = 46 + bh + 32
    tb = draw.textbbox((0,0), headline, font=f_badge)
    tw, th = tb[2]-tb[0]+32, tb[3]-tb[1]+12
    draw.rounded_rectangle([60, type_y, 60+tw, type_y+th], radius=6, fill=(accent[0]//3, accent[1]//3, accent[2]//3))
    draw.text((76, type_y + 6 - tb[1]), headline, fill=accent, font=f_badge)

    # Separator
    sep_y = type_y + th + 24
    draw.rectangle([60, sep_y, W-60, sep_y+3], fill=(accent[0]//4, accent[1]//4, accent[2]//4))

    # Body text
    body_y = sep_y + 50
    lines_all = []
    for para in body.split("\n"):
        para = para.strip()
        if not para:
            lines_all.append("")
            continue
        lines_all.extend(textwrap.wrap(para, width=26))
        lines_all.append("")
    while lines_all and lines_all[-1] == "":
        lines_all.pop()

    mid_top, mid_bot = body_y, 1060
    lh = 64
    total_h = len(lines_all) * lh
    text_y = mid_top + max(0, (mid_bot - mid_top - total_h) // 2)

    first_line = lines_all[0] if lines_all else ""
    rest = lines_all[1:]

    fb = draw.textbbox((0,0), first_line, font=f_head)
    x_first = max(60, (W - (fb[2]-fb[0])) // 2)
    draw.text((x_first, text_y - fb[1]), first_line, fill=(255,255,255), font=f_head)

    cur_y = text_y + 98
    for line in rest:
        if not line:
            cur_y += 28
            continue
        lb = draw.textbbox((0,0), line, font=f_body)
        x = max(60, (W - (lb[2]-lb[0])) // 2)
        draw.text((x, cur_y - lb[1]), line, fill=(200, 200, 210), font=f_body)
        cur_y += lh

    # CTA box
    cta_y = 1080
    draw.rounded_rectangle([60, cta_y, W-60, cta_y+68], radius=12, fill=(accent[0]//5, accent[1]//5, accent[2]//5), outline=accent, width=2)
    cb = draw.textbbox((0,0), cta, font=f_cta)
    draw.text(((W-(cb[2]-cb[0]))//2, cta_y+18-cb[1]), cta, fill=accent, font=f_cta)

    # Footer
    draw.rectangle([0, 1178, W, 1350], fill=(18, 18, 24))
    draw.rectangle([0, 1178, W, 1182], fill=accent)

    url_text = "reviews.thehappy-healthy-life.com"
    ub = draw.textbbox((0,0), url_text, font=f_url)
    draw.text(((W-(ub[2]-ub[0]))//2, 1202-ub[1]), url_text, fill=(255,255,255), font=f_url)

    sub_text = "Full supplement reviews  •  Link in bio"
    sb = draw.textbbox((0,0), sub_text, font=f_sub)
    draw.text(((W-(sb[2]-sb[0]))//2, 1255-sb[1]), sub_text, fill=(120,120,135), font=f_sub)

    draw.rectangle([0, 1342, W, 1350], fill=accent)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95, optimize=True)
    return buf.getvalue()


# ── Image file management ─────────────────────────────────────────────────────

def save_image(img_bytes, filename):
    """Save generated image to ig_content/ folder (archive only)."""
    os.makedirs(CONTENT_DIR, exist_ok=True)
    path = os.path.join(CONTENT_DIR, filename)
    with open(path, "wb") as f:
        f.write(img_bytes)
    return path

def get_github_raw_url(filename):
    """Return raw.githubusercontent.com URL from the PUBLIC ig-assets repo."""
    return f"https://raw.githubusercontent.com/{ASSETS_REPO}/master/ig_content/{filename}"


def wait_for_url(url, max_wait=90, interval=10):
    """Poll url until it returns HTTP 200 or max_wait seconds elapse. Returns True if accessible."""
    import urllib.request
    import urllib.error
    elapsed = 0
    while elapsed < max_wait:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(interval)
        elapsed += interval
    return False


# ── Instagram API ──────────────────────────────────────────────────────────────

def publish_ig_image(image_url, caption):
    import requests
    create_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    payload = {"image_url": image_url, "caption": caption, "access_token": IG_TOKEN}
    for attempt in range(3):
        try:
            r = requests.post(create_url, data=payload, timeout=30)
            if r.status_code != 200:
                log(f"  Create erreur {r.status_code}: {r.text[:200]}")
                time.sleep(5)
                continue
            creation_id = r.json().get("id")
            if not creation_id:
                return 0, {"error": "no creation_id"}
            time.sleep(8)
            r2 = requests.post(
                f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish",
                data={"creation_id": creation_id, "access_token": IG_TOKEN},
                timeout=30,
            )
            return r2.status_code, r2.json()
        except Exception as e:
            log(f"  publish erreur tentative {attempt+1}: {e}")
            time.sleep(5)
    return 0, {"error": "echec apres 3 tentatives"}


# ── Caption builder ───────────────────────────────────────────────────────────

def make_caption(cat_key, headline, body, cta, hashtags):
    cat_name = CATEGORIES[cat_key]["name"]
    body_clean = body.replace("\n", " ")
    save_cta = random.choice([
        "Save this post to remember it later!",
        "Save this! You'll want to read it again.",
        "Bookmark this post — share it with someone who needs it.",
    ])
    follow_cta = random.choice([
        "Follow for daily health tips.",
        "Follow us for more research-backed health content.",
        "Follow to learn something new about your health every day.",
    ])
    cat_url = CATEGORIES[cat_key]["cat_url"]
    bio_cta = f"Full reviews & guides: {SITE_URL}/{cat_url}/ (link in bio)"

    return f"""{headline}: {body_clean}

{cta}

{save_cta}

{follow_cta}

{bio_cta}

.
.
.
{hashtags} #HealthFacts #WellnessTips #NaturalHealth #HealthyLiving #SupplementReviews"""


# ── Logging & state ───────────────────────────────────────────────────────────

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
        with open(DONE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_done(done):
    with open(DONE_FILE, "w") as f:
        json.dump(done, f, indent=2)

def load_idx():
    try:
        with open(POST_IDX_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"cat_idx": 0, "content_idx": {}}

def save_idx(state):
    with open(POST_IDX_FILE, "w") as f:
        json.dump(state, f, indent=2)

import random

# keep `random` alias for existing caption helpers that use random.choice
# ── Reel helpers ──────────────────────────────────────────────────────────────

def get_github_reels_url(filename):
    return f"https://raw.githubusercontent.com/{ASSETS_REPO}/master/ig_reels/{filename}"




def load_reel_idx():
    try:
        with open(REEL_IDX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"idx": 0}


def save_reel_idx(state):
    with open(REEL_IDX_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def make_reel_caption(product_name, cat_slug, slug):
    review_url = f"{SITE_URL}/{cat_slug}/{slug}/"
    return (
        f"Honest review of {product_name}\n\n"
        f"Does it really work? We break down the ingredients, benefits, and real results.\n\n"
        f"Full review: {review_url}\n\n"
        f"#HealthSupplements #SupplementReview #NaturalHealth #HonestReview #HealthTips "
        f"#WellnessReview #HealthReview #SupplementFacts"
    )


def publish_ig_reel(video_url, caption):
    """Publish a Reel via Instagram Graph API. Returns (status_code, response_json)."""
    import requests

    IG_API = f"https://graph.facebook.com/v19.0/{IG_USER_ID}"

    r = requests.post(
        f"{IG_API}/media",
        params={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": IG_TOKEN,
        },
        timeout=60,
    )
    if r.status_code != 200:
        return r.status_code, r.json()

    container_id = r.json().get("id")
    if not container_id:
        return r.status_code, r.json()

    log(f"    Reel container: {container_id}")

    for _ in range(30):
        time.sleep(10)
        pr = requests.get(
            f"https://graph.facebook.com/v19.0/{container_id}",
            params={"fields": "status_code", "access_token": IG_TOKEN},
            timeout=30,
        )
        if pr.status_code == 200:
            status = pr.json().get("status_code", "")
            log(f"    Reel status: {status}")
            if status == "FINISHED":
                break
            if status == "ERROR":
                return 500, {"error": "Reel container processing failed"}

    pub = requests.post(
        f"{IG_API}/media_publish",
        params={"creation_id": container_id, "access_token": IG_TOKEN},
        timeout=60,
    )
    return pub.status_code, pub.json()


# ── Main ──────────────────────────────────────────────────────────────────────

def generate_phase():
    """Phase 1: Generate images and save pending list. Run before git commit."""
    tz_tunis = timezone(timedelta(hours=1))
    today_key = datetime.now(timezone.utc).astimezone(tz_tunis).strftime("%Y-%m-%d")

    done = load_done()
    if done.get(today_key):
        log(f"Instagram deja publie pour {today_key} — skip generate")
        sys.exit(0)

    state = load_idx()
    cat_idx = state.get("cat_idx", 0)
    content_idx = state.get("content_idx", {})

    log(f"=== Instagram Generate Phase {today_key} ({POSTS_PER_DAY} images) ===")

    pending = []
    for i in range(POSTS_PER_DAY):
        cat_key = CAT_ROTATION[cat_idx % len(CAT_ROTATION)]
        cat_idx += 1

        items = CONTENT[cat_key]
        cidx = content_idx.get(cat_key, 0) % len(items)
        content_idx[cat_key] = cidx + 1

        headline, body, cta = items[cidx]
        hashtags = CATEGORIES[cat_key]["hashtags"]
        filename = f"{today_key}_{i+1}.jpg"

        log(f"  [{i+1}/{POSTS_PER_DAY}] {CATEGORIES[cat_key]['name']} — {headline}")

        public_url = None
        try:
            img_bytes = make_ig_image(cat_key, headline, body, cta)
            save_image(img_bytes, filename)
            log(f"    Saved: ig_content/{filename}")
            public_url = get_github_raw_url(filename)
            log(f"    URL: {public_url}")
        except Exception as e:
            log(f"    Image generation failed: {e}")
            filename = None

        pending.append({
            "filename": filename,
            "public_url": public_url,
            "cat_key": cat_key,
            "headline": headline,
            "body": body,
            "cta": cta,
            "hashtags": hashtags,
        })

    state["cat_idx"] = cat_idx
    state["content_idx"] = content_idx
    save_idx(state)

    with open(PENDING_FILE, "w") as f:
        json.dump({"date": today_key, "posts": pending}, f, indent=2)

    # Generate Reel video dynamically with Pexels + edge-tts + FFmpeg
    reel_products = load_all_products()
    if reel_products:
        r_state = load_reel_idx()
        r_idx = r_state.get("idx", 0) % len(reel_products)
        product = reel_products[r_idx]
        r_state["idx"] = r_idx + 1
        save_reel_idx(r_state)

        cat_slug     = product["category_slug"]
        reel_filename = f"{today_key}.mp4"
        reels_dir    = os.path.join(BASE_DIR, "ig_reels")
        os.makedirs(reels_dir, exist_ok=True)
        reel_path    = os.path.join(reels_dir, reel_filename)
        generated_ok = False

        if PEXELS_API_KEY:
            try:
                queries   = PEXELS_QUERIES.get(cat_slug, ["healthy lifestyle woman"])
                query     = _random.choice(queries)
                log(f"Reel [{product['name']}]: Pexels search '{query}'")
                video_url = pexels_search_video(query, PEXELS_API_KEY)
                if video_url:
                    with tempfile.TemporaryDirectory() as tmp:
                        raw_path   = os.path.join(tmp, "raw.mp4")
                        audio_path = os.path.join(tmp, "audio.mp3")
                        download_video(video_url, raw_path)
                        size_kb = os.path.getsize(raw_path) // 1024
                        log(f"  downloaded {size_kb}KB")
                        log(f"  generating voiceover (edge-tts)...")
                        make_reel_voiceover(product, audio_path)
                        log(f"  processing FFmpeg overlay...")
                        process_reel_video(raw_path, audio_path, reel_path, product)
                        generated_ok = os.path.exists(reel_path)
                        if generated_ok:
                            log(f"  reel video {reel_filename} {os.path.getsize(reel_path)//1024}KB OK")
                else:
                    log("  Pexels: no video found")
            except Exception as e:
                log(f"  Reel generation error: {e}")
        else:
            log("  PEXELS_API_KEY not set — skipping reel video generation")

        with open(REEL_PENDING_FILE, "w") as f:
            json.dump({
                "date": today_key,
                "slug": product["slug"],
                "name": product["name"],
                "category_slug": cat_slug,
                "mp4_filename": reel_filename,
                "generated": generated_ok,
            }, f, indent=2)
        log(f"Reel pending: {product['name']} generated={generated_ok}")

    log(f"=== Generate done: {len([p for p in pending if p['filename']])} images saved ===")


def publish_phase():
    """Phase 2: Publish images using GitHub raw URLs. Run after git commit+push."""
    if not IG_TOKEN or not IG_USER_ID:
        log("ERREUR: INSTAGRAM_ACCESS_TOKEN ou INSTAGRAM_USER_ID non defini")
        sys.exit(1)

    tz_tunis = timezone(timedelta(hours=1))
    today_key = datetime.now(timezone.utc).astimezone(tz_tunis).strftime("%Y-%m-%d")

    done = load_done()
    if done.get(today_key):
        log(f"Instagram deja publie pour {today_key}")
        sys.exit(0)

    # Load pending list written by generate phase
    try:
        with open(PENDING_FILE, "r") as f:
            pending_data = json.load(f)
    except Exception:
        log("ERREUR: ig_pending.json introuvable — lancer --generate d'abord")
        sys.exit(1)

    if pending_data.get("date") != today_key:
        log(f"ERREUR: ig_pending.json est pour {pending_data.get('date')}, pas {today_key}")
        sys.exit(1)

    log(f"=== Instagram Publish Phase {today_key} ===")

    published = 0
    errors = 0

    for i, post in enumerate(pending_data["posts"]):
        img_url = post.get("public_url")
        if not img_url:
            log(f"  [{i+1}] SKIP — pas d'URL publique (tmpfiles.org upload a echoue au generate)")
            errors += 1
            continue

        log(f"  [{i+1}] {CATEGORIES[post['cat_key']]['name']} — {post['headline']}")
        log(f"    URL: {img_url}")

        # Verify the image is accessible on GitHub CDN before sending to Instagram
        log(f"    Vérification CDN...")
        if not wait_for_url(img_url, max_wait=90, interval=10):
            log(f"    ERREUR: URL inaccessible après 90s — skip")
            errors += 1
            continue
        log(f"    CDN OK — publication...")

        caption = make_caption(post["cat_key"], post["headline"], post["body"], post["cta"], post["hashtags"])

        status, resp = publish_ig_image(img_url, caption)
        if status == 200:
            log(f"    OK post_id={resp.get('id','?')}")
            published += 1
        else:
            log(f"    ERREUR {status}: {resp}")
            errors += 1

        if i < len(pending_data["posts"]) - 1:
            time.sleep(15)

    done[today_key] = {
        "published": published,
        "errors": errors,
        "at": datetime.utcnow().isoformat(),
    }
    save_done(done)
    log(f"=== Termine: {published} publies | {errors} erreurs ===")


REEL_DONE_FILE = os.path.join(BASE_DIR, "ig_reel_done.json")


def publish_reel_phase():
    """Publish today's Reel independently — can run even when images are already published."""
    if not IG_TOKEN or not IG_USER_ID:
        log("ERREUR: INSTAGRAM_ACCESS_TOKEN ou INSTAGRAM_USER_ID non defini")
        sys.exit(1)

    tz_tunis = timezone(timedelta(hours=1))
    today_key = datetime.now(timezone.utc).astimezone(tz_tunis).strftime("%Y-%m-%d")

    try:
        with open(REEL_DONE_FILE, "r") as f:
            reel_done = json.load(f)
    except Exception:
        reel_done = {}

    if reel_done.get(today_key):
        log(f"Instagram Reel deja publie pour {today_key}")
        sys.exit(0)

    if not os.path.exists(REEL_PENDING_FILE):
        log("ERREUR: ig_reel_pending.json introuvable — lancer --generate d'abord")
        sys.exit(1)

    with open(REEL_PENDING_FILE, "r") as f:
        reel_data = json.load(f)

    if reel_data.get("date") != today_key:
        log(f"ERREUR: ig_reel_pending.json est pour {reel_data.get('date')}, pas {today_key}")
        sys.exit(1)

    video_url = get_github_reels_url(reel_data["mp4_filename"])
    caption = make_reel_caption(reel_data["name"], reel_data["category_slug"], reel_data["slug"])

    log(f"=== Publishing Reel: {reel_data['name']} ===")
    log(f"  URL: {video_url}")

    reel_status, reel_resp = publish_ig_reel(video_url, caption)
    if reel_status == 200:
        log(f"  Reel OK id={reel_resp.get('id', '?')}")
        reel_done[today_key] = {"id": reel_resp.get("id"), "at": datetime.utcnow().isoformat()}
        with open(REEL_DONE_FILE, "w") as f:
            json.dump(reel_done, f, indent=2)
    else:
        log(f"  Reel ERREUR {reel_status}: {reel_resp}")
        sys.exit(1)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--publish"
    try:
        if mode == "--generate":
            generate_phase()
        elif mode == "--publish-reel":
            publish_reel_phase()
        else:
            publish_phase()
    except Exception:
        log(f"EXCEPTION:\n{traceback.format_exc()}")
        sys.exit(1)
