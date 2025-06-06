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
    
LOG_FILE = "daily_logs.json"
if __name__ == "__main__":
    daily_reminder()
    app.start(port=3000)