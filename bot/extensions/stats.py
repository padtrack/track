from __future__ import annotations
from typing import List, Optional, Tuple
import datetime


from discord.ext import commands, tasks
from discord import app_commands, ui
import discord

import api
from bot.track import Track
from bot.utils import assets, db, wows
from bot.utils.logs import logger


RESOURCES = {
    "pvp": ("Randoms", "EMOJI_RANDOM_BATTLE", "RANDOM_BATTLE"),
    "pve": ("Co-Op", "EMOJI_COOPERATIVE_BATTLE", "COOPERATIVE_BATTLE"),
    "rank": ("Ranked", "EMOJI_RANKED_BATTLE", "RANKED_BATTLE"),
    "rank_old": ("Ranked (old)", "EMOJI_RANKED_BATTLE", "RANKED_BATTLE"),
}
BATTLE_TYPES = {
    index: RESOURCES[b_type]
    for b_type, t_data in api.BATTLE_TYPES.items()
    for index in t_data["sizes"].values()
}
EPOCH = datetime.datetime.fromtimestamp(0)


class BattleTypeSelect(ui.Select):
    SIZES = ["all", "solo", "duo", "trio"]

    def __init__(self, default_only=False):
        super().__init__(min_values=1, max_values=1, options=[])

        for battle_type, type_data in api.BATTLE_TYPES.items():
            if default_only:
                index = type_data["sizes"][type_data["default"]]
                label, emoji_id, _ = BATTLE_TYPES[index]
                self.append_option(
                    discord.SelectOption(
                        label=label,
                        value=index,
                        emoji=assets.get(emoji_id),
                        default=index == api.DEFAULT_BATTLE_TYPE,
                    )
                )
            else:
                for size, index in type_data["sizes"].items():
                    label, emoji_id, _ = BATTLE_TYPES[index]
                    size_name = self.SIZES[size]

                    if len(type_data["sizes"]) > 1:
                        label = f"{label} ({size_name})"

                    self.append_option(
                        discord.SelectOption(
                            label=label,
                            value=index,
                            emoji=assets.get(emoji_id),
                            default=index == api.DEFAULT_BATTLE_TYPE,
                        )
                    )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        value = self.values[0]

        for option in self.options:
            option.default = option.value == value

        await self.view.update_battle_type(value)


class PartialPlayerView(ui.View):
    def __init__(self, user_id: int, player: api.PartialPlayer, **kwargs):
        super().__init__(**kwargs)

        self.user_id: int = user_id
        self.player: api.PartialPlayer = player
        self.message: Optional[discord.Message] = None

        self.select = BattleTypeSelect(default_only=True)
        self.add_item(self.select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You must be the command invoker to do that.", ephemeral=True
            )
            return False
        return True

    async def update_battle_type(self, battle_type: str):
        if battle_type not in self.player.statistics:
            if statistics := await api.get_partial_statistics(
                self.player.region,
                self.player.id,
                self.player.clan_role.clan_id,
                battle_type,
            ):
                self.player.statistics[battle_type] = statistics
            else:
                logger.error(
                    "Failed to update partial player "
                    f'(region "{self.player.region}", '
                    f'id "{self.player.id}", '
                    f'battle_type "{battle_type}")'
                )
                return

        await self.message.edit(
            embed=PartialPlayerEmbed(self.player, battle_type), view=self
        )

    async def on_timeout(self):
        self.select.disabled = True
        await self.message.edit(view=self)


class PartialPlayerEmbed(discord.Embed):
    def __init__(
        self,
        player: api.PartialPlayer,
        battle_type: str = api.DEFAULT_BATTLE_TYPE,
    ):
        stats = player.statistics[battle_type]
        clan = player.clan_role.clan

        super().__init__(
            title=f"{player.name}'s Partial Stats ({player.region.upper()})",
            description=(
                f"Battles: `{stats.battles_count}`\n"
                f"Wins: `{stats.wins_percentage:.2f}%`\n"
            ),
            url=player.profile_url,
            timestamp=list(player.statistics.values())[0].last_battle_time,
        )

        self.add_field(
            name="Clan",
            value=(
                f"[{clan.tag}] {clan.name}\n"
                f"Role: {player.clan_role.role.title().replace('_', ' ')}\n"
                f"Joined: <t:{int(player.clan_role.joined_at.timestamp())}:D>\n"
            ),
            inline=False,
        )

        self.add_field(
            name="Averages",
            value=(
                f"Damage: `{stats.damage_per_battle:.0f}`\n"
                f"EXP: `{stats.exp_per_battle:.0f}`\n"
                f"Kills: `{stats.frags_per_battle:.2f}`\n"
            ),
            inline=False,
        )

        self.set_footer(text="Last battle")


class FullPlayerView(ui.View):
    def __init__(self, user_id: int, player: api.FullPlayer):
        super().__init__()

        self.message: Optional[discord.Message] = None
        self.user_id = user_id
        self.player = player

        self.select = BattleTypeSelect()
        self.add_item(self.select)
        self.add_item(ui.Button(label="WoWS Numbers", url=player.wows_numbers_url))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You must be the command invoker to do that.", ephemeral=True
            )
            return False
        return True

    async def update_battle_type(self, battle_type: str):
        await self.message.edit(
            embed=FullPlayerEmbed(self.player, battle_type), view=self
        )

    async def on_timeout(self):
        self.select.disabled = True
        await self.message.edit(view=self)


class StatisticsEmbedCommon(discord.Embed):
    METRICS = {
        "base_exp": ("Base EXP", "EMOJI_EXP", 0),
        "damage_dealt": ("Damage", "EMOJI_DAMAGE_DEALT", 0),
        "frags": ("Kills", "EMOJI_FRAGS", 2),
        "planes_killed": ("Aircraft", "EMOJI_PLANES_KILLED", 2),
        "ships_spotted": ("Spotted", "EMOJI_SHIPS_SPOTTED", 2),
        "scouting_damage": ("Scouting", "EMOJI_SCOUTING_DAMAGE", 0),
        "total_agro": ("Potential", "EMOJI_POTENTIAL_DAMAGE", 0),
    }
    ARMAMENTS = {
        "main": "Main Battery",
        "atba": "Secondaries",
        "tpd": "Torpedoes",
        "dbomb": "Depth Charges",
        "planes": "Aircraft",
        "ram": "Rams",
    }

    def __init__(self, statistics: dict[str, int], **kwargs):
        if not statistics:
            super().__init__(description="No statistics for this gamemode.", **kwargs)
            return

        self.stats = statistics

        self.stats["total_agro"] = self.stats["art_agro"] + self.stats["tpd_agro"]
        self.stats["base_exp"] = self.stats["original_exp"]
        self.stats["max_base_exp"] = self.stats["max_exp"]

        wins, wins_rate = self.rate("wins")
        losses = self.stats["losses"]
        ties = self.battles - wins - losses
        survived, survived_rate = self.rate("survived")
        died = self.battles - survived

        super().__init__(
            description=(
                f"Battles: `{self.battles}`\n"
                f"Wins: `{wins_rate * 100:.2f}%` (`{wins}`/`{losses}`/`{ties}`)\n"
                f"Survival: `{survived_rate * 100:.2f}%` (`{survived}`/`{died}`)"
            ),
            **kwargs,
        )

    @property
    def battles(self) -> int:
        return self.stats["battles_count"]

    def rate(self, key: str, total: str = None) -> Tuple[int, float]:
        value = self.stats[key]
        total = self.stats[total] if total else self.battles
        return value, value / total if self.battles != 0 else 0

    def add_metrics(self):
        averages, max_values = zip(
            *[self.get_metric(key) for key in self.METRICS.keys()]
        )

        self.add_field(
            name="Averages",
            value=self.format_metrics(averages),
            inline=True,
        )

        self.add_field(
            name="Records",
            value=self.format_metrics(max_values),
            inline=True,
        )

    def get_metric(self, key: str) -> Tuple[Optional[float], int]:
        if not self.battles:
            return 0, 0

        total = self.stats[key]
        max_value = self.stats[f"max_{key}"]

        if total >= 4_000_000_000:
            return None, max_value

        return total / self.battles, max_value

    def format_metrics(self, values: List[Optional[float, int]]):
        strings = []

        for index, (label, emoji_id, digits) in enumerate(self.METRICS.values()):
            if not (value := values[index]):
                continue

            digits = 0 if isinstance(value, int) else digits

            if not digits:
                value = "{:,}".format(int(value)).replace(",", " ")
                strings.append(f"{assets.get(emoji_id)} {label}: `{value}`")
            else:
                strings.append(f"{assets.get(emoji_id)} {label}: `{value:.{digits}f}`")

        return "\n".join(strings)

    def add_armaments(self):
        armaments = {
            key: data
            for key in self.ARMAMENTS.keys()
            if (data := self.get_armament(key)) is not None
        }

        self.add_field(
            name="Armaments",
            value=self.format_armaments(armaments),
            inline=False,
        )

    def get_armament(self, key: str) -> Tuple[int, int, Optional[float]]:
        frags = self.stats.get(f"frags_by_{key}", None)
        max_frags = self.stats.get(f"max_frags_by_{key}", None)
        hits = self.stats.get(f"hits_by_{key}", None)
        shots = self.stats.get(f"shots_by_{key}", None)
        if not shots or shots == 0:
            return frags, max_frags, None

        return frags, max_frags, hits / shots

    def format_armaments(self, values: dict[str, Tuple[int, int, float]]) -> str:
        strings = []

        for key, (frags, max_frags, accuracy) in values.items():
            label = self.ARMAMENTS.get(key)
            accuracy = "-" if accuracy is None else "{:.2f}%".format(accuracy * 100)

            strings.append(f"{label}: (`{frags}`/`{max_frags}`/`{accuracy}`)")

        return "\n".join(strings)


class FullPlayerEmbed(StatisticsEmbedCommon):
    def __init__(
        self, player: api.FullPlayer, battle_type: str = api.DEFAULT_BATTLE_TYPE
    ):
        super().__init__(
            statistics=player.statistics[battle_type],
            title=f"[{player.karma}] {player.name}'s Stats ({player.region.upper()})",
            url=player.profile_url,
            timestamp=player.last_battle_time,
        )

        if player.clan_role:
            clan = player.clan_role.clan
            self.add_field(
                name="Clan",
                value=(
                    f"[{clan.tag}] {clan.name}\n"
                    f"Role: {player.clan_role.role.title().replace('_', ' ')}\n"
                    f"Joined: <t:{int(player.clan_role.joined_at.timestamp())}:D>\n"
                ),
                inline=False,
            )

        if hasattr(self, "stats"):
            self.add_metrics()
            self.add_armaments()

        label, _, icon_id = BATTLE_TYPES[battle_type]
        self.set_author(name=label, icon_url=assets.get(icon_id))

        self.set_footer(text="Last battle")


class HiddenEmbed(discord.Embed):
    def __init__(self, player: api.Player):
        clan = player.clan_role.clan

        super().__init__(
            title=f"{player.name}'s Stats ({player.region.upper()})",
            description="Profile is hidden.",
            url=player.profile_url,
        )

        self.add_field(
            name="Clan",
            value=(
                f"Clan: [{clan.tag}] {clan.name}\n"
                f"Role: {player.clan_role.role.title().replace('_', ' ')}\n"
                f"Joined: <t:{int(player.clan_role.joined_at.timestamp())}:D>\n"
            ),
            inline=False,
        )


class ShipStatisticsView(ui.View):
    def __init__(
        self,
        user_id: int,
        player: api.FullPlayer,
        ship_id: int,
        ship_name: str,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.user_id: int = user_id
        self.player: api.FullPlayer = player
        self.ship_id: int = ship_id
        self.ship_name: str = ship_name
        self.message: Optional[discord.Message] = None
        self.statistics: dict[str, dict[str, int]] = {}

        self.select = BattleTypeSelect()
        self.add_item(self.select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You must be the command invoker to do that.", ephemeral=True
            )
            return False
        return True

    async def update_battle_type(self, battle_type: str):
        if battle_type not in self.statistics:
            if (
                stats := await api.get_ship_statistics(
                    self.player.region,
                    self.player.id,
                    self.ship_id,
                    battle_type,
                )
            ) is not None:
                self.statistics[battle_type] = stats
            else:
                logger.error(
                    f"Failed to update ship (id {self.ship_id}) statistics for player "
                    f'(region "{self.player.region}", '
                    f'id "{self.player.id}", '
                    f'battle_type "{battle_type}")'
                )
                return

        await self.message.edit(
            embed=ShipStatisticsEmbed(
                self.player, self.statistics[battle_type], self.ship_name, battle_type
            ),
            view=self,
        )

    async def on_timeout(self):
        self.select.disabled = True
        await self.message.edit(view=self)


class ShipStatisticsEmbed(StatisticsEmbedCommon):
    def __init__(
        self,
        player: api.FullPlayer,
        stats: dict[str, int],
        ship_name: str,
        battle_type: str = api.DEFAULT_BATTLE_TYPE,
    ):
        super().__init__(
            statistics=stats,
            title=f"{player.name}'s {ship_name} ({player.region.upper()})",
            url=player.profile_url,
        )

        if hasattr(self, "stats"):
            self.add_metrics()
            self.add_armaments()

        label, _, icon_id = BATTLE_TYPES[battle_type]
        self.set_author(name=label, icon_url=assets.get(icon_id))


class StatsCog(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot

        self.load_seasons.start()

    @tasks.loop(hours=1)
    async def load_seasons(self):
        logger.info("Loading Seasons...")

        try:
            await api.wg.get_seasons()
            logger.info("Seasons Loaded")
        except Exception as e:
            logger.warning("Failed to load Seasons", exc_info=e)

            if not api.wg.seasons:
                import sys

                sys.exit(1)

    # noinspection PyUnusedLocal
    @app_commands.command(
        name="stats",
        description="Fetches player statistics.",
        extras={"category": "wows"},
    )
    @app_commands.describe(
        region="The WoWS region to search players in.",
        player="The username to search for.",
        ship="The ship to search for.",
    )
    async def stats(
        self,
        interaction: discord.Interaction,
        region: Optional[wows.Regions],
        player: app_commands.Transform[api.Player, api.PlayerTransformer],
        ship: Optional[app_commands.Transform[wows.Ship, wows.ShipTransformer]],
    ):
        if isinstance(player, api.PartialPlayer):
            if ship:
                await interaction.followup.send(
                    "Cannot fetch ship statistics for player with hidden profile."
                )
            else:
                embed = PartialPlayerEmbed(player)
                view = PartialPlayerView(interaction.user.id, player)
                view.message = await interaction.followup.send(embed=embed, view=view)
        elif isinstance(player, api.FullPlayer):
            if player.last_battle_time == EPOCH:
                await interaction.followup.send(
                    "This player has not played any battles."
                )
                return

            if ship:
                if not (
                    stats := await api.get_ship_statistics(
                        player.region,
                        player.id,
                        ship.id,
                        access_code=player.used_access_code,
                    )
                ):
                    await interaction.followup.send(
                        "Player has no statistics for this ship."
                    )
                else:
                    ship_name = ship.tl(interaction)["full"]
                    embed = ShipStatisticsEmbed(player, stats, ship_name)
                    view = ShipStatisticsView(
                        interaction.user.id, player, ship.id, ship_name
                    )
                    view.message = await interaction.followup.send(
                        embed=embed, view=view
                    )
            else:
                embed = FullPlayerEmbed(player)
                view = FullPlayerView(interaction.user.id, player)
                view.message = await interaction.followup.send(embed=embed, view=view)
        elif isinstance(player, api.Player):
            if ship:
                await interaction.followup.send(
                    "Cannot fetch ship statistics for player with hidden profile."
                )
            elif player.hidden_profile:
                await interaction.followup.send(embed=HiddenEmbed(player))
            else:
                await interaction.followup.send(
                    "This player has not played any battles."
                )
        else:
            await interaction.followup.send("No players found.")

    @app_commands.command(
        name="mystats",
        description="Shortcut for linked users.",
        extras={"category": "wows"},
    )
    @app_commands.describe(ship="The ship to search for.")
    async def my_stats(
        self,
        interaction: discord.Interaction,
        ship: Optional[app_commands.Transform[wows.Ship, wows.ShipTransformer]],
    ):
        await interaction.response.defer()
        user = await db.User.get_or_create(id=interaction.user.id)

        if not user.wg_id:
            await interaction.response.send_message(
                "You must be linked to use this command! See `/link`.", ephemeral=True
            )
            return

        player = await api.get_player(user.wg_region, user.wg_id, user.wg_ac)

        if not isinstance(player, api.FullPlayer):
            await interaction.followup.send(
                "Failed to fetch your data. Check your profile visibility settings."
            )
            return

        # Duplicated code

        if player.last_battle_time == EPOCH:
            await interaction.followup.send("You have not played any battles.")
            return

        if ship:
            if not (
                stats := await api.get_ship_statistics(
                    player.region,
                    player.id,
                    ship.id,
                    access_code=player.used_access_code,
                )
            ):
                await interaction.followup.send("You have no statistics for this ship.")
            else:
                ship_name = ship.tl(interaction)["full"]
                embed = ShipStatisticsEmbed(player, stats, ship_name)
                view = ShipStatisticsView(
                    interaction.user.id, player, ship.id, ship_name
                )
                view.message = await interaction.followup.send(embed=embed, view=view)
        else:
            embed = FullPlayerEmbed(player)
            view = FullPlayerView(interaction.user.id, player)
            view.message = await interaction.followup.send(embed=embed, view=view)


async def setup(bot: Track):
    await bot.add_cog(StatsCog(bot))
