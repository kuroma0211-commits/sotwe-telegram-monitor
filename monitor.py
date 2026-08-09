import os
import json
import hashlib
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

ACCOUNTS = [
    "AZINABUER",
    "byst1522",
    "wqinginovo",
]

STATE_FILE = "seen.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    )
}


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
    """
    嘗試從 Sotwe 的 tweet card 找出原始 X/Twitter 貼文網址。
    """

    for a in card.find_all("a", href=True):
        href = a["href"]

        if "/status/" in href:
            if href.startswith("/"):
                return "https://x.com" + href

            if href.startswith("http"):
                return href

    return None


def get_media_urls(card):
    """
    找出影片/圖片的媒體網址，拿來建立穩定的影片 ID。
    """

    urls = []

    # video src
    for video in card.find_all("video"):
        src = video.get("src")
        if src:
            urls.append(src)

        for source in video.find_all("source"):
            src = source.get("src")
            if src:
                urls.append(src)

    # img src
    for img in card.find_all("img"):
        src = img.get("src")
        if src:
            urls.append(src)

    return sorted(set(urls))


def make_video_id(account, card):
    """
    優先使用媒體網址建立影片 ID。
    如果找不到媒體網址，就使用 tweet card 的文字建立 ID。
    """

    media_urls = get_media_urls(card)

    text = card.get_text(" ", strip=True)

    if media_urls:
        raw = account.lower() + "|" + "|".join(media_urls)
    else:
        raw = account.lower() + "|" + text

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def is_own_video(card, account):
    """
    只抓帳號自己的影片，不抓轉推的影片。
    """

    text = card.get_text(" ", strip=True)

    # 轉推排除
    if "retweeted" in text.lower():
        return False

    # Sotwe 通常會顯示：
    # AZINABUER's tweet video.
    account_lower = account.lower()

    if f"{account_lower}'s tweet video." in text.lower():
        return True

    # 有些帳號名稱可能大小寫不同
    if "tweet video." in text.lower():
        return account_lower in text.lower()

    return False


def fetch_account(account):
    url = f"https://www.sotwe.com/{account}?lang=en"

    print(f"Checking @{account} ...")

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    cards = soup.select(".tweet-card")

    print(f"  Found {len(cards)} tweet cards")

    videos = []

    for card in cards:

        if not is_own_video(card, account):
            continue

        video_id = make_video_id(account, card)

        tweet_url = get_tweet_url(card)

        text = card.get_text(" ", strip=True)

        videos.append({
            "id": video_id,
            "account": account,
            "url": tweet_url,
            "text": text,
        })

    return videos


def main():

    seen = load_seen()

    # 第一次執行
    first_run = not bool(seen)

    if first_run:
        print("First run - building baseline.")
    else:
        print("Checking for new videos...")

    new_videos = []

    for account in ACCOUNTS:

        try:
            videos = fetch_account(account)

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

    # 限制 seen.json 不要無限膨脹
    for account in seen:
        seen[account] = seen[account][-200:]

    save_seen(seen)

    # 第一次執行
    if first_run:
        total = sum(len(v) for v in seen.values())

        message = (
            "🤖 Sotwe Monitor 初始化完成！\n\n"
            f"目前已記錄 {total} 個影片。\n\n"
            "之後只會通知新的影片。"
        )

        send_telegram(message)

        print(message)
        return

    # 新影片
    if new_videos:

        for video in new_videos:

            account = video["account"]
            tweet_url = video["url"]

            if tweet_url:
                link = tweet_url
            else:
                link = f"https://x.com/{account}"

            message = (
                "🎬 發現新影片！\n\n"
                f"帳號：@{account}\n\n"
                f"🔗 {link}"
            )

            send_telegram(message)

            print(
                f"NEW VIDEO @{account}: {link}"
            )

    else:
        print("No new videos.")


if __name__ == "__main__":
    main()
