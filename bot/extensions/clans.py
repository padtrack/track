from typing import Dict, List, Optional
import html

from discord.ext import commands, tasks
from discord import app_commands, ui
import discord
import tabulate

import api
from bot.extensions.stats import BattleTypeSelect
from bot.track import Track
from bot.utils import assets, db, wows
from bot.utils.logs import logger


class ClanEmbedCommon(discord.Embed):
    def __init__(self, clan: api.FullClan, **kwargs):
        super().__init__(color=int(clan.clan.color[1:], 16), **kwargs)


class ClanModeButton(ui.Button):
    LABELS = {
        "overview": "Overview",
        "members": "Members",
        "ratings": "Ratings",
    }

    def __init__(self, mode: str, is_active: bool, **kwargs):
        style = self.get_style(is_active)
        super().__init__(label=self.LABELS[mode], style=style, **kwargs)

        self.value = mode

    @staticmethod
    def get_style(is_active: bool):
        return (
            discord.ButtonStyle.success if is_active else discord.ButtonStyle.secondary
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.view.set_active(self.value)


class MembersPageButton(ui.Button):
    EMOJIS = ["1️⃣", "2️⃣", "3️⃣"]

    def __init__(self, page: int, is_active: bool, **kwargs):
        style = self.get_style(is_active)
        super().__init__(emoji=self.EMOJIS[page], style=style, **kwargs)

        self.value = page

    @staticmethod
    def get_style(is_active: bool):
        return (
            discord.ButtonStyle.primary if is_active else discord.ButtonStyle.secondary
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.view.set_active_page(self.value)


class ExpandedSelect(BattleTypeSelect):
    def __init__(self, **kwargs):
        super().__init__(default_only=True, **kwargs)

        self.add_option(
            label="Clan Battles",
            value="cvc",
            emoji=assets.get("EMOJI_CLAN_BATTLE"),
            default=False,
        )


class SeasonsSelect(ui.Select):
    # TODO: deal with CB Season 26 in 2024

    def __init__(self, region: str, **kwargs):
        super().__init__(min_values=1, max_values=1, options=[], **kwargs)

        for season in reversed(api.wg.seasons[region].data.values()):
            if 0 < season.season_id < 100:
                description = (
                    f"Tier: {season.ship_tier_min}"
                    if season.ship_tier_min == season.ship_tier_max
                    else f"Tiers: {season.ship_tier_min}-{season.ship_tier_max}"
                )

                self.add_option(
                    label=f"Season {season.season_id}: {season.name}",
                    value=str(season.season_id),
                    description=description,
                    default=season.season_id == api.wg.seasons[region].last_clan_season,
                )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        value = self.values[0]

        for option in self.options:
            option.default = option.value == value

        await self.view.update_season(int(value))


class ClanView(ui.View):
    MODES = ["overview", "members", "ratings"]

    def __init__(
        self,
        user_id: int,
        clan: api.FullClan,
        members_data: Dict[str, List[api.ClanMemberStatistics]],
        global_position: Optional[api.LadderPosition],
        local_position: Optional[api.LadderPosition],
    ):
        super().__init__(timeout=180)

        self.user_id = user_id
        self.clan = clan
        self.members_count = len(list(members_data.values())[0])
        self.members_data = members_data
        self.seasons_data: Dict[int, List[api.ClanMemberStatistics]] = {}
        self.global_position: Optional[api.LadderPosition] = global_position
        self.local_position: Optional[api.LadderPosition] = local_position
        self.message: Optional[discord.Message] = None

        self.mode_buttons = {
            mode: ClanModeButton(mode, mode == "overview") for mode in self.MODES
        }
        for button in self.mode_buttons.values():
            self.add_item(button)

        self.members_pages = (self.members_count - 1) // ClanMembersEmbed.PER_PAGE + 1
        self.page_buttons: List[MembersPageButton] = []
        self.selected_page: int = 0
        self.type_select: Optional[BattleTypeSelect] = None
        self.selected_battle_type: str = api.DEFAULT_BATTLE_TYPE
        self.seasons_select: Optional[SeasonsSelect] = None
        self.selected_season: int = api.wg.seasons[clan.region].last_clan_season

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You must be the command invoker to do that.", ephemeral=True
            )
            return False
        return True

    async def set_active(self, new_mode: str):
        for mode, button in self.mode_buttons.items():
            button.style = button.get_style(mode == new_mode)

        # clear even if last mode was members is intentional
        for button in self.page_buttons:
            self.remove_item(button)
        if self.type_select:
            self.remove_item(self.type_select)
            self.type_select = None
        if self.seasons_select:
            self.remove_item(self.seasons_select)
            self.seasons_select = None

        match new_mode:
            case "overview":
                embed = ClanEmbed(self.clan, self.members_data)
                await self.message.edit(embed=embed, view=self)
            case "members":
                if self.members_pages > 1:
                    for num in range(self.members_pages):
                        button = MembersPageButton(num, num == 0, row=1)
                        self.page_buttons.append(button)
                        self.add_item(button)

                self.selected_page = 0
                self.selected_battle_type = api.DEFAULT_BATTLE_TYPE
                self.type_select = ExpandedSelect(row=2)
                self.add_item(self.type_select)
                await self.update_members_embed()
            case "ratings":
                embed = ClanRatingsEmbed(
                    self.clan, self.global_position, self.local_position
                )
                await self.message.edit(embed=embed, view=self)

    async def update_members_embed(self):
        if self.selected_battle_type == "cvc":
            if self.selected_season not in self.seasons_data:
                if statistics := await api.get_clan_members(
                    self.clan.region, self.clan.clan.id, "cvc", self.selected_season
                ):
                    self.seasons_data[self.selected_season] = statistics
                else:
                    logger.error(
                        "Failed to update clan members "
                        f'(region "{self.clan.region}", '
                        f'id "{self.clan.clan.id}", '
                        f'battle_type "cvc" season "{self.selected_season}")'
                    )
                    return

            data = self.seasons_data[self.selected_season]
        else:
            data = self.members_data[self.selected_battle_type]

        embed = ClanMembersEmbed(
            self.clan, data, self.selected_page, self.members_pages
        )

        await self.message.edit(embed=embed, view=self)

    async def set_active_page(self, page: int):
        self.selected_page = page

        for button in self.page_buttons:
            button.style = MembersPageButton.get_style(button.value == page)

        await self.update_members_embed()

    async def update_battle_type(self, battle_type: str):
        if battle_type == "cvc":
            self.selected_season = api.wg.seasons[self.clan.region].last_clan_season

            if not self.seasons_select:
                self.seasons_select = SeasonsSelect(self.clan.region, row=3)
                self.add_item(self.seasons_select)
        else:
            if self.seasons_select:
                self.remove_item(self.seasons_select)
                self.seasons_select = None

            if battle_type not in self.members_data:
                if statistics := await api.get_clan_members(
                    self.clan.region,
                    self.clan.clan.id,
                    battle_type,
                ):
                    self.members_data[battle_type] = statistics
                else:
                    logger.error(
                        "Failed to update clan members "
                        f'(region "{self.clan.region}", '
                        f'id "{self.clan.clan.id}", '
                        f'battle_type "{battle_type}")'
                    )
                    return

        self.selected_battle_type = battle_type
        await self.update_members_embed()

    async def update_season(self, season: int):
        self.selected_season = season
        await self.update_members_embed()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        await self.message.edit(view=self)


class ClanEmbed(ClanEmbedCommon):
    PROGRESS_FOREGROUND = "▰"
    PROGRESS_BACKGROUND = "▱"
    DESCRIPTION_MAX_LINES = 20

    def __init__(
        self,
        clan: api.FullClan,
        members_data: Dict[str, List[api.ClanMemberStatistics]],
    ):
        clan_name = discord.utils.escape_markdown(f"[{clan.clan.tag}] {clan.clan.name}")
        super().__init__(
            clan,
            title=clan_name,
            description=f"Created: <t:{int(clan.clan.created_at.timestamp())}:D>\n"
            f"Achievements: `{len(clan.achievements)}`",
        )

        members = list(members_data.values())[0]
        names = sorted((member.name for member in members), key=str.lower)
        self.add_field(
            name=f"Members ({len(members)})",
            value=" • ".join(f"`{name}`" for name in names),
            inline=True,
        )

        all_modifiers = set()
        strings = []
        for building in clan.buildings.values():
            all_modifiers.update(building.modifiers)

            building_id = building.modifiers[0]
            building_type = api.wg.buildings[clan.region].type_of(building_id)
            total = api.wg.buildings[clan.region].upgrades_count(building_type)
            remaining = total - building.level
            name = building.name.replace(
                "_", " "
            ).title()  # TODO: look for real building names

            if building.level:
                strings.append(
                    f"{name} "
                    f"{self.PROGRESS_FOREGROUND * building.level}"
                    f"{self.PROGRESS_BACKGROUND * remaining}"
                )

        oil_remaining = 0
        for building in api.wg.buildings[clan.region].buildings.values():
            if building.building_id not in all_modifiers:
                oil_remaining += building.cost

        self.add_field(
            name="Base",
            value=f"Oil remaining to max: `{oil_remaining}`\n" + "\n".join(strings),
            inline=True,
        )

        # wargaming is really bad at handling apostrophes
        description = html.unescape(html.unescape(clan.clan.raw_description))
        description = discord.utils.escape_markdown(description)
        if description:
            self.add_field(
                name="Description", value=self.truncate(description), inline=False
            )

    def truncate(self, string: str):
        n = self.DESCRIPTION_MAX_LINES
        start = string.find("\n")

        while start >= 0 and n > 0:
            start = string.find("\n", start + 1)
            n -= 1

        if not n and start != -1 and start != len(string):
            return string[:start] + "\n... (truncated)"
        return string


class ClanMembersEmbed(ClanEmbedCommon):
    PER_PAGE = 17  # (17 * 3 = 51) > 50
    KEYS = [
        "name",
        "wins_percentage",
        "damage_per_battle",
        "frags_per_battle",
        "battles_count",
    ]
    HEADERS = ["Name", "W/B", "D/B", "F/B", "BTL"]
    FLOAT_FMT = ["", ".1f", ".0f", ".2f", ".0f"]

    def __init__(
        self,
        clan: api.FullClan,
        members: List[api.ClanMemberStatistics],
        page: int,
        max_pages: int,
    ):
        title = (
            f"Clan Members ({page + 1}/{max_pages})"
            if max_pages > 1
            else "Clan Members"
        )
        description = f"""```{self.get_table(members, page)}```"""
        super().__init__(
            clan,
            title=title,
            description=description,
        )

        self.set_author(
            icon_url=assets.get("WG_LOGO"), name=f"[{clan.clan.tag}] {clan.clan.name}"
        )

    def get_table(self, members: List[api.ClanMemberStatistics], page: int) -> str:
        start = page * self.PER_PAGE
        end = (page + 1) * self.PER_PAGE
        # end is not inclusive
        data = [
            [getattr(member, key) for key in self.KEYS]
            for count, member in enumerate(members)
            if start <= count < end
        ]

        return tabulate.tabulate(data, headers=self.HEADERS, floatfmt=self.FLOAT_FMT)


class ClanRatingsEmbed(ClanEmbedCommon):
    RATING_NAMES = ["Alpha", "Bravo"]

    def __init__(
        self,
        clan: api.FullClan,
        global_position: api.LadderPosition,
        local_position: api.LadderPosition,
    ):
        current_season = api.wg.seasons[clan.region].last_clan_season

        if not global_position:
            description = "Clan does not have a ladder position.\n"
        else:
            description = (
                f"Global Position: `{global_position.rank}`\n"
                f"Local Position: `{local_position.rank}`\n"
            )

        if last := clan.wows_ladder.last_battle_at:
            description += f"Last Battle: <t:{int(last.timestamp())}:D>\n"

        super().__init__(
            clan,
            title=f"Clan Ratings (Season {current_season})",
            description=description,
        )

        self.set_author(
            icon_url=assets.get("WG_LOGO"), name=f"[{clan.clan.tag}] {clan.clan.name}"
        )

        current = []

        for rating in clan.wows_ladder.ratings:
            if rating.season_number == current_season:
                current.append(rating)

        current = sorted(current, key=lambda x: x.team_number)

        for rating in current:
            wins, battles = rating.wins_count, rating.battles_count
            wins_rate = 100 * wins / battles if rating.battles_count else 0

            last_win = (
                f"<t:{int(rating.last_win_at.timestamp())}:D>"
                if rating.last_win_at
                else "`None`"
            )

            self.insert_field_at(
                index=rating.team_number,
                name=self.RATING_NAMES[rating.team_number - 1],
                value=(
                    f"Battles: `{battles}`\n"
                    f"Wins: `{wins}` "
                    f"(`{wins_rate:.2f}%`)\n"
                    f"Win Streak: `{rating.current_winning_streak}` "
                    f"(Record: `{rating.longest_winning_streak}`)\n"
                    f"Rating: `{rating.public_rating}` "
                    f"(Record: `{rating.max_position.public_rating}`)\n"
                    f"Last Win: {last_win}\n"
                ),
                inline=False,
            )


class ClansCog(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot

        self.load_seasons.start()

    @tasks.loop(hours=1)
    async def load_seasons(self):
        logger.info("Loading Buildings...")

        try:
            await api.wg.get_buildings()
            logger.info("Buildings Loaded")
        except Exception as e:
            logger.warning("Failed to load Buildings", exc_info=e)

            if not api.wg.buildings:
                import sys

                sys.exit(1)

    @staticmethod
    async def send_clan(interaction: discord.Interaction, clan: api.FullClan):
        if clan is None:
            await interaction.followup.send("No clans found.")
            return

        if not (members := await api.get_clan_members(clan.region, clan.clan.id)):
            await interaction.followup.send("Failed to fetch clan members.")
            return

        members_data = {api.DEFAULT_BATTLE_TYPE: members}
        global_position = await api.get_ladder_position(
            clan.region, clan.clan.id, local=False
        )
        local_position = await api.get_ladder_position(
            clan.region, clan.clan.id, local=True
        )
        view = ClanView(
            interaction.user.id, clan, members_data, global_position, local_position
        )
        view.message = await interaction.followup.send(
            embed=ClanEmbed(clan, members_data), view=view
        )

    # noinspection PyUnusedLocal
    @app_commands.command(
        name="clan", description="Fetches clan statistics.", extras={"category": "wows"}
    )
    @app_commands.describe(
        region="The WoWS region to search clans in.",
        clan="The clan tag or name to search for.",
    )
    async def clan(
        self,
        interaction: discord.Interaction,
        region: Optional[wows.Regions],
        clan: app_commands.Transform[api.FullClan, api.ClanTransformer],
    ):
        await self.send_clan(interaction, clan)

    @app_commands.command(
        name="myclan",
        description="Shortcut to /clan for linked users.",
        extras={"category": "wows"},
    )
    async def my_clan(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user = await db.User.get_or_create(id=interaction.user.id)

        if not user.wg_id:
            await interaction.response.send_message(
                "You must be linked to use this command! See `/link`."
            )
            return

        player = await api.get_player(user.wg_region, user.wg_id, user.wg_ac)

        if not player.clan_role:
            await interaction.followup.send("You aren't in a clan.")
            return

        clan = await api.get_clan(player.region, player.clan_role.clan_id)
        await self.send_clan(interaction, clan)


async def setup(bot: Track):
    await bot.add_cog(ClansCog(bot))
