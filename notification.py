import requests
import json
import logging
import os

def send_discord_message(content):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")

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
    # color: green(info), red(warning), blue(trade)
    if color == "red":
        prefix = "[WARNING] "
    elif color == "blue":
        prefix = "[TRADE] "
    else:
        prefix = "[INFO] "

    content = f"**{prefix}{title}**\n{message}"
    send_discord_message(content)