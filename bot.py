import os
import json
import re
import logging
import time
import datetime
import threading
from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
APP_LEVEL_TOKEN = os.getenv("APP_LEVEL_TOKEN")

client = WebClient(token=SLACK_BOT_TOKEN)
socket_client = SocketModeClient(app_token=APP_LEVEL_TOKEN, web_client=client)

CONFIG_FILE = "daily_post.json"
TEMP_FILE = "daily_post_temp.json"
last_posted_date = None

def save_temp(data):
    with open(TEMP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_temp():
    if not os.path.exists(TEMP_FILE):
        return None
    with open(TEMP_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def clear_temp():
    if os.path.exists(TEMP_FILE):
        os.remove(TEMP_FILE)

def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def clear_config():
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_channel_id(text: str) -> str | None:
    m = re.search(r"<#([A-Z0-9]+)(\|[^>]*)?>", text)
    if m:
        return m.group(1)
    return None

def get_channel_id(channel_name: str) -> str | None:
    if channel_name.startswith("#"):
        channel_name = channel_name[1:]
    try:
        result = client.conversations_list(types="public_channel,private_channel")
        for ch in result["channels"]:
            if ch["name"] == channel_name:
                return ch["id"]
    except Exception as e:
        logging.error(f"チャンネルリスト取得エラー: {e}")
    return None

def handle_command(text: str, event_channel: str):
    if text.startswith("!毎日投稿停止"):
        clear_config()
        clear_temp()
        client.chat_postMessage(channel=event_channel, text="✅ 毎日投稿を停止しました。")

    elif text.startswith("!毎日投稿設定"):
        parts = text.split(" ", 2)
        if len(parts) < 3:
            client.chat_postMessage(channel=event_channel, text="❌ 使用方法: `!毎日投稿設定 HH:MM #channel`")
            return

        time_str, channel_input = parts[1], parts[2].strip()
        channel_id = extract_channel_id(channel_input)
        if not channel_id:
            if channel_input.startswith("#"):
                channel_id = get_channel_id(channel_input[1:])
            else:
                client.chat_postMessage(channel=event_channel, text="❌ チャンネル指定が不正です。")
                return

        if not channel_id:
            client.chat_postMessage(channel=event_channel, text=f"❌ チャンネル `{channel_input}` が見つかりません。")
            return

        save_temp({"time": time_str, "channel_id": channel_id})
        client.chat_postMessage(channel=event_channel, text="✅ 投稿時間とチャンネルを設定しました。\n続けて `!毎日投稿内容 メッセージ内容` を送信してください。")

    elif text.startswith("!毎日投稿内容"):
        temp = load_temp()
        if not temp:
            client.chat_postMessage(channel=event_channel, text="⚠️ 先に `!毎日投稿設定` を使用してください。")
            return

        message = text[len("!毎日投稿内容 "):].strip()
        if not message:
            client.chat_postMessage(channel=event_channel, text="❌ 投稿内容が空です。")
            return

        config = {
            "time": temp["time"],
            "channel_id": temp["channel_id"],
            "message": message
        }
        save_config(config)
        clear_temp()
        client.chat_postMessage(
            channel=event_channel,
            text=f"✅ 毎日 `{config['time']}` にチャンネルID `{config['channel_id']}` へ以下の内容を投稿します。\n---\n{message}"
        )

@socket_client.socket_mode_request_listeners.append
def handle_events(client: SocketModeClient, req: SocketModeRequest):
    logging.info(f"イベント受信タイプ: {req.type}")
    logging.info(f"ペイロード内容: {json.dumps(req.payload, ensure_ascii=False, indent=2)}")

    if req.type == "events_api":
        event = req.payload.get("event", {})
        if event.get("type") == "message" and "bot_id" not in event:
            handle_command(event.get("text", ""), event.get("channel"))
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

def check_and_post():
    global last_posted_date

    config = load_config()
    if not config:
        return

    now = datetime.datetime.now()
    current_time = now.strftime("%H:%M")

    if last_posted_date != now.date() and current_time == config["time"]:
        try:
            client.chat_postMessage(
                channel=config["channel_id"],
                text=config["message"]
            )
            last_posted_date = now.date()
            logging.info(f"✅ 投稿完了: {now}")
        except Exception as e:
            logging.error(f"投稿エラー: {e}")

def start_posting_loop():
    def loop():
        while True:
            check_and_post()
            time.sleep(30)
    t = threading.Thread(target=loop)
    t.daemon = True
    t.start()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    socket_client.connect()
    start_posting_loop()
    print("Bot 起動中...")
    while True:
        time.sleep(1)
