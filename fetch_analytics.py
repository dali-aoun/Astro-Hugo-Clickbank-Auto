"""
Fetch analytics metrics from Pinterest, Instagram, and YouTube.
Run via GitHub Actions to access secrets.
"""
import urllib.request, urllib.error, json, os, sys
from datetime import datetime, timedelta

PINTEREST_TOKEN = os.environ.get("PINTEREST_ACCESS_TOKEN", "")
INSTAGRAM_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_USER_ID = os.environ.get("INSTAGRAM_USER_ID", "")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN", "")
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID", "")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", "")

TODAY = datetime.utcnow().strftime("%Y-%m-%d")
START_30 = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
START_7  = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")


def _get(url, token=None, extra_headers=None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if extra_headers:
        for k, v in extra_headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code}: {body[:300]}")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def _post(url, data):
    payload = json.dumps(data).encode()
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  Error: {e}")
        return None


# ── PINTEREST ─────────────────────────────────────────────────────────────────
def pinterest_metrics():
    print("\n========== PINTEREST ==========")
    if not PINTEREST_TOKEN:
        print("  PINTEREST_ACCESS_TOKEN manquant"); return

    # Account overview
    acct = _get("https://api.pinterest.com/v5/user_account", PINTEREST_TOKEN)
    if acct:
        print(f"  Username   : {acct.get('username', '?')}")
        print(f"  Followers  : {acct.get('follower_count', '?')}")
        print(f"  Following  : {acct.get('following_count', '?')}")
        print(f"  Pin count  : {acct.get('pin_count', '?')}")
        print(f"  Board count: {acct.get('board_count', '?')}")

    # Account analytics (last 30 days)
    metrics = "IMPRESSION,OUTBOUND_CLICK,SAVE,PIN_CLICK,TOTAL_AUDIENCE,ENGAGED_AUDIENCE"
    url = (
        f"https://api.pinterest.com/v5/user_account/analytics"
        f"?start_date={START_30}&end_date={TODAY}"
        f"&metric_types={metrics}"
    )
    data = _get(url, PINTEREST_TOKEN)
    if data and "all" in data:
        s = data["all"].get("summary_metrics", {})
        print(f"\n  --- 30 derniers jours ---")
        print(f"  Impressions      : {s.get('IMPRESSION', '?'):,}")
        print(f"  Pin clicks       : {s.get('PIN_CLICK', '?'):,}")
        print(f"  Outbound clicks  : {s.get('OUTBOUND_CLICK', '?'):,}")
        print(f"  Saves            : {s.get('SAVE', '?'):,}")
        print(f"  Total audience   : {s.get('TOTAL_AUDIENCE', '?'):,}")
        print(f"  Engaged audience : {s.get('ENGAGED_AUDIENCE', '?'):,}")
    elif data:
        print(f"  Raw: {json.dumps(data)[:500]}")

    # Last 7 days
    url7 = (
        f"https://api.pinterest.com/v5/user_account/analytics"
        f"?start_date={START_7}&end_date={TODAY}"
        f"&metric_types={metrics}"
    )
    d7 = _get(url7, PINTEREST_TOKEN)
    if d7 and "all" in d7:
        s7 = d7["all"].get("summary_metrics", {})
        print(f"\n  --- 7 derniers jours ---")
        print(f"  Impressions      : {s7.get('IMPRESSION', '?'):,}")
        print(f"  Pin clicks       : {s7.get('PIN_CLICK', '?'):,}")
        print(f"  Outbound clicks  : {s7.get('OUTBOUND_CLICK', '?'):,}")
        print(f"  Saves            : {s7.get('SAVE', '?'):,}")


# ── INSTAGRAM ─────────────────────────────────────────────────────────────────
def instagram_metrics():
    print("\n========== INSTAGRAM ==========")
    if not INSTAGRAM_TOKEN or not INSTAGRAM_USER_ID:
        print("  Token/UserID manquant"); return

    # Account info
    url = (
        f"https://graph.facebook.com/v19.0/{INSTAGRAM_USER_ID}"
        f"?fields=username,name,followers_count,follows_count,media_count,biography"
        f"&access_token={INSTAGRAM_TOKEN}"
    )
    acct = _get(url)
    if acct:
        print(f"  Username    : @{acct.get('username', '?')}")
        print(f"  Followers   : {acct.get('followers_count', '?')}")
        print(f"  Following   : {acct.get('follows_count', '?')}")
        print(f"  Posts total : {acct.get('media_count', '?')}")

    # Account insights (last 30 days)
    metrics = "reach,impressions,profile_views,website_clicks,accounts_engaged"
    url_ins = (
        f"https://graph.facebook.com/v19.0/{INSTAGRAM_USER_ID}/insights"
        f"?metric={metrics}&period=days_28"
        f"&access_token={INSTAGRAM_TOKEN}"
    )
    ins = _get(url_ins)
    if ins and "data" in ins:
        print(f"\n  --- 28 derniers jours ---")
        for m in ins["data"]:
            name = m.get("name", "?")
            val = m.get("values", [{}])
            total = sum(v.get("value", 0) for v in val)
            print(f"  {name:<22}: {total:,}")
    elif ins:
        print(f"  Raw: {json.dumps(ins)[:500]}")

    # Recent media performance
    url_media = (
        f"https://graph.facebook.com/v19.0/{INSTAGRAM_USER_ID}/media"
        f"?fields=id,media_type,timestamp,like_count,comments_count"
        f"&limit=10&access_token={INSTAGRAM_TOKEN}"
    )
    media = _get(url_media)
    if media and "data" in media:
        print(f"\n  --- 10 derniers posts ---")
        for m in media["data"]:
            ts = m.get("timestamp", "?")[:10]
            mtype = m.get("media_type", "?")
            likes = m.get("like_count", 0)
            comments = m.get("comments_count", 0)
            print(f"  {ts} [{mtype:<8}] ❤ {likes:>4}  💬 {comments}")


# ── YOUTUBE ───────────────────────────────────────────────────────────────────
def youtube_get_access_token():
    if not (YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN):
        return None
    url = "https://oauth2.googleapis.com/token"
    payload = (
        f"client_id={YT_CLIENT_ID}&client_secret={YT_CLIENT_SECRET}"
        f"&refresh_token={YT_REFRESH_TOKEN}&grant_type=refresh_token"
    ).encode()
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()).get("access_token")
    except Exception as e:
        print(f"  YT token error: {e}")
        return None


def youtube_metrics():
    print("\n========== YOUTUBE ==========")
    token = youtube_get_access_token()
    if not token:
        print("  Impossible d'obtenir le token YouTube"); return

    # Channel info
    url = "https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true"
    ch = _get(url, token)
    if ch and ch.get("items"):
        item = ch["items"][0]
        stats = item.get("statistics", {})
        snippet = item.get("snippet", {})
        print(f"  Channel     : {snippet.get('title', '?')}")
        print(f"  Subscribers : {stats.get('subscriberCount', '?')}")
        print(f"  Total views : {stats.get('viewCount', '?')}")
        print(f"  Videos      : {stats.get('videoCount', '?')}")

    # Channel analytics (last 30 days) via YouTube Analytics API
    ch_id_data = _get("https://www.googleapis.com/youtube/v3/channels?part=id&mine=true", token)
    if not ch_id_data or not ch_id_data.get("items"):
        print("  Channel ID introuvable"); return
    ch_id = ch_id_data["items"][0]["id"]

    url_analytics = (
        f"https://youtubeanalytics.googleapis.com/v2/reports"
        f"?ids=channel=={ch_id}"
        f"&startDate={START_30}&endDate={TODAY}"
        f"&metrics=views,estimatedMinutesWatched,averageViewDuration,likes,comments,shares,subscribersGained"
        f"&dimensions=day&sort=day"
    )
    an = _get(url_analytics, token)
    if an and "rows" in an:
        rows = an["rows"]
        totals = [0] * len(an.get("columnHeaders", []))
        for row in rows:
            for i, val in enumerate(row):
                if i > 0:
                    totals[i] += val
        headers = [h["name"] for h in an.get("columnHeaders", [])]
        print(f"\n  --- 30 derniers jours ---")
        for i, h in enumerate(headers):
            if i > 0:
                print(f"  {h:<35}: {int(totals[i]):,}")
    elif an:
        print(f"  Raw: {json.dumps(an)[:500]}")

    # Recent videos
    url_vids = (
        f"https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&forMine=true&type=video&maxResults=10"
        f"&order=date"
    )
    vids = _get(url_vids, token)
    if vids and vids.get("items"):
        vid_ids = ",".join(v["id"]["videoId"] for v in vids["items"] if "videoId" in v.get("id", {}))
        if vid_ids:
            url_stats = f"https://www.googleapis.com/youtube/v3/videos?part=statistics,snippet&id={vid_ids}"
            vstats = _get(url_stats, token)
            if vstats and vstats.get("items"):
                print(f"\n  --- 10 dernières vidéos ---")
                for v in vstats["items"]:
                    title = v["snippet"]["title"][:40]
                    s = v.get("statistics", {})
                    views = s.get("viewCount", 0)
                    likes = s.get("likeCount", 0)
                    pub = v["snippet"]["publishedAt"][:10]
                    print(f"  {pub} | {int(views):>6} views | ❤ {int(likes):>4} | {title}")


if __name__ == "__main__":
    print(f"Analytics Report — {TODAY}")
    print("=" * 50)
    pinterest_metrics()
    instagram_metrics()
    youtube_metrics()
    print("\n========== FIN ==========")
