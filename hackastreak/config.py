import os
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]

# Comma separated Slack user IDs who see usage stats on the App Home
ADMIN_USER_IDS = {u.strip() for u in os.getenv("ADMIN_USER_IDS", "").split(",") if u.strip()}

# Channel where saying "hackastreak" gets a reaction + help message
PINGWORD_CHANNEL_ID = os.getenv("PINGWORD_CHANNEL_ID", "C0AJLGZ73NE")

DB_PATH = os.getenv("DB_PATH", "hackastreak.db")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
