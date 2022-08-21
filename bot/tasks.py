import contextlib
import io
import logging
import os
import random
import string
import tempfile
import time

import redis
import rq
from renderer.render import Renderer, RenderDual, ReplayData
from replay_parser import ReplayParser
from rq.job import Job

from bot.utils.errors import ReadingError, RenderingError, VersionNotFoundError
from config import cfg

_url = f"redis://:{cfg.redis.password}@{cfg.redis.host}:{cfg.redis.port}/"
_redis = redis.from_url(_url)


@contextlib.contextmanager
def temp():
    tmp = tempfile.NamedTemporaryFile("w+b", suffix=".mp4", delete=False)
    try:
        yield tmp
    finally:
        tmp.close()
        os.remove(tmp.name)


def render_single(
        requester_id: int, cooldown: int, data: bytes,
        fps: int, quality: int,
        logs: bool, anon: bool, enable_chat: bool, team_tracers: bool
):
    job: Job = rq.get_current_job()

    try:
        t1 = time.perf_counter()
        job.meta["status"] = "Reading"
        job.save_meta()

        try:
            with io.BytesIO(data) as fp:
                replay_info = ReplayParser(fp, strict=True).get_info()
        except (ModuleNotFoundError, RuntimeError):
            raise VersionNotFoundError()
        except Exception:
            raise ReadingError()

        replay_data: ReplayData = replay_info["hidden"]["replay_data"]

        def progress_callback(progress: float):
            job.meta["progress"] = progress
            job.save_meta()

        try:
            job.meta["status"] = "Rendering"
            job.save_meta()

            with temp() as tmp:
                Renderer(
                    replay_data, logs, anon, enable_chat, team_tracers, use_tqdm=False
                ).start(tmp.name, fps, quality, progress_callback)

                tmp.seek(0)
                video_data = tmp.read()

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


def render_dual(
        requester_id: int, cooldown: int, gdata: bytes, rdata: bytes,
        fps: int, quality: int,
        green_name: str, red_name: str, team_tracers: bool
):
    job: Job = rq.get_current_job()

    try:
        t1 = time.perf_counter()
        job.meta["status"] = "Reading"
        job.save_meta()

        try:
            with (
                io.BytesIO(gdata) as fp1,
                io.BytesIO(rdata) as fp2,
            ):
                g_replay_info = ReplayParser(fp1, strict=True).get_info()
                g_replay_data: ReplayData = g_replay_info["hidden"]["replay_data"]

                r_replay_info = ReplayParser(fp2, strict=True).get_info()
                r_replay_data: ReplayData = r_replay_info["hidden"]["replay_data"]
        except (ModuleNotFoundError, RuntimeError):
            raise VersionNotFoundError()
        except Exception:
            raise ReadingError()

        def progress_callback(progress: float):
            job.meta["progress"] = progress
            job.save_meta()

        try:
            job.meta["status"] = "Rendering"
            job.save_meta()

            with temp() as tmp:
                RenderDual(
                    g_replay_data, r_replay_data, green_name, red_name, team_tracers, use_tqdm=False
                ).start(tmp.name, fps, quality, progress_callback)

                tmp.seek(0)
                video_data = tmp.read()

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