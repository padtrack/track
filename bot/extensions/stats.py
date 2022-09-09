from __future__ import annotations
from typing import Any, Callable, Coroutine, Optional
from discord.ext import commands, tasks
from discord import app_commands, ui
import discord


from bot.track import Track
from bot.utils import assets, vortex, wg_api
from bot.utils.logs import logger


# class CVCSelect(ui.Select):
#     def __init__(self, **kwargs):
#         super().__init__(min_values=1, max_values=1, **kwargs)
#
#         self.add_option(
#             label="Clan Battles",
#             value="battle",
#             emoji=assets.get("EMOJI_CLAN_BATTLE"),
#             default=True,
#         )
#         self.add_option(
#             label="Clan Brawl",
#             value="brawl",
#             emoji=assets.get("EMOJI_BRAWL_BATTLE"),
#             default=False,
#         )
#
#
# class CVCModal(ui.Modal):
#     def __init__(self, cvc_callback: Callable[[discord.Interaction, dict], Coroutine[Any]], **kwargs):
#         super().__init__(title="CVC Modal", **kwargs)
#         self.cvc_callback = cvc_callback
#
#         self.cvc = CVCSelect()
#         self.add_item(self.cvc)
#         self.season = ui.TextInput(
#             label="Season", style=discord.TextStyle.short, max_length=2
#         )
#         self.add_item(self.season)
#
#     async def on_submit(self, interaction: discord.Interaction) -> None:
#         try:
#             season = int(self.season.value)
#             if self.cvc.values[0] == "brawl":
#                 season += 200
#
#             await self.cvc_callback(interaction, {"battle_type": "cvc", "season": season})
#         except ValueError:
#             await interaction.response.send_message("Invalid season.", ephemeral=True)


class BattleTypeButton(ui.Button):
    def __init__(
        self,
        value: str,
        view_callback: Callable[[discord.Interaction, str], Coroutine[Any]],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.value = value
        self.view_callback = view_callback

    async def callback(self, interaction: discord.Interaction):
        await self.view_callback(interaction, self.value)


class PartialStatisticsView(ui.View):
    BATTLE_TYPES = {
        "pvp": ("Randoms", "EMOJI_RANDOM_BATTLE"),
        "pve": ("Co-Op", "EMOJI_COOPERATIVE_BATTLE"),
        "rank_solo": ("Ranked", "EMOJI_RANKED_BATTLE"),
        "cvc": ("Clan Battles", "EMOJI_CLAN_BATTLE"),
    }

    def __init__(
        self, user_id: int, player: vortex.PartialPlayer, initial: str = "pvp", **kwargs
    ):
        super().__init__(**kwargs)

        self.user_id: int = user_id
        self.player: vortex.PartialPlayer = player
        self.message: Optional[discord.Message] = None

        for value, (label, emoji_id) in self.BATTLE_TYPES.items():
            self.add_item(
                BattleTypeButton(
                    value,
                    self.update,
                    label=label,
                    emoji=assets.get(emoji_id),
                    style=(
                        discord.ButtonStyle.success
                        if value == initial
                        else discord.ButtonStyle.secondary
                    ),
                )
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You must be the command invoker to do that.", ephemeral=True
            )
            return False
        return True

    async def update(self, interaction: discord.Interaction, battle_type: str):
        await interaction.response.defer()

        if battle_type not in self.player.statistics:
            if statistics := await vortex.get_partial_statistics(
                self.player.region,
                self.player.id,
                self.player.clan_role.clan_id,
                battle_type,
            ):
                stats, _, _ = statistics

                self.player.statistics[battle_type] = stats
            else:
                # TODO: log failed vortex update
                return

        for button in self.children:
            if isinstance(button, BattleTypeButton):
                button.style = (
                    discord.ButtonStyle.success
                    if button.value == battle_type
                    else discord.ButtonStyle.secondary
                )

        await self.message.edit(
            embed=PartialStatisticsEmbed(self.player, battle_type), view=self
        )


class PartialStatisticsEmbed(discord.Embed):
    def __init__(self, player: vortex.PartialPlayer, battle_type: str):
        stats = player.statistics[battle_type]
        clan = player.clan_role.clan

        # TODO sanitize inputs to prevent markdown
        super().__init__(
            title=f"{player.name}'s Stats (Partial)",
            description=(
                f"Battles: `{stats.battles_count}`\n"
                f"Wins: `{stats.wins_percentage:.2f}%`\n"
            ),
            timestamp=player.last_battle_time,
        )

        self.add_field(
            name="Clan",
            value=(
                f"Clan: [{clan.tag}] {clan.name}\n"
                f"Role: {player.clan_role.role.title().replace('_', ' ')}\n"
                f"Joined at: <t:{int(player.clan_role.joined_at.timestamp())}:D>\n"
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

        self.set_footer(text="Last battle at")


class StatsCog(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot

        self.load_seasons.start()

    @tasks.loop(hours=1)
    async def load_seasons(self):
        logger.info("Loading Seasons...")

        try:
            await wg_api.get_seasons()
            logger.info("Seasons Loaded")
        except Exception as e:
            logger.warning("Failed to load Seasons", exc_info=e)

            if not wg_api.seasons:
                import sys

                sys.exit(1)

    @app_commands.command(
        name="stats", description="PLACEHOLDER", extras={"category": "wows"}
    )
    async def stats(
        self,
        interaction: discord.Interaction,
        player: app_commands.Transform[vortex.Player, vortex.PlayerTransformer],
    ):
        if isinstance(player, vortex.PartialPlayer):
            embed = PartialStatisticsEmbed(player, "pvp")
            view = PartialStatisticsView(interaction.user.id, player)
            view.message = await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(":(")


async def setup(bot: Track):
    await bot.add_cog(StatsCog(bot))
