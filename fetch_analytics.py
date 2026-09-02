"""
Fetch analytics metrics from Pinterest, Instagram, and YouTube.
Run via GitHub Actions to access secrets.
"""
import urllib.request, urllib.error, json, os
from datetime import datetime, timedelta, timezone

PINTEREST_TOKEN   = os.environ.get("PINTEREST_ACCESS_TOKEN", "")
INSTAGRAM_TOKEN   = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_USER_ID = os.environ.get("INSTAGRAM_USER_ID", "")
YT_REFRESH_TOKEN  = os.environ.get("YT_REFRESH_TOKEN", "")
YT_CLIENT_ID      = os.environ.get("YT_CLIENT_ID", "")
YT_CLIENT_SECRET  = os.environ.get("YT_CLIENT_SECRET", "")

_now     = datetime.now(timezone.utc)
TODAY    = _now.strftime("%Y-%m-%d")
START_30 = (_now - timedelta(days=30)).strftime("%Y-%m-%d")
START_7  = (_now - timedelta(days=7)).strftime("%Y-%m-%d")


def _get(url, token=None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code}: {body[:400]}")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def _post_form(url, data):
    payload = data.encode()
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  Error: {e}")
        return None


# ── PINTEREST ─────────────────────────────────────────────────────────────────
# Valid metric_types: ENGAGEMENT, ENGAGEMENT_RATE, IMPRESSION,
#   OUTBOUND_CLICK, OUTBOUND_CLICK_RATE, PIN_CLICK, PIN_CLICK_RATE, SAVE, SAVE_RATE
def pinterest_metrics():
    print("\n========== PINTEREST ==========")
    if not PINTEREST_TOKEN:
        print("  PINTEREST_ACCESS_TOKEN manquant"); return

    acct = _get("https://api.pinterest.com/v5/user_account", PINTEREST_TOKEN)
    if acct:
        print(f"  Username    : {acct.get('username', '?')}")
        print(f"  Followers   : {acct.get('follower_count', '?'):,}")
        print(f"  Pins        : {acct.get('pin_count', '?'):,}")
        print(f"  Boards      : {acct.get('board_count', '?')}")

    metrics = "IMPRESSION,OUTBOUND_CLICK,OUTBOUND_CLICK_RATE,PIN_CLICK,PIN_CLICK_RATE,SAVE,SAVE_RATE,ENGAGEMENT,ENGAGEMENT_RATE"

    for label, start in [("30 derniers jours", START_30), ("7 derniers jours", START_7)]:
        url = (
            f"https://api.pinterest.com/v5/user_account/analytics"
            f"?start_date={start}&end_date={TODAY}"
            f"&metric_types={metrics}"
        )
        data = _get(url, PINTEREST_TOKEN)
        if data and "all" in data:
            s = data["all"].get("summary_metrics", {})
            print(f"\n  --- {label} ---")
            print(f"  Impressions        : {int(s.get('IMPRESSION', 0)):>10,}")
            print(f"  Pin clicks         : {int(s.get('PIN_CLICK', 0)):>10,}")
            print(f"  Pin click rate     : {s.get('PIN_CLICK_RATE', 0):.4f}")
            print(f"  Outbound clicks    : {int(s.get('OUTBOUND_CLICK', 0)):>10,}")
            print(f"  Outbound CTR       : {s.get('OUTBOUND_CLICK_RATE', 0):.4f}")
            print(f"  Saves              : {int(s.get('SAVE', 0)):>10,}")
            print(f"  Save rate          : {s.get('SAVE_RATE', 0):.4f}")
            print(f"  Engagement         : {int(s.get('ENGAGEMENT', 0)):>10,}")
            print(f"  Engagement rate    : {s.get('ENGAGEMENT_RATE', 0):.4f}")
        elif data:
            print(f"  [{label}] Raw: {json.dumps(data)[:300]}")

    # Top 5 pins by impressions
    pins_url = (
        f"https://api.pinterest.com/v5/user_account/analytics/top_pins"
        f"?start_date={START_30}&end_date={TODAY}"
        f"&metric_types=IMPRESSION,OUTBOUND_CLICK,SAVE&num_of_pins=5"
    )
    pins = _get(pins_url, PINTEREST_TOKEN)
    if pins and "pins" in pins:
        print(f"\n  --- Top 5 pins (30j, par impressions) ---")
        for p in pins["pins"]:
            m = p.get("metrics", {})
            title = (p.get("title") or "?")[:35]
            print(f"  {title:<36} | imp:{int(m.get('IMPRESSION',0)):>6,} clicks:{int(m.get('OUTBOUND_CLICK',0)):>5,} saves:{int(m.get('SAVE',0)):>5,}")


# ── INSTAGRAM ─────────────────────────────────────────────────────────────────
def instagram_metrics():
    print("\n========== INSTAGRAM ==========")
    if not INSTAGRAM_TOKEN or not INSTAGRAM_USER_ID:
        print("  Token/UserID manquant"); return

    # Account info
    url = (
        f"https://graph.facebook.com/v19.0/{INSTAGRAM_USER_ID}"
        f"?fields=username,followers_count,follows_count,media_count"
        f"&access_token={INSTAGRAM_TOKEN}"
    )
    acct = _get(url)
    if acct:
        print(f"  Username    : @{acct.get('username', '?')}")
        print(f"  Followers   : {acct.get('followers_count', 0):,}")
        print(f"  Following   : {acct.get('follows_count', 0):,}")
        print(f"  Posts total : {acct.get('media_count', 0):,}")

    # Insights — try multiple metric sets (permissions vary by app mode)
    # Set 1: reach + impressions (requires instagram_manage_insights OR basic scope)
    tried = False
    for metric_set, period in [
        ("reach,impressions,profile_views", "day"),
        ("reach,impressions", "day"),
        ("follower_count", "day"),
    ]:
        url_ins = (
            f"https://graph.facebook.com/v19.0/{INSTAGRAM_USER_ID}/insights"
            f"?metric={metric_set}&period={period}&since={START_30}&until={TODAY}"
            f"&access_token={INSTAGRAM_TOKEN}"
        )
        ins = _get(url_ins)
        if ins and "data" in ins:
            print(f"\n  --- Insights ({metric_set}) ---")
            for m in ins["data"]:
                name = m.get("name", "?")
                vals = m.get("values", [])
                total = sum(v.get("value", 0) for v in vals)
                print(f"  {name:<22}: {total:,}")
            tried = True
            break

    if not tried:
        print("  Insights: permission instagram_manage_insights requise")
        print("  → Activer Live mode sur app Meta + demander la permission")

    # Media performance (always works with basic access)
    url_media = (
        f"https://graph.facebook.com/v19.0/{INSTAGRAM_USER_ID}/media"
        f"?fields=id,media_type,timestamp,like_count,comments_count,permalink"
        f"&limit=20&access_token={INSTAGRAM_TOKEN}"
    )
    media = _get(url_media)
    if media and "data" in media:
        posts = media["data"]
        total_likes    = sum(p.get("like_count", 0) for p in posts)
        total_comments = sum(p.get("comments_count", 0) for p in posts)
        reels  = [p for p in posts if p.get("media_type") == "VIDEO"]
        images = [p for p in posts if p.get("media_type") == "IMAGE"]
        print(f"\n  --- 20 derniers posts ---")
        print(f"  Reels   : {len(reels)}")
        print(f"  Images  : {len(images)}")
        print(f"  Total likes    : {total_likes}")
        print(f"  Total comments : {total_comments}")
        print(f"\n  Post detail (date | type | ❤ likes | 💬 comments)")
        for p in posts:
            ts   = p.get("timestamp", "?")[:10]
            mt   = p.get("media_type", "?")[:5]
            lk   = p.get("like_count", 0)
            cm   = p.get("comments_count", 0)
            print(f"    {ts} [{mt:<5}] ❤ {lk:>3}  💬 {cm}")


# ── YOUTUBE ───────────────────────────────────────────────────────────────────
def _yt_access_token():
    if not (YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN):
        return None
    data = (
        f"client_id={YT_CLIENT_ID}&client_secret={YT_CLIENT_SECRET}"
        f"&refresh_token={YT_REFRESH_TOKEN}&grant_type=refresh_token"
    )
    res = _post_form("https://oauth2.googleapis.com/token", data)
    return res.get("access_token") if res else None


def youtube_metrics():
    print("\n========== YOUTUBE ==========")
    token = _yt_access_token()
    if not token:
        print("  Impossible d'obtenir le token YouTube"); return

    # Channel info
    ch = _get("https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true", token)
    ch_id = None
    if ch and ch.get("items"):
        item  = ch["items"][0]
        stats = item.get("statistics", {})
        ch_id = item["id"]
        print(f"  Channel     : {item['snippet'].get('title', '?')}")
        print(f"  Subscribers : {int(stats.get('subscriberCount', 0)):,}")
        print(f"  Total views : {int(stats.get('viewCount', 0)):,}")
        print(f"  Videos      : {int(stats.get('videoCount', 0)):,}")

    # YouTube Analytics API — try; if 403 (API not enabled) print instructions
    if ch_id:
        url_an = (
            f"https://youtubeanalytics.googleapis.com/v2/reports"
            f"?ids=channel=={ch_id}"
            f"&startDate={START_30}&endDate={TODAY}"
            f"&metrics=views,estimatedMinutesWatched,averageViewDuration,likes,comments,shares,subscribersGained"
        )
        an = _get(url_an, token)
        if an and "rows" in an:
            headers = [h["name"] for h in an.get("columnHeaders", [])]
            totals  = [0.0] * len(headers)
            for row in an["rows"]:
                for i, v in enumerate(row):
                    totals[i] += float(v)
            print(f"\n  --- Analytics 30 derniers jours ---")
            for i, h in enumerate(headers):
                print(f"  {h:<35}: {int(totals[i]):,}")
        elif an is None:
            print("\n  YouTube Analytics API non activée.")
            print("  → Activer ici : https://console.developers.google.com/apis/api/youtubeanalytics.googleapis.com/overview?project=277499395894")

    # Recent 10 videos — always works
    vids = _get(
        "https://www.googleapis.com/youtube/v3/search"
        "?part=snippet&forMine=true&type=video&maxResults=10&order=date",
        token
    )
    if vids and vids.get("items"):
        vid_ids = ",".join(
            v["id"]["videoId"] for v in vids["items"] if "videoId" in v.get("id", {})
        )
        if vid_ids:
            vstats = _get(
                f"https://www.googleapis.com/youtube/v3/videos?part=statistics,snippet&id={vid_ids}",
                token
            )
            if vstats and vstats.get("items"):
                total_views = sum(int(v.get("statistics", {}).get("viewCount", 0)) for v in vstats["items"])
                total_likes = sum(int(v.get("statistics", {}).get("likeCount", 0)) for v in vstats["items"])
                print(f"\n  --- 10 dernières vidéos ---")
                print(f"  Total vues  (10 vids) : {total_views:,}")
                print(f"  Total likes (10 vids) : {total_likes:,}")
                print()
                for v in vstats["items"]:
                    title = v["snippet"]["title"][:45]
                    s     = v.get("statistics", {})
                    views = int(s.get("viewCount", 0))
                    likes = int(s.get("likeCount", 0))
                    pub   = v["snippet"]["publishedAt"][:10]
                    print(f"  {pub} | {views:>5} views | ❤ {likes:>3} | {title}")


if __name__ == "__main__":
    print(f"Analytics Report — {TODAY}")
    print("=" * 60)
    pinterest_metrics()
    instagram_metrics()
    youtube_metrics()
    print("\n========== FIN ==========")
