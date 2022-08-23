import logging
import os
import sys

sys.path.insert(1, os.path.join(sys.path[0], ".."))

from bot.track import Track
from bot.utils import logs
from config import cfg


if __name__ == "__main__":
    try:
        bot = Track()
        bot.run(cfg.discord.token, log_handler=logs.handler)
    except Exception as e:
        logs.logger.log(logging.ERROR, "Exiting due to error", exc_info=e)
