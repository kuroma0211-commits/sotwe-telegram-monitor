import os
import json
import hashlib
import time
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# 換成你要監控的一般帳號 (例如新聞媒體、公開資訊帳號)
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
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )
    response.raise_for_status()


def fetch_account_with_playwright(page, account, debug=False):
    url = f"https://www.sotwe.com/{account}?lang=en"
    print(f"Checking @{account} via Playwright...")

    page.goto(url, wait_until="networkidle", timeout=60000)
    time.sleep(3)

    html = page.content()

    if debug:
        # 除錯用: 把實際抓到的 HTML 存下來檢查真正的 class 結構
        with open(f"debug_{account}.html", "w", encoding="utf-8") as f:
            f.write(html)

    soup = BeautifulSoup(html, "html.parser")

    # 改用更穩健的方式: 找所有含 /status/ 連結的 <a>,
    # 往上找到該推文的容器區塊(通常是它的祖先 article 或 div)
    status_links = soup.find_all("a", href=lambda h: h and "/status/" in h)

    seen_urls = set()
    videos = []
    for link in status_links:
        href = link["href"]
        tweet_url = "https://x.com" + href if href.startswith("/") else href
        if tweet_url in seen_urls:
            continue
        seen_urls.add(tweet_url)

        # 往上找一個看起來像卡片容器的父層(有多個子元素、包含文字)
        container = link
        for _ in range(6):
            if container.parent is None:
                break
            container = container.parent
            if len(container.get_text(strip=True)) > 20:
                break

        text = container.get_text(" ", strip=True)
        media_urls = []
        for video in container.find_all("video"):
            if video.get("src"):
                media_urls.append(video["src"])
            for source in video.find_all("source"):
                if source.get("src"):
                    media_urls.append(source["src"])
        for img in container.find_all("img"):
            if img.get("src"):
                media_urls.append(img["src"])

        raw = account.lower() + "|" + tweet_url
        video_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        videos.append({
            "id": video_id,
            "account": account,
            "url": tweet_url,
            "text": text[:200],
        })

    print(f"  Found {len(videos)} tweet items")
    return videos


def main():
    seen = load_seen()
    first_run = not bool(seen) or all(len(v) == 0 for v in seen.values())

    if first_run:
        print("First run - building baseline.")
    else:
        print("Checking for new items...")

    new_videos = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        for account in ACCOUNTS:
            try:
                # 第一次先開 debug=True 存 HTML 檢查結構,確認後可關掉
                videos = fetch_account_with_playwright(page, account, debug=True)
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
            "之後只會通知新項目。"
        )
        send_telegram(message)
        print(message)
        return

    if new_videos:
        for video in new_videos:
            account = video["account"]
            link = video["url"] or f"https://x.com/{account}"
            message = (
                "🎬 發現新貼文！\n\n"
                f"帳號：@{account}\n\n"
                f"🔗 {link}"
            )
            send_telegram(message)
            print(f"NEW ITEM @{account}: {link}")
    else:
        print("No new items.")


if __name__ == "__main__":
    main()