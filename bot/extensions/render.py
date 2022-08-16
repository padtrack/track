import asyncio
import io
import logging
from typing import Callable, Optional

import aioredis
import discord
import redis
import rq
import rq.job
import rq.worker
from discord import app_commands, ui
from discord.ext import commands

from bot.track import Track
from bot.utils import errors, functions
from bot import tasks
from config import cfg

logger = logging.getLogger("track")
_url = f"redis://:{cfg.redis.password}@localhost:{cfg.redis.port}/"
_redis: redis.Redis = redis.from_url(_url)
_async_redis: aioredis.Redis = aioredis.from_url(_url)


def track_task_request(f):
    async def wrapped(cls, interaction: discord.Interaction, attachment: discord.Attachment, *args, **kwargs):
        await _async_redis.set(f"task_request_{interaction.user.id}", "", ex=Render.MAX_WAIT_TIME)
        try:
            return await f(cls, interaction, attachment, *args, **kwargs)
        except Exception as e:
            logger.log(logging.ERROR, "An error occurred while rendering", exc_info=e)
        finally:
            await _async_redis.delete(f"task_request_{interaction.user.id}")

    return wrapped


class Render:
    DEFAULT_FPS = 30
    DEFAULT_QUALITY = 7
    MAX_WAIT_TIME = 180
    COOLDOWN = 30
    QUEUE_SIZE = 10

    PROGRESS_FOREGROUND = "▰"
    PROGRESS_BACKGROUND = "▱"

    QUEUE: rq.Queue
    TASK: Callable

    @classmethod
    async def check(cls, interaction: discord.Interaction):
        worker_count = rq.worker.Worker.count(connection=_redis, queue=cls.QUEUE)
        cooldown = await _async_redis.ttl(f"cooldown_{interaction.user.id}")

        try:
            assert worker_count != 0, \
                f"{interaction.user.mention} No running workers detected."
            assert (cls.QUEUE.count <= cls.QUEUE_SIZE), \
                f"{interaction.user.mention} Queue full. Please try again later."
            assert cooldown <= 0, \
                f"{interaction.user.mention} You're on render cooldown for `{cooldown}s`."
            assert not await _async_redis.exists(f"task_request_{interaction.user.id}"), \
                f"{interaction.user.mention} You have an ongoing/queued render. Please try again later."
            return True
        except AssertionError as e:
            await functions.reply(interaction, str(e), ephemeral=True)
            return False

    @staticmethod
    def get_job_position(job: rq.job.Job):
        _pos = job.get_position()
        return _pos + 1 if _pos else 1

    @classmethod
    async def worker(cls, bot: Track, interaction: discord.Interaction, attachment: discord.Attachment, *args):
        if not await cls.check(interaction):
            return

        job_ttl = max(cls.QUEUE.count, 1) * cls.MAX_WAIT_TIME

        with io.BytesIO() as buf:
            await attachment.save(buf)
            buf.seek(0)

            arguments = [buf.read(), interaction.user.id]
            arguments.extend(args)
            job: rq.job.Job = cls.QUEUE.enqueue(
                cls.TASK,
                args=arguments,
                failure_ttl=cls.MAX_WAIT_TIME,
                result_ttl=cls.MAX_WAIT_TIME,
                ttl=job_ttl,
            )

        bot.loop.create_task(cls.poll_result(interaction, attachment, job))

    @classmethod
    @track_task_request
    async def poll_result(cls, interaction: discord.Interaction, attachment: discord.Attachment, job: rq.job.Job):
        position = Render.get_job_position(job)
        embed = RenderWaitingEmbed(attachment, position)

        message = await functions.reply(interaction, content=None, embed=embed)
        status = "failed"
        last_position: Optional[int] = None
        last_progress: Optional[float] = None

        try:
            while True:
                position = Render.get_job_position(job)
                status = job.get_status(refresh=True)

                match status:
                    case "queued":
                        if position != last_position:
                            embed = RenderWaitingEmbed(attachment, position)
                            await message.edit(embed=embed)
                            last_position = position
                    case "started":
                        progress = job.get_meta(refresh=True).get("progress", 0.0)
                        if progress != last_progress:
                            embed = RenderStartedEmbed(attachment, job, progress)
                            await message.edit(embed=embed)
                            last_progress = progress
                    case "finished":
                        if isinstance(job.result, tuple):
                            data, random_str, time_taken = job.result

                            try:
                                with io.BytesIO(data) as reader:
                                    file = discord.File(reader, f"{random_str}.mp4")

                                sent_message = await functions.reply(interaction, content=None, file=file)
                                embed = RenderSuccessEmbed(attachment, sent_message, time_taken)
                            except discord.HTTPException:
                                err_message = "Rendered file too large for Discord 8MB limit! Try lowering quality."
                                embed = RenderFailureEmbed(attachment, err_message)
                        elif isinstance(job.result, errors.RenderError):
                            embed = RenderFailureEmbed(attachment, str(job.result))
                        elif isinstance(job.result, rq.worker.JobTimeoutException):
                            embed = RenderFailureEmbed(attachment, "Max job time reached.")
                        else:
                            embed = RenderFailureEmbed(attachment, "An unhandled error occurred.")
                            logger.error(f"Unhandled job result {job.result}", exc_info=job.exc_info)

                        await message.edit(embed=embed)
                        break
                    case "failed":
                        embed = RenderEmbed(attachment, RenderFailureEmbed.COLOR, status="Failed")
                        await message.edit(embed=embed)
                        break
                    case _base:
                        logger.warning("Unknown job status", status)
                        pass

                await asyncio.sleep(1)
        except Exception as e:
            logger.log(logging.ERROR, "An error occurred while rendering", exc_info=e)

        job.delete()
        return status


class RenderSingle(Render):
    QUEUE = rq.Queue("single", connection=_redis)
    TASK = tasks.render_single


class RenderEmbed(discord.Embed):
    TITLE = "**Minimap Renderer**"

    def __init__(self, attachment: discord.Attachment, color: int, **kwargs):
        super().__init__(title=RenderEmbed.TITLE, color=color)

        self.add_field(name="Input File", value=attachment.filename, inline=False)
        self.set_footer(text=f"help me pay jeff bezos https://ko-fi.com/trackpad")
        self.process_kwargs(**kwargs)

    def process_kwargs(self, **kwargs):
        if status := kwargs.pop("status", None):
            self.add_field(name="Status", value=status, inline=False)

        if position := kwargs.pop("position", None):
            self.add_field(name="Position", value=position, inline=False)

        if progress := kwargs.pop("progress", None):
            bar = f"{round(progress * 10) * Render.PROGRESS_FOREGROUND}" \
                  f"{round((1 - progress) * 10) * Render.PROGRESS_BACKGROUND}"
            self.add_field(name="Progress", value=bar, inline=False)

        if time_taken := kwargs.pop("time_taken", None):
            self.add_field(name="Time taken", value=time_taken, inline=False)

        if result := kwargs.pop("result", None):
            self.add_field(name="Result", value=result, inline=False)


class RenderWaitingEmbed(RenderEmbed):
    COLOR = 0xFF751A  # orange

    def __init__(self, attachment: discord.Attachment, position: int):
        super().__init__(attachment, self.COLOR, position=position)


class RenderStartedEmbed(RenderEmbed):
    COLOR = 0xFFFF1A  # yellow

    def __init__(self, attachment: discord.Attachment, job: rq.job.Job, progress: float):
        if task_status := job.get_meta(refresh=True).get("status", None):
            super().__init__(attachment, self.COLOR, status=task_status, progress=progress)
        else:
            super().__init__(attachment, self.COLOR, status="Running")


class RenderSuccessEmbed(RenderEmbed):
    COLOR = 0x66FF33  # green
    TEMPLATE = "File link: [{0}]({1})\nMessage link: [Message]({2})"

    def __init__(self, attachment: discord.Attachment, sent_message: discord.Message, time_taken: str):
        sent_attachment = sent_message.attachments[0]
        result_msg = self.TEMPLATE.format(sent_attachment.filename, sent_attachment.url, sent_message.jump_url)

        super().__init__(attachment, self.COLOR, result=result_msg, time_taken=time_taken)


class RenderFailureEmbed(RenderEmbed):
    COLOR = 0xFF1A1A  # red

    def __init__(self, attachment: discord.Attachment, err_message):
        super().__init__(attachment, self.COLOR, status="Error", result=err_message)


class RenderCog(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot
        self._render = Render()

    @app_commands.command(description="Generates a minimap timelapse and more from a replay file.")
    @app_commands.describe(replay="A .wowsreplay file.",
                           fps="Can be a value from 15 to 30, and defaults to 20.",
                           quality="Can be a value from 1-9, and defaults to 7. Higher values may require Nitro boosts.",
                           logs="Shows additional statistics, and defaults to on.",
                           anon="Anonymizes player names in the format \"Player X\", and defaults to off. Ignored when logs is off.",
                           chat="Shows chat, and defaults to on. Ignored when logs is off.")
    async def render(self, interaction: discord.Interaction, replay: discord.Attachment,
                     fps: app_commands.Range[int, 15, 30] = 20, quality: app_commands.Range[int, 1, 9] = 7,
                     logs: bool = True, anon: bool = False, chat: bool = True):
        await RenderSingle.worker(self.bot, interaction, replay, logs, anon, chat, fps, quality, RenderSingle.COOLDOWN)


async def setup(bot: Track):
    await bot.add_cog(RenderCog(bot))
    # _redis.client_id()
    # await _async_redis.client_id()
