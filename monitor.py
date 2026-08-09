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
    "nasa",
    "cnn",
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
        data={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": False},
        timeout=30,
    )
    response.raise_for_status()


def fetch_account_with_playwright(page, account):
    url = f"https://www.sotwe.com/{account}?lang=en"
    print(f"Checking @{account} ...")

    # 改用 domcontentloaded,不要等 networkidle(可能永遠不會靜止)
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    try:
        page.wait_for_selector("a[href*='/status/']", timeout=20000)
    except Exception as e:
        print(f"  WARNING: no /status/ link appeared within timeout: {e}")

    html = page.content()
    print(f"  HTML length: {len(html)}")

    # 一律存檔方便看,workflow 會上傳成 artifact
    with open(f"debug_{account}.html", "w", encoding="utf-8") as f:
        f.write(html)

    soup = BeautifulSoup(html, "html.parser")
    status_links = soup.find_all("a", href=lambda h: h and "/status/" in h)
    print(f"  Found {len(status_links)} status links")

    seen_urls = set()
    videos = []
    for link in status_links:
        href = link["href"]
        tweet_url = "https://x.com" + href if href.startswith("/") else href
        if tweet_url in seen_urls:
            continue
        seen_urls.add(tweet_url)

        container = link
        for _ in range(6):
            if container.parent is None:
                break
            container = container.parent
            if len(container.get_text(strip=True)) > 20:
                break

        text = container.get_text(" ", strip=True)
        raw = account.lower() + "|" + tweet_url
        video_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        videos.append({
            "id": video_id,
            "account": account,
            "url": tweet_url,
            "text": text[:200],
        })

    return videos


def main():
    seen = load_seen()
    first_run = not bool(seen) or all(len(v) == 0 for v in seen.values())
    print(f"first_run = {first_run}")

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
                    if video["id"] not in seen[account]:
                        seen[account].append(video["id"])
                        if not first_run:
                            new_videos.append(video)
            except Exception as e:
                print(f"ERROR @{account}: {type(e).__name__}: {e}")

        browser.close()

    for account in seen:
        seen[account] = seen[account][-200:]

    save_seen(seen)
    print("seen.json content:", json.dumps(seen, ensure_ascii=False))

    if first_run:
        total = sum(len(v) for v in seen.values())
        send_telegram(f"🤖 Monitor 初始化完成！目前已記錄 {total} 個項目。")
        return

    if new_videos:
        for video in new_videos:
            link = video["url"] or f"https://x.com/{video['account']}"
            send_telegram(f"🎬 發現新貼文！\n\n帳號：@{video['account']}\n\n🔗 {link}")
    else:
        print("No new items.")


if __name__ == "__main__":
    main()