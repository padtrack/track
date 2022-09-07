from __future__ import annotations
from typing import List, Literal, Optional
import asyncio
import io
import os
from PIL import Image
import random
import toml
from unidecode import unidecode

from discord.ext import commands
from discord import app_commands, ui
import discord
from sqlalchemy import select

from bot.track import Track
from bot.utils import db, errors, wows


CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../assets/public/guess.toml"
)
SILHOUETTES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../assets/public/ships_silhouettes"
)


class InspectEmbed(discord.Embed):
    ICON = "https://cdn.discordapp.com/attachments/651324664496521225/651332148963442688/logo.png"

    def __init__(
        self, cog: GuessCog, interaction: discord.Interaction, ship: wows.Ship
    ):
        tl = ship.tl(interaction)
        super().__init__(
            title=f'{tl["full"]} ({tl["short"]})',
        )

        self.add_field(
            name="Basic Information",
            value=f"ID: `{ship.id}`\n"
            f"Paper Ship: `{ship.isPaperShip}`\n"
            f"Group: `{ship.group}`\n"
            f"Tier: `{ship.level}`\n"
            f"Class: `{ship.species}`\n"
            f"Nation: `{ship.nation}`\n",
        )

        self.set_author(name=f"{ship.name} ({ship.index})", icon_url=self.ICON)
        self.set_image(url="attachment://ship.png")

        allowed = cog.is_allowed(ship)
        guess_str = f"Allowed: `{allowed}`\n"
        if allowed:
            guess_str += (
                "Cleaned Names:\n"
                f"- `{wows.Ship.clean(unidecode(tl['full']))}`\n"
                f"- `{wows.Ship.clean(unidecode(tl['short']))}`\n"
            )

            if similar_ships := cog.get_similar(ship):
                guess_str += "Similar:\n"
                for similar in similar_ships:
                    similar_tl = similar.tl(interaction)
                    guess_str += f"- {similar_tl['full']}\n"

        self.add_field(name="Guess", value=guess_str)


class InspectView(ui.View):
    SHIPBUILDER_URL = "https://app.wowssb.com/ship?shipIndexes={}&ref=track"
    WOWSFT_URL = "https://wowsft.com/ship?index={}"

    def __init__(self, ship: wows.Ship, **kwargs):
        super().__init__(**kwargs)

        self.add_item(
            ui.Button(label="ShipBuilder", url=self.SHIPBUILDER_URL.format(ship.index))
        )
        self.add_item(ui.Button(label="WoWSFT", url=self.WOWSFT_URL.format(ship.index)))


class GuessEmbed(discord.Embed):
    def __init__(
        self,
        difficulty: str,
        min_level: int,
        max_level: int,
        historical: bool,
    ):
        super().__init__(
            title="Guess the ship!",
            description=(
                f"Difficulty: `{difficulty.title()}`\n"
                + (
                    f"Tiers: `{min_level}-{max_level}`\n"
                    if min_level != max_level
                    else f"Tier: `{min_level}`\n"
                )
                + ("(Only historical ships)" if historical else "")
            ),
        )

        self.set_image(url="attachment://ship.png")


class GuessCancelButton(ui.Button):
    def __init__(self, interaction: discord.Interaction, ship: wows.Ship):
        super().__init__(label="Cancel", style=discord.ButtonStyle.danger)

        self.loop = interaction.client.loop
        self.user_id = interaction.user.id
        self.channel_id = interaction.channel_id
        self.ship = ship

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            # TODO: this sounds weird
            await interaction.response.send_message(
                "You must be the command invoker to do that.", ephemeral=True
            )
            return

        for task in asyncio.all_tasks(loop=self.loop):
            if task.get_name() == f"guess_{self.channel_id}" and not task.done():
                task.cancel()
                await self.view.close()
                await interaction.response.send_message(
                    f"The answer was `{self.ship.tl(interaction)['full']}`."
                )
                break


class GuessView(ui.View):
    def __init__(self, interaction: discord.Interaction, ship: wows.Ship):
        super().__init__(timeout=GuessGame.HINT_TIMER + GuessGame.END_TIMER)

        self.message: Optional[discord.Message] = None
        self.button = GuessCancelButton(interaction, ship)
        self.add_item(self.button)

    async def close(self) -> None:
        self.button.disabled = True
        await self.message.edit(view=self)


class GuessGame:
    HINT_TIMER = 20
    END_TIMER = 10

    def __init__(
        self,
        cog: GuessCog,
        interaction: discord.Interaction,
        difficulty: str,
        min_level: int,
        max_level: int,
        historical: bool,
        ship: wows.Ship,
    ):
        self.interaction = interaction
        self.difficulty = difficulty
        self.min_level = min_level
        self.max_level = max_level
        self.historical = historical
        self.ship = ship
        self.accepted = cog.get_accepted(
            interaction, difficulty, min_level, max_level, historical, ship
        )

    def get_hint(self) -> str:
        if self.min_level != self.max_level:
            return f"Need a hint? It's tier `{self.ship.level}`."
        else:
            return f"Need a hint? It's a ship from `{self.ship.nation.upper()}`."

    async def run(self) -> None:
        view = GuessView(self.interaction, self.ship)
        sent_message = await self.interaction.followup.send(
            embed=GuessEmbed(
                self.difficulty, self.min_level, self.max_level, self.historical
            ),
            view=view,
            file=GuessCog.get_silhouette(self.ship),
        )
        view.message = sent_message
        start = discord.utils.snowflake_time(sent_message.id)

        def check(m: discord.Message):
            clean = wows.Ship.clean(unidecode(m.content))
            return (
                clean in self.accepted and m.channel.id == self.interaction.channel_id
            )

        try:
            message: discord.Message = await self.interaction.client.wait_for(
                "message", timeout=self.HINT_TIMER, check=check
            )
        except asyncio.TimeoutError:
            await self.interaction.followup.send(self.get_hint())

            try:
                message: discord.Message = await self.interaction.client.wait_for(
                    "message", timeout=self.END_TIMER, check=check
                )
            except asyncio.TimeoutError:
                await view.close()
                await self.interaction.followup.send(
                    f"Time's up. The answer was `{self.ship.tl(self.interaction)['full']}`."
                )
                return

        if message is not None:
            await view.close()

            time = (discord.utils.snowflake_time(message.id) - start).total_seconds()

            # cheap trick to ensure user exists
            user = await db.User.get_or_create(id=message.author.id)
            db.User.invalidate(id=user.id)

            result_msg = f"Well done! Time taken: `{time:.3f}s`.\n"
            async with db.async_session() as session:
                user = (
                    await session.execute(
                        select(db.User).filter_by(id=message.author.id)
                    )
                ).scalar_one()

                if user.guess_record is None or time < user.guess_record:
                    result_msg += "A new record!"
                    user.guess_record = time

                user.guess_count += 1
                await session.commit()

            await message.channel.send(result_msg, reference=message)


class GuessCog(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot
        with open(CONFIG_PATH) as fp:
            self.config = toml.load(fp)

    def is_allowed(self, ship: wows.Ship) -> bool:
        return (
            ship.group in self.config["groups"]
            and ship.index not in self.config["forbidden"]
        )

    def random_ship(
        self, min_level: int, max_level: int, historical: bool
    ) -> wows.Ship:
        valid = []
        for ship in wows.ships.values():
            if min_level <= ship.level <= max_level and self.is_allowed(ship):
                if historical and ship.isPaperShip:
                    continue

                valid.append(ship)

        try:
            return random.choice(valid)
        except IndexError:
            # NOTE: as of 0.11.7 there are non-paper ships at every level
            # but just in case WG adds another level
            raise errors.CustomError(
                "No valid ships with given criteria "
                f"(Tiers {min_level}-{max_level}, historical: {historical})."
            )

    def get_similar(self, ship: wows.Ship) -> List[wows.Ship]:
        return [
            wows.ships[index]
            for group in self.config["similar"]
            for index in group
            if index != ship.index and ship.index in group
        ]

    def get_accepted(
        self,
        interaction: discord.Interaction,
        difficulty: str,
        min_level: int,
        max_level: int,
        historical: bool,
        ship: wows.Ship,
    ):
        accepted = [
            wows.Ship.clean(unidecode(ship.tl(interaction)["short"])),
            wows.Ship.clean(unidecode(ship.tl(interaction)["full"])),
        ]

        if difficulty != "hard":
            for similar in self.get_similar(ship):
                if (
                    difficulty == "normal"
                    and similar.level < min_level
                    or similar.level > max_level
                ) or (historical and similar.isPaperShip):
                    continue

                accepted.append(
                    wows.Ship.clean(unidecode(similar.tl(interaction)["short"]))
                )
                accepted.append(
                    wows.Ship.clean(unidecode(similar.tl(interaction)["full"]))
                )

        return list(set(accepted))

    @staticmethod
    def get_silhouette(ship: wows.Ship) -> discord.File:
        fp = io.BytesIO()

        base = Image.open(f"{SILHOUETTES_PATH}/ship_background.png")
        silhouette = Image.open(f"{SILHOUETTES_PATH}/{ship.index}.png").convert("RGBA")
        base.paste(silhouette, (0, 0), silhouette)

        base.save(fp, "PNG")
        fp.seek(0)

        return discord.File(fp, filename="ship.png")

    @app_commands.command(
        name="guess",
        description='Silhouette guessing game based on "Who\'s that Pokemon?"',
        extras={"category": "wows"},
    )
    async def guess(
        self,
        interaction: discord.Interaction,
        difficulty: Literal["easy", "normal", "hard"] = "normal",
        min_level: app_commands.Range[int, 1, 11] = 6,
        max_level: app_commands.Range[int, 1, 11] = 11,
        historical: bool = False,
    ):
        if min_level > max_level:
            await interaction.response.send_message(
                "min_level must be less than or equal to max_level.", ephemeral=True
            )

        for task in asyncio.all_tasks(loop=self.bot.loop):
            if task.get_name() == f"guess_{interaction.channel_id}" and not task.done():
                await interaction.response.send_message(
                    "A game is already running in this channel.", ephemeral=True
                )
                return

        await interaction.response.defer()

        ship = self.random_ship(min_level, max_level, historical)
        game = GuessGame(
            self,
            interaction,
            difficulty,
            min_level,
            max_level,
            historical,
            ship,
        )

        await self.bot.loop.create_task(
            game.run(), name=f"guess_{interaction.channel_id}"
        )

    @app_commands.command(
        name="inspect", description="View ship details.", extras={"category": "wows"}
    )
    @app_commands.describe(ship="The ship to use.")
    async def inspect(
        self,
        interaction: discord.Interaction,
        ship: app_commands.Transform[wows.Ship, wows.ShipTransformer],
    ):
        await interaction.response.send_message(
            embed=InspectEmbed(self, interaction, ship),
            view=InspectView(ship),
            file=self.get_silhouette(ship),
        )


async def setup(bot: Track):
    await bot.add_cog(GuessCog(bot))
