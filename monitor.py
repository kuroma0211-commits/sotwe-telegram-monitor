import os
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

ACCOUNTS = [
    "AZINABUER",
    "byst1522",
    "wqingqinovo",
]

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text,
        },
        timeout=30,
    )

    response.raise_for_status()


def main():
    message = (
        "🤖 Sotwe Monitor 測試成功！\n\n"
        "目前監控帳號：\n"
        + "\n".join(f"• {account}" for account in ACCOUNTS)
    )

    send_telegram(message)


if __name__ == "__main__":
    main()
