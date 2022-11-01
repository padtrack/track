import aiohttp
import io
import json
import logging
import time
from typing import Optional

import aioredis
import bs4
import discord
import redis
import rq
import rq.job
import rq.worker
from discord import app_commands, ui
from discord.ext import commands

from bot import tasks
from bot.track import Track
from bot.utils import errors, functions
from config import cfg

logger = logging.getLogger("track")
_url = f"redis://:{cfg.redis.password}@localhost:{cfg.redis.port}/"
_redis: redis.Redis = redis.from_url(_url)
_async_redis: aioredis.Redis = aioredis.from_url(_url)

URL_MAX_LENGTH = 512


def track_task_request(f):
    async def wrapped(self, *args, **kwargs):
        await _async_redis.set(f"task_request_{self._interaction.user.id}", "", ex=600)
        try:
            return await f(self, *args, **kwargs)
        except Exception as e:
            logger.error("Render tracking failed", exc_info=e)
        finally:
            await _async_redis.delete(f"task_request_{self._interaction.user.id}")

    return wrapped


class BuildsButton(ui.Button):
    def __init__(self, builds: list[dict], **kwargs):
        super().__init__(label="View Builds", **kwargs)

        self.fp = io.StringIO()
        for build in builds:
            if clan := build["clan"]:
                self.fp.write(f"[{clan}] ")
            self.fp.write(build["name"] + "\n" + build["build_url"] + "\n\n")
        self.fp.seek(0)

    async def callback(self, interaction: discord.Interaction) -> None:
        # noinspection PyTypeChecker
        file = discord.File(self.fp, filename="builds.txt")
        await functions.reply(interaction, file=file, ephemeral=True)
        self.fp.seek(0)


class ChatButton(ui.Button):
    def __init__(self, chat: str, **kwargs):
        super().__init__(label="Export Chat", **kwargs)

        self.fp = io.StringIO(chat)
        self.fp.seek(0)

    async def callback(self, interaction: discord.Interaction) -> None:
        # noinspection PyTypeChecker
        file = discord.File(self.fp, filename="chat.txt")
        await functions.reply(interaction, file=file, ephemeral=True)
        self.fp.seek(0)


class RenderView(ui.View):
    def __init__(self, builds: list[dict], chat: str, **kwargs):
        super().__init__(**kwargs)

        for build in builds:
            if build["relation"] == -1:
                url = build["build_url"] + "&ref=track"
                if len(url) <= URL_MAX_LENGTH:
                    self.add_item(ui.Button(label="Player Build", url=url))
                break

        self.builds_button = BuildsButton(builds)
        self.add_item(self.builds_button)
        self.chat_button = ChatButton(chat)
        self.add_item(self.chat_button)
        self.message: Optional[discord.Message] = None

    async def on_timeout(self) -> None:
        self.builds_button.disabled = True
        self.chat_button.disabled = True
        await self.message.edit(view=self)


class Render:
    DEFAULT_FPS = 30
    DEFAULT_QUALITY = 7
    MAX_WAIT_TIME = 180
    FINISHED_TTL = 600
    COOLDOWN = 30
    QUEUE_SIZE = 10

    PROGRESS_FOREGROUND = "▰"
    PROGRESS_BACKGROUND = "▱"

    QUEUE: rq.Queue

    def __init__(self, bot: Track, interaction: discord.Interaction):
        self._bot = bot
        self._interaction = interaction
        self._job: Optional[rq.job.Job] = None

    @property
    def job_position(self) -> int:
        pos = self._job.get_position()
        return pos + 1 if pos else 1

    @property
    def job_ttl(self) -> int:
        return max(self.QUEUE.count, 1) * self.MAX_WAIT_TIME

    async def _reupload(
        self, task_status: Optional[str], exc_info: Optional[str]
    ) -> None:
        raise NotImplementedError()

    async def _check(self) -> bool:
        worker_count = rq.worker.Worker.count(connection=_redis, queue=self.QUEUE)
        cooldown = await _async_redis.ttl(f"cooldown_{self._interaction.user.id}")

        try:
            assert (
                worker_count != 0
            ), f"{self._interaction.user.mention} No running workers detected."
            assert (
                self.QUEUE.count <= self.QUEUE_SIZE
            ), f"{self._interaction.user.mention} Queue full. Please try again later."
            assert (
                cooldown <= 0
            ), f"{self._interaction.user.mention} You're on render cooldown until <t:{int(time.time()) + cooldown}:R>."
            assert not await _async_redis.exists(
                f"task_request_{self._interaction.user.id}"
            ), f"{self._interaction.user.mention} You have an ongoing/queued render. Please try again later."
            return True
        except AssertionError as e:
            await functions.reply(self._interaction, str(e), ephemeral=True)
            return False

    @track_task_request
    async def poll_result(self, input_name: str) -> None:
        embed = RenderWaitingEmbed(input_name, self.job_position)
        message = await functions.reply(self._interaction, embed=embed)
        last_position: Optional[int] = None
        last_progress: Optional[float] = None

        psub = _async_redis.pubsub()
        psub.ignore_subscribe_messages = True
        await psub.psubscribe(f"*{self._job.id}")

        async for response in psub.listen():
            if response["type"] != "pmessage":
                continue

            status = self._job.get_status(refresh=True)
            match status:
                case "queued":
                    position = self.job_position
                    if position == last_position:
                        continue

                    embed = RenderWaitingEmbed(input_name, position)
                    message = await message.edit(embed=embed)
                    last_position = position
                case "started":
                    progress = self._job.get_meta(refresh=True).get("progress", 0.0)
                    if progress == last_progress:
                        continue

                    embed = RenderStartedEmbed(input_name, self._job, progress)
                    message = await message.edit(embed=embed)
                    last_progress = progress
                case "finished":
                    if not self._job.result:
                        continue

                    if isinstance(self._job.result, tuple):
                        data, filename, time_taken, builds_str, chat = self._job.result

                        try:
                            file = discord.File(io.BytesIO(data), f"{filename}.mp4")
                            if builds_str:
                                view = RenderView(json.loads(builds_str), chat)
                                sent_message = await functions.reply(
                                    self._interaction,
                                    content=None,
                                    file=file,
                                    view=view,
                                )
                                view.message = sent_message
                            else:
                                sent_message = await functions.reply(
                                    self._interaction, content=None, file=file
                                )
                            embed = RenderSuccessEmbed(
                                input_name, sent_message, time_taken
                            )
                        except discord.HTTPException:
                            embed = RenderFailureEmbed(
                                input_name,
                                "Rendered file too large (>8 MB). Consider reducing quality.",
                            )
                    elif isinstance(self._job.result, errors.RenderError):
                        embed = RenderFailureEmbed(input_name, self._job.result.message)
                    else:
                        logger.error(f"Unhandled job result {self._job.result}")
                        embed = RenderFailureEmbed(
                            input_name, "An unhandled error occurred."
                        )

                    await message.edit(embed=embed)
                    break
                case "failed":
                    timeout = self._job.get_meta(refresh=True).get("timeout", None)
                    if timeout:
                        logger.warning("Render job timed out")
                        embed = RenderFailureEmbed(input_name, "Job timed out.")
                    else:
                        # fetch again to update exc_info
                        job = rq.job.Job.fetch(self._job.id, connection=_redis)
                        task_status = self._job.meta.get("status", None)
                        logger.error(
                            f'Render job failed with status "{task_status}"\n{job.exc_info}'
                        )
                        if "StopIteration" in job.exc_info:
                            err_message = "An unhandled error occurred (likely incomplete replay)."
                        else:
                            err_message = "An unhandled error occurred."

                        embed = RenderFailureEmbed(input_name, err_message)
                        await self._reupload(task_status, job.exc_info)

                    await message.edit(embed=embed)
                    break
                case _base:
                    logger.warning(f"Unknown job status {status}")
                    embed = RenderFailureEmbed(input_name, "Render job expired.")
                    await message.edit(embed=embed)
                    break

        await psub.unsubscribe()
        await psub.close()


class RenderSingle(Render):
    QUEUE = rq.Queue("single", connection=_redis)

    def __init__(
        self,
        bot: Track,
        interaction: discord.Interaction,
        attachment: discord.Attachment,
    ):
        super().__init__(bot, interaction)

        self._attachment = attachment

    async def _reupload(
        self, task_status: Optional[str], exc_info: Optional[str]
    ) -> None:
        try:
            with (
                io.BytesIO() as fp,
                io.StringIO(f"Task Status: {task_status}\n\n{exc_info}\n") as report,
            ):
                await self._attachment.save(fp)

                channel = await self._bot.fetch_channel(cfg.channels.failed_renders)
                # noinspection PyTypeChecker
                await channel.send(
                    files=[
                        discord.File(report, filename="report.txt"),
                        discord.File(fp, filename=self._attachment.filename),
                    ]
                )
        except (discord.HTTPException, discord.NotFound):
            logger.error(
                f"Failed to reupload render with interaction ID {self._interaction.id}"
            )

    async def start(self, *args) -> None:
        if not await self._check():
            return

        await self._interaction.response.defer()

        with io.BytesIO() as fp:
            await self._attachment.save(fp)
            fp.seek(0)

            arguments = [self._interaction.user.id, self.COOLDOWN, fp.read()]
            arguments.extend(args)
            self._job = self.QUEUE.enqueue(
                tasks.render_single,
                args=arguments,
                failure_ttl=self.FINISHED_TTL,
                result_ttl=self.FINISHED_TTL,
                ttl=self.job_ttl,
            )

        self._bot.loop.create_task(self.poll_result(self._attachment.filename))


class RenderDual(Render):
    QUEUE = rq.Queue("dual", connection=_redis)

    def __init__(
        self,
        bot: Track,
        interaction: discord.Interaction,
        attachment1: discord.Attachment,
        attachment2: discord.Attachment,
    ):
        super().__init__(bot, interaction)

        self._attachment1 = attachment1
        self._attachment2 = attachment2

    async def _reupload(
        self, task_status: Optional[str], exc_info: Optional[str]
    ) -> None:
        try:
            with (
                io.BytesIO() as fp1,
                io.BytesIO() as fp2,
                io.StringIO(f"Task Status: {task_status}\n\n{exc_info}\n") as report,
            ):
                await self._attachment1.save(fp1)
                await self._attachment2.save(fp2)

                channel = await self._bot.fetch_channel(cfg.channels.failed_renders)
                # noinspection PyTypeChecker
                await channel.send(
                    files=[
                        discord.File(report, filename="report.txt"),
                        discord.File(fp1, filename=self._attachment1.filename),
                        discord.File(fp2, filename=self._attachment2.filename),
                    ],
                )
        except (discord.HTTPException, discord.NotFound):
            logger.error(
                f"Failed to reupload render with interaction ID {self._interaction.id}"
            )

    async def start(self, *args) -> None:
        if not await self._check():
            return

        await self._interaction.response.defer()

        with (io.BytesIO() as fp1, io.BytesIO() as fp2):
            await self._attachment1.save(fp1)
            fp1.seek(0)
            await self._attachment2.save(fp2)
            fp2.seek(0)

            arguments = [
                self._interaction.user.id,
                self.COOLDOWN,
                fp1.read(),
                fp2.read(),
            ]
            arguments.extend(args)
            self._job = self.QUEUE.enqueue(
                tasks.render_dual,
                args=arguments,
                failure_ttl=self.FINISHED_TTL,
                result_ttl=self.FINISHED_TTL,
                ttl=self.job_ttl,
            )

        self._bot.loop.create_task(self.poll_result(f"{args[2]} vs. {args[3]}"))


class RenderKOTS(Render):
    QUEUE = rq.Queue("dual", connection=_redis)

    def __init__(
        self,
        bot: Track,
        interaction: discord.Interaction,
        url1: str,
        url2: str,
    ):
        super().__init__(bot, interaction)

        self._url1 = url1
        self._url2 = url2

    async def _reupload(
        self, task_status: Optional[str], exc_info: Optional[str]
    ) -> None:
        try:
            with (
                io.StringIO(f"Task Status: {task_status}\n\n{exc_info}\n") as report,
            ):

                channel = await self._bot.fetch_channel(cfg.channels.failed_renders)
                # noinspection PyTypeChecker
                await channel.send(
                    f"KOTS URLs:\n{self._url1}\n{self._url2}",
                    files=[
                        discord.File(report, filename="report.txt"),
                    ],
                )
        except (discord.HTTPException, discord.NotFound):
            logger.error(
                f"Failed to reupload render with interaction ID {self._interaction.id}"
            )

    async def start(self, *args) -> None:
        if not await self._check():
            return

        await self._interaction.response.defer()

        async with aiohttp.ClientSession(
            headers={"Connection": "keep-alive"}
        ) as session:
            async with (
                session.get(self._url1) as response1,
                session.get(self._url2) as response2,
            ):
                with (
                    io.BytesIO(await response1.read()) as fp1,
                    io.BytesIO(await response2.read()) as fp2,
                ):

                    arguments = [
                        self._interaction.user.id,
                        self.COOLDOWN,
                        fp1.read(),
                        fp2.read(),
                    ]
                    arguments.extend(args)
                    self._job = self.QUEUE.enqueue(
                        tasks.render_dual,
                        args=arguments,
                        failure_ttl=self.FINISHED_TTL,
                        result_ttl=self.FINISHED_TTL,
                        ttl=self.job_ttl,
                    )

                self._bot.loop.create_task(self.poll_result(f"{args[2]} vs. {args[3]}"))


class RenderEmbed(discord.Embed):
    TITLE = "**Minimap Renderer**"

    def __init__(self, color: int, input_name: str, **kwargs):
        super().__init__(title=RenderEmbed.TITLE, color=color)

        self.add_field(name="Input", value=input_name)
        self.set_footer(
            text="Consider supporting the project! https://ko-fi.com/trackpad"
        )
        self.process_kwargs(**kwargs)

    def process_kwargs(self, **kwargs):
        if status := kwargs.pop("status", None):
            self.add_field(name="Status", value=status, inline=False)

        if position := kwargs.pop("position", None):
            self.add_field(name="Position", value=position, inline=False)

        if progress := kwargs.pop("progress", None):
            bar = (
                f"{round(progress * 10) * Render.PROGRESS_FOREGROUND}"
                f"{round((1 - progress) * 10) * Render.PROGRESS_BACKGROUND}"
            )
            self.add_field(name="Progress", value=bar, inline=False)

        if time_taken := kwargs.pop("time_taken", None):
            self.add_field(name="Time taken", value=time_taken, inline=False)

        if result := kwargs.pop("result", None):
            self.add_field(name="Result", value=result, inline=False)


class RenderWaitingEmbed(RenderEmbed):
    COLOR = 0xFF751A  # orange

    def __init__(self, input_name: str, position: int):
        super().__init__(self.COLOR, input_name, position=position)


class RenderStartedEmbed(RenderEmbed):
    COLOR = 0xFFFF1A  # yellow

    def __init__(self, input_name: str, job: rq.job.Job, progress: float):
        if task_status := job.get_meta(refresh=True).get("status", None):
            super().__init__(
                self.COLOR, input_name, status=task_status.title(), progress=progress
            )
        else:
            super().__init__(self.COLOR, input_name, status="Started")


class RenderSuccessEmbed(RenderEmbed):
    COLOR = 0x66FF33  # green
    TEMPLATE = "File link: [{0}]({1})\nMessage link: [Message]({2})"

    def __init__(self, input_name: str, sent_message: discord.Message, time_taken: str):
        sent_attachment = sent_message.attachments[0]
        result_msg = self.TEMPLATE.format(
            sent_attachment.filename, sent_attachment.url, sent_message.jump_url
        )

        super().__init__(
            self.COLOR, input_name, result=result_msg, time_taken=time_taken
        )


class RenderFailureEmbed(RenderEmbed):
    COLOR = 0xFF1A1A  # red

    def __init__(self, input_name: str, err_message):
        super().__init__(self.COLOR, input_name, status="Error", result=err_message)


class RenderCog(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot

    @app_commands.command(
        name="render",
        description="Generates a minimap timelapse and more from a replay file.",
        extras={"category": "wows"},
    )
    @app_commands.describe(
        replay="A .wowsreplay file.",
        fps="Can be a value from 15 to 30, and defaults to 20.",
        quality="Can be a value from 1-9, and defaults to 7. Higher values may require Nitro boosts.",
        logs="Shows additional statistics, and defaults to on.",
        anon='Anonymizes player names in the format "Player X", and defaults to off. Ignored when logs is off.',
        chat="Shows chat, and defaults to on. Ignored when logs is off.",
        team_tracers="Colors tracers by their relation to the replay creator, and defaults to off.",
    )
    async def render(
        self,
        interaction: discord.Interaction,
        replay: discord.Attachment,
        fps: app_commands.Range[int, 15, 30] = 20,
        quality: app_commands.Range[int, 1, 9] = 7,
        logs: bool = True,
        anon: bool = False,
        chat: bool = True,
        team_tracers: bool = False,
    ):
        render = RenderSingle(self.bot, interaction, replay)
        await render.start(fps, quality, logs, anon, chat, team_tracers)

    @app_commands.command(
        name="dualrender",
        description="Merges two replay files from opposing teams into a minimap timelapse.",
        extras={"category": "wows"},
    )
    @app_commands.describe(
        replay_a='The replay to use as the "green" team.',
        replay_b='The replay to use as the "red" team.',
        name_a='The name to use for the "green" team.',
        name_b='The name to use for the "red" team.',
        fps="Can be a value from 15 to 30, and defaults to 20.",
        quality="Can be a value from 1-9, and defaults to 7. Higher values may require Nitro boosts.",
        team_tracers="Colors tracers by their relation to the replay creator, and defaults to off.",
    )
    async def dual_render(
        self,
        interaction: discord.Interaction,
        replay_a: discord.Attachment,
        replay_b: discord.Attachment,
        name_a: app_commands.Range[str, 1, 12] = "Alpha",
        name_b: app_commands.Range[str, 1, 12] = "Bravo",
        fps: app_commands.Range[int, 15, 30] = 20,
        quality: app_commands.Range[int, 1, 9] = 7,
        team_tracers: bool = False,
    ):
        render = RenderDual(self.bot, interaction, replay_a, replay_b)
        await render.start(fps, quality, name_a, name_b, team_tracers)

    @app_commands.command(
        name="kotsrender",
        description="Shortcut to dualrender that takes a game URL.",
        extras={"category": "wows"},
    )
    @app_commands.describe(
        url="URL that matches */matches/{match_id}/game/{game_id}",
        fps="Can be a value from 15 to 30, and defaults to 20.",
        quality="Can be a value from 1-9, and defaults to 7. Higher values may require Nitro boosts.",
        team_tracers="Colors tracers by their relation to the replay creator, and defaults to off.",
    )
    async def kots_render(
        self,
        interaction: discord.Interaction,
        url: str,
        fps: app_commands.Range[int, 15, 30] = 20,
        quality: app_commands.Range[int, 1, 9] = 7,
        team_tracers: bool = False,
    ):
        # TODO: move interaction defer here, update docs
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(
                        f"Error code {response.status} while fetching KOTS match"
                    )
                    await interaction.response.send_message(
                        "Failed to fetch match, please check URL."
                    )
                    return

                soup = bs4.BeautifulSoup(await response.text(), "html.parser")
                if len(replay_urls := soup.select("a[href*=replay]")) != 2:
                    await interaction.response.send_message(
                        "Couldn't find two replay URLs."
                    )
                    return

                tag_a, tag_b = replay_urls

                def get_team_name(tag):
                    parent = next(
                        parent for x, parent in enumerate(tag.parents) if x == 13
                    )
                    heading = parent.contents[0]
                    return heading.text[10:-1]

                name_a, name_b = get_team_name(tag_a), get_team_name(tag_b)

                url_a = f"https://wows-tournaments.com{tag_a['href']}"
                url_b = f"https://wows-tournaments.com{tag_b['href']}"
                render = RenderKOTS(self.bot, interaction, url_a, url_b)
                await render.start(fps, quality, name_a, name_b, team_tracers)


async def setup(bot: Track):
    await bot.add_cog(RenderCog(bot))
    await _async_redis.config_set("notify-keyspace-events", "KEA")
