import os
import sys
import traceback
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from config import cfg
from bot.utils import db, errors, functions, logs

intents = discord.Intents.default()
intents.message_content = True  # required for guess


class CustomTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        user = await db.User.get_or_create(id=interaction.user.id)
        if user.is_blacklisted:
            return False

        if interaction.guild is not None:
            guild = await db.Guild.get_or_create(id=interaction.guild.id)
            if guild.is_blacklisted:
                return False

        return True

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        error = getattr(error, "original", error)  # normal commands
        if isinstance(error, app_commands.AppCommandError):
            error = error.__cause__ if error.__cause__ is not None else error
        command = interaction.command

        if command is None:
            logs.logger.error(f"Ignoring exception in command tree", exc_info=error)
        elif command.on_error:
            return

        if isinstance(error, errors.SilentError):
            pass
        elif isinstance(error, errors.CustomError):
            await functions.reply(interaction, error.message, ephemeral=error.ephemeral)
        else:
            await functions.reply(interaction, "An unhandled error occurred.")
            logs.logger.error(
                f"Ignoring exception in command {command.name}", exc_info=error
            )


class Track(commands.AutoShardedBot):
    def __init__(self, sync: bool = False):
        super().__init__(
            command_prefix=cfg.discord.default_prefix,
            intents=intents,
            tree_cls=CustomTree,
            case_insensitive=True,
            owner_ids=cfg.discord.owner_ids,
        )

        self.sync: bool = sync
        self.stopping: bool = False  # used for warm shutdowns
        self.online_since: datetime = datetime.utcnow()

    async def setup_hook(self) -> None:
        try:
            await self.load_extensions()
        except commands.ExtensionError as error:
            print(f"Failed to load extension {error.name}.")
            traceback.print_exception(
                type(error), error, error.__traceback__, file=sys.stderr
            )
            sys.exit()

        if self.sync:
            logs.logger.info("Syncing tree...")
            await self.tree.sync()
            logs.logger.info(f"Tree Synced")

    async def load_extensions(self) -> None:
        for root, dirs, files in os.walk("extensions"):
            for file in files:
                if file.endswith("py"):
                    try:
                        extension = f"{root}.{file[:-3]}".replace("/", ".")
                        await self.load_extension(extension)
                    except commands.NoEntryPointError as e:
                        message = f"{e.name} has no entry point."
                        logs.logger.warning(message)
                        pass

        await self.load_extension("jishaku")

    @property
    def created_on(self) -> datetime:
        return self.user.created_at
