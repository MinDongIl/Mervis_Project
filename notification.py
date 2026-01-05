import requests
import json
import logging
import secret

def send_discord_message(content):
    webhook_url = getattr(secret, 'DISCORD_WEBHOOK_URL', '')

    if not webhook_url:
        logging.warning("Discord webhook URL is missing.")
        return

    data = {
        "content": content,
        "username": "Mervis"
    }

    try:
        response = requests.post(webhook_url, json=data)
        if response.status_code != 204:
            logging.error(f"Failed to send Discord message: {response.status_code} {response.text}")
    except Exception as e:
        logging.error(f"Discord notification error: {e}")

def send_alert(title, message, color="green"):
    # 간단한 알림용 (추후 확장 가능)
    # color: green(정보), red(경고/에러), blue(매매) 등 구분 가능하나 현재는 텍스트 위주
    
    icon = "" # 이모티콘 제거됨
    if color == "red":
        prefix = "[WARNING] "
    elif color == "blue":
        prefix = "[TRADE] "
    else:
        prefix = "[INFO] "

    content = f"**{prefix}{title}**\n{message}"
    send_discord_message(content)