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

def load_all_configs():
    if not os.path.exists(CONFIG_FILE):
        return []
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_all_configs(configs):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(configs, f, ensure_ascii=False, indent=2)

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

def extract_channel_id(text: str) -> str | None:
    m = re.search(r"<#([A-Z0-9]+)(\|[^>]*)?>", text)
    return m.group(1) if m else None

def extract_channel_id_from_blocks(blocks) -> str | None:
    for block in blocks:
        for element in block.get("elements", []):
            if element.get("type") == "rich_text_section":
                for sub in element.get("elements", []):
                    if sub.get("type") == "channel":
                        return sub.get("channel_id")
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

def parse_fixed_interval(time_str: str, freq_str: str) -> tuple[int, int | None]:
    if not re.match(r"^\d{2}:\d{2}$", time_str):
        return None, None
    h, m = map(int, time_str.split(":"))
    fixed_time = h * 3600 + m * 60

    m2 = re.match(r"^(\d+)d$", freq_str)
    if m2:
        n = int(m2.group(1))
        if n <= 0:
            return None, None
        interval = n * 86400
        return interval, fixed_time
    return None, None

def handle_command(text: str, event_channel: str, blocks=None):
    if text.startswith("!投稿設定"):
        parts = text.split(" ", 3)
        if len(parts) < 4:
            client.chat_postMessage(channel=event_channel, text="❌ 使用方法: `!投稿設定 HH:MM 3d #チャンネル名`")
            return

        time_str, freq_str, channel_input = parts[1], parts[2], parts[3]
        interval, fixed_time = parse_fixed_interval(time_str, freq_str)
        if interval is None:
            client.chat_postMessage(channel=event_channel, text="❌ 時刻または頻度の指定が不正です。")
            return

        channel_id = extract_channel_id(text) or extract_channel_id_from_blocks(blocks or []) or get_channel_id(channel_input)
        if not channel_id:
            client.chat_postMessage(channel=event_channel, text="❌ チャンネルが見つかりません。")
            return

        save_temp({
            "interval": interval,
            "fixed_time": fixed_time,
            "channel_id": channel_id
        })
        client.chat_postMessage(channel=event_channel, text="✅ 投稿時刻とチャンネルを設定しました。\n続けて `!投稿内容 メッセージ内容` を送ってください。")

    elif text.startswith("!投稿内容"):
        temp = load_temp()
        if not temp:
            client.chat_postMessage(channel=event_channel, text="⚠️ `!投稿設定` を先に実行してください。")
            return

        message = text[len("!投稿内容 "):].strip()
        if not message:
            client.chat_postMessage(channel=event_channel, text="❌ メッセージが空です。")
            return

        temp["message"] = message
        configs = load_all_configs()
        configs = [cfg for cfg in configs if cfg["message"] != message]
        configs.append(temp)
        save_all_configs(configs)
        clear_temp()

        client.chat_postMessage(channel=event_channel, text=f"✅ 登録完了: {message}")

    elif text.startswith("!投稿停止"):
        message = text[len("!投稿停止 "):].strip()
        configs = load_all_configs()
        new_configs = [cfg for cfg in configs if cfg["message"] != message]
        if len(new_configs) == len(configs):
            client.chat_postMessage(channel=event_channel, text="⚠️ 指定されたメッセージの設定は見つかりませんでした。")
        else:
            save_all_configs(new_configs)
            client.chat_postMessage(channel=event_channel, text=f"✅ 投稿停止完了: {message}")

    elif text.startswith("!投稿一覧"):
        configs = load_all_configs()
        if not configs:
            client.chat_postMessage(channel=event_channel, text="ℹ️ 登録された投稿はありません。")
        else:
            messages = [f"- {cfg['message']} ({cfg['interval']//86400}日おき)" for cfg in configs]
            client.chat_postMessage(channel=event_channel, text="📋 登録投稿一覧:\n" + "\n".join(messages))

@socket_client.socket_mode_request_listeners.append
def handle_events(client: SocketModeClient, req: SocketModeRequest):
    if req.type == "events_api":
        event = req.payload.get("event", {})
        logging.info(f"イベント受信タイプ: {req.type}")
        logging.info(f"ペイロード内容: {json.dumps(req.payload, ensure_ascii=False, indent=2)}")
        if event.get("type") == "message" and "bot_id" not in event:
            handle_command(event.get("text", ""), event.get("channel"), event.get("blocks"))
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

def load_last_post_time(msg):
    path = f".last_post_{hash(msg)}"
    if os.path.exists(path):
        return float(open(path).read())
    return 0

def save_last_post_time(msg):
    path = f".last_post_{hash(msg)}"
    with open(path, "w") as f:
        f.write(str(time.time()))

def should_post(cfg, now_ts):
    last_post = load_last_post_time(cfg["message"])
    interval = cfg["interval"]
    fixed = cfg.get("fixed_time")

    if fixed is not None:
        today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        target = today + datetime.timedelta(seconds=fixed)
        return last_post < target.timestamp() <= now_ts
    return now_ts - last_post >= interval

def check_and_post_all():
    now_ts = time.time()
    configs = load_all_configs()
    for cfg in configs:
        if should_post(cfg, now_ts):
            try:
                client.chat_postMessage(channel=cfg["channel_id"], text=cfg["message"])
                save_last_post_time(cfg["message"])
                logging.info(f"✅ 投稿: {cfg['message']}")
            except Exception as e:
                logging.error(f"❌ 投稿失敗: {e}")

def start_posting_loop():
    def loop():
        while True:
            check_and_post_all()
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
