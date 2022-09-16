import argparse
import os
import sys

sys.path.insert(1, os.path.join(sys.path[0], ".."))

from bot.track import Track
from bot.utils import logs
from config import cfg


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync", action=argparse.BooleanOptionalAction)
    args = parser.parse_args()
    try:
        logs.logger.info("Launching bot")
        bot = Track(args.sync)
        bot.run(cfg.discord.token, log_handler=logs.handler)
    except Exception as e:
        logs.logger.error("Exiting due to error", exc_info=e)
