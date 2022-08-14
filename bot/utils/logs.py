__all__ = ['logger', 'handler']

import logging.handlers
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../logs/track.log")

logger = logging.getLogger('track')
logger.setLevel(logging.INFO)
logging.getLogger('discord').setLevel(logging.INFO)
logging.getLogger('discord.http').setLevel(logging.WARNING)

handler = logging.handlers.RotatingFileHandler(
    filename=PATH,
    encoding='utf-8',
    maxBytes=32 * 1024 * 1024,  # 32 MiB
    backupCount=5,  # Rotate through 5 files
)

fmt = "[{asctime}] [{levelname:<8}] {name}: {message}"
dt_fmt = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(fmt, dt_fmt, style='{')

handler.setFormatter(formatter)
logger.addHandler(handler)
