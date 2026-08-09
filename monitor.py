import os
import json
import hashlib
import time
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

ACCOUNTS = [
    "AZINABUER",
    "byst1522",
    "wqinginovo",
]

STATE_FILE = "seen.json"

def load_seen():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_seen(seen):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )
    response.raise_for_status()

def get_tweet_url(card):
    for a in card.find_all("a", href=True):
        href = a["href"]
        if "/status/" in href:
            if href.startswith("/"):
                return "https://x.com" + href
            if href.startswith("http"):
                return href
    return None

def get_media_urls(card):
    urls = []
    for video in card.find_all("video"):
        src = video.get("src")
        if src:
            urls.append(src)
        for source in video.find_all("source"):
            src = source.get("src")
            if src:
                urls.append(src)
    for img in card.find_all("img"):
        src = img.get("src")
        if src:
            urls.append(src)
    return sorted(set(urls))

def make_video_id(account, card):
    media_urls = get_media_urls(card)
    text = card.get_text(" ", strip=True)
    if media_urls:
        raw = account.lower() + "|" + "|".join(media_urls)
    else:
        raw = account.lower() + "|" + text
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def fetch_account_with_playwright(page, account):
    url = f"https://www.sotwe.com/{account}?lang=en"
    print(f"Checking @{account} via Playwright...")
    
    page.goto(url, wait_until="networkidle", timeout=60000)
    time.sleep(3)  # 等待 DOM 完全渲染
    
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    
    cards = soup.select(".tweet-card")
    if not cards:
        cards = soup.find_all("div", class_=lambda c: c and "tweet" in c.lower())

    print(f"  Found {len(cards)} tweet cards")

    videos = []
    for card in cards:
        text = card.get_text(" ", strip=True)
        if "retweeted" in text.lower():
            continue
        
        # 只要包含媒體或推文連結就納入紀錄
        video_id = make_video_id(account, card)
        tweet_url = get_tweet_url(card)
        
        videos.append({
            "id": video_id,
            "account": account,
            "url": tweet_url,
            "text": text,
        })

    return videos

def main():
    seen = load_seen()
    first_run = not bool(seen) or all(len(v) == 0 for v in seen.values())

    if first_run:
        print("First run - building baseline.")
    else:
        print("Checking for new videos...")

    new_videos = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        for account in ACCOUNTS:
            try:
                videos = fetch_account_with_playwright(page, account)
                if account not in seen:
                    seen[account] = []

                for video in videos:
                    video_id = video["id"]
                    if video_id not in seen[account]:
                        seen[account].append(video_id)
                        if not first_run:
                            new_videos.append(video)
            except Exception as e:
                print(f"ERROR @{account}: {e}")

        browser.close()

    for account in seen:
        seen[account] = seen[account][-200:]

    save_seen(seen)

    if first_run:
        total = sum(len(v) for v in seen.values())
        message = (
            "🤖 Sotwe Monitor 初始化完成！\n\n"
            f"目前已記錄 {total} 個項目。\n\n"
            "之後只會通知新影片/貼文。"
        )
        send_telegram(message)
        print(message)
        return

    if new_videos:
        for video in new_videos:
            account = video["account"]
            tweet_url = video["url"]
            link = tweet_url if tweet_url else f"https://x.com/{account}"
            message = (
                "🎬 發現新影片/貼文！\n\n"
                f"帳號：@{account}\n\n"
                f"🔗 {link}"
            )
            send_telegram(message)
            print(f"NEW ITEM @{account}: {link}")
    else:
        print("No new items.")

if __name__ == "__main__":
    main()
