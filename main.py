from slack_bolt import App
from slack_sdk import WebClient
import json
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import os

load_dotenv()
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
CHANNEL_ID = os.environ["CHANNEL_ID"]

app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
client = WebClient(token=SLACK_BOT_TOKEN)


LOG_FILE = "daily_logs.json"

# ログ読み込み
try:
    with open(LOG_FILE, "r") as f:
        logs = json.load(f)
except FileNotFoundError:
    logs = {}

def save_logs():
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

def daily_reminder():
    today_str = datetime.now().strftime("%Y-%m-%d")
    text = f"{today_str} の発表スレッドです。ここに返信して発表してください。"
    res = client.chat_postMessage(channel=CHANNEL_ID, text=text)
    thread_ts = res['ts']
    logs[today_str] = {"thread_ts": thread_ts, "messages": []}
    save_logs()
    print(f"Created thread for {today_str}")

scheduler = BackgroundScheduler()
scheduler.add_job(daily_reminder, 'cron', hour=20, minute=0)  # 毎日20時
scheduler.start()

# スレッド内の返信を保存
@app.event("message")
def handle_message_events(body, say, logger):
    event = body.get("event", {})
    thread_ts = event.get("thread_ts")
    channel = event.get("channel")
    user = event.get("user")
    text = event.get("text")
    ts = event.get("ts")

    if thread_ts and channel == CHANNEL_ID and user is not None:
        for deta,data in logs.items():
            if data["thread_ts"] == thread_ts:
                data["messages"].append({
                    "user": user,
                    "text": text,
                    "ts": ts
                })
                save_logs()
                break

# 単日ログ表示: "!log YYYY-MM-DD"
@app.message("^!log ")
def log_command(message, say):
    text = message.get("text", "")
    args = text.split()
    if len(args) < 2:
        say("日付を指定してください。例: !log 2025-06-04")
        return
    date = args[1]
    if date not in logs:
        say(f"{date} のログはありません。")
        return

    response = f"【{date} の発表ログ】\n"
    for m in logs[date]["messages"]:
        response += f"<@{m['user']}>: {m['text']}\n"

    if len(response) > 3500:
        response = response[:3500] + "\n(長いため一部省略)"
    say(response)

# 🔽 ここが新しく追加する !log_all コマンド 🔽
@app.message("!log_all")
def log_all_command(message, say):
    response = "📚【過去すべての発表ログ】\n"
    for date in sorted(logs.keys()):
        response += f"\n📅 {date}:\n"
        for m in logs[date]["messages"]:
            response += f" - <@{m['user']}>: {m['text']}\n"

    if len(response) > 3500:
        response = response[:3500] + "\n(長いため一部省略)"

    say(response)

# 起動
if __name__ == "__main__":
    app.start(port=3000)