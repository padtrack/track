import io
import logging
import random
import string
import tempfile
import time

import redis
import rq
from renderer.render import Renderer
from replay_parser import ReplayParser
from rq.job import Job

from bot.utils.errors import ReadingError, RenderingError, VersionNotFoundError
from config import cfg

_url = f"redis://:{cfg.redis.password}@{cfg.redis.host}:{cfg.redis.port}/"
_redis = redis.from_url(_url)


def render_single(
        data: bytes, requester_id: int,
        logs: bool, anon: bool, enable_chat: bool,
        fps: int, quality: int,
        cooldown: int
):
    job: Job = rq.get_current_job()

    try:
        t1 = time.perf_counter()
        job.meta["status"] = "Reading"
        job.save_meta()

        try:
            with io.BytesIO(data) as fp:
                replay_info = ReplayParser(fp).get_info()
        except RuntimeError:
            raise VersionNotFoundError()
        except Exception:
            raise ReadingError()

        replay_data = replay_info["hidden"]["replay_data"]

        # if replay_data.game_battle_type not in [7, 11, 14, 15, 16]:
        #     raise UnsupportedBattleTypeError()
        print(replay_data.game_battle_type)

        try:
            job.meta["status"] = "Rendering"
            job.save_meta()
            with tempfile.NamedTemporaryFile("w+b", suffix=".mp4", delete=False) as video_file:
                Renderer(replay_data, logs, anon, enable_chat).start(video_file.name, fps, quality)

                # with open(video_file.name, "rb") as f:
                #     video_data = f.read()
                video_file.seek(0)
                video_data = video_file.read()

        except ModuleNotFoundError:
            raise VersionNotFoundError()
        except Exception as e:
            logging.error("Fatal error while rendering", exc_info=e)
            raise RenderingError()

        t2 = time.perf_counter()
        str_taken = time.strftime("%M:%S", time.gmtime(t2 - t1))
        random_str = "".join(
            random.choice(string.ascii_uppercase[:6]) for _ in range(4)
        )
        random_str += "".join(random.choice(string.digits) for _ in range(8))
        return video_data, random_str, str_taken
    except Exception as e:
        return e
    finally:
        _redis.set(
            f"cooldown_{requester_id}", "", ex=cooldown
        )
