import logging

from slack_bolt.adapter.socket_mode import SocketModeHandler

from . import config, db
from .app import app

logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

db.init()
SocketModeHandler(app, config.SLACK_APP_TOKEN).start()
