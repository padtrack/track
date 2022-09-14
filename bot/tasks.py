import contextlib
import io
import json
import os
import tempfile
import time

import redis
import rq

# noinspection PyPackageRequirements
from renderer.render import Renderer, RenderDual, ReplayData
from replay_parser import ReplayParser
from rq.job import Job

from bot.utils.errors import ArenaMismatchError, VersionNotFoundError
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


@contextlib.contextmanager
def measure_time() -> float:
    start = time.perf_counter()
    yield lambda: time.perf_counter() - start


def cooldown_handler(job: Job, *_exc_info):
    _redis.set(f"cooldown_{job.args[0]}", "", ex=job.args[1])


def timeout_handler(job: Job, _exc_type, exc_value, _traceback):
    if isinstance(exc_value, rq.worker.JobTimeoutException):
        job.meta["timeout"] = True
        job.save_meta()


def progress_callback(job: Job):
    def callback(progress: float):
        job.meta["progress"] = progress
        job.save_meta()

    return callback


def render_single(
    requester_id: int,
    cooldown: int,
    data: bytes,
    fps: int,
    quality: int,
    logs: bool,
    anon: bool,
    enable_chat: bool,
    team_tracers: bool,
):
    job: Job = rq.get_current_job()

    with measure_time() as t:
        job.meta["status"] = "reading"
        job.save_meta()

        try:
            with io.BytesIO(data) as fp:
                replay_info = ReplayParser(fp, strict=True).get_info()
                replay_data: ReplayData = replay_info["hidden"]["replay_data"]
        except (ModuleNotFoundError, RuntimeError):
            return VersionNotFoundError()

        try:
            job.meta["status"] = "rendering"
            job.save_meta()

            with temp() as tmp:
                render = Renderer(
                    replay_data, logs, anon, enable_chat, team_tracers, use_tqdm=False
                )
                render.start(tmp.name, fps, quality, progress_callback(job))
                tmp.seek(0)
                video_data = tmp.read()
        except ModuleNotFoundError:
            return VersionNotFoundError()

    time_taken = time.strftime("%M:%S", time.gmtime(t()))
    file_name = str(replay_data.game_arena_id)

    try:
        file_name = file_name[len(file_name) - 8 :]
    except IndexError:
        pass

    players = replay_info["hidden"]["replay_data"].player_info
    chat = ""
    for battle_time, events in replay_info["hidden"]["replay_data"].events.items():
        for message in events.evt_chat:
            player = players[message.player_id]

            if anon and player.clan_tag:
                clan_tag = f"[{'#' * len(player.clan_tag)}] "
            elif player.clan_tag:
                clan_tag = f"[{player.clan_tag}] "
            else:
                clan_tag = ""

            if anon:
                name = render.usernames[player.id]
            else:
                name = player.name

            chat += f"[{battle_time // 60:02}:{battle_time % 60:02}] {clan_tag}{name}: {message.message}\n"

    _redis.set(f"cooldown_{requester_id}", "", ex=cooldown)
    return (
        video_data,
        f"render_{file_name}",
        time_taken,
        json.dumps(render.get_player_build()),
        chat,
    )


def render_dual(
    requester_id: int,
    cooldown: int,
    gdata: bytes,
    rdata: bytes,
    fps: int,
    quality: int,
    green_name: str,
    red_name: str,
    team_tracers: bool,
):
    job: Job = rq.get_current_job()

    with measure_time() as t:
        job.meta["status"] = "reading"
        job.save_meta()

        try:
            with (io.BytesIO(gdata) as fp1, io.BytesIO(rdata) as fp2):
                g_replay_info = ReplayParser(fp1, strict=True).get_info()
                g_replay_data: ReplayData = g_replay_info["hidden"]["replay_data"]
                r_replay_info = ReplayParser(fp2, strict=True).get_info()
                r_replay_data: ReplayData = r_replay_info["hidden"]["replay_data"]
        except (ModuleNotFoundError, RuntimeError):
            return VersionNotFoundError()

        if g_replay_data.game_arena_id != r_replay_data.game_arena_id:
            return ArenaMismatchError()

        try:
            job.meta["status"] = "rendering"
            job.save_meta()

            with temp() as tmp:
                RenderDual(
                    g_replay_data,
                    r_replay_data,
                    green_name,
                    red_name,
                    team_tracers,
                    use_tqdm=False,
                ).start(tmp.name, fps, quality, progress_callback(job))
                tmp.seek(0)
                video_data = tmp.read()
        except ModuleNotFoundError:
            return VersionNotFoundError()

    time_taken = time.strftime("%M:%S", time.gmtime(t()))
    name = str(g_replay_data.game_arena_id)

    try:
        name = name[len(name) - 8 :]
    except IndexError:
        pass

    _redis.set(f"cooldown_{requester_id}", "", ex=cooldown)
    return video_data, f"render_{green_name}_{red_name}_{name}", time_taken, ""
