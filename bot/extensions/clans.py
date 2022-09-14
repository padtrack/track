from typing import Dict, List, Optional
import html

from discord.ext import commands, tasks
from discord import app_commands, ui
import discord
import tabulate

import api
from bot.extensions.stats import BattleTypeSelect
from bot.track import Track
from bot.utils import assets, wows
from bot.utils.logs import logger


class ClanEmbedCommon(discord.Embed):
    DEFAULT_COLOR = 0xFFFFFF

    def __init__(self, clan: api.FullClan, **kwargs):
        color = self.DEFAULT_COLOR if not clan.wows_ladder else clan.wows_ladder.color
        super().__init__(color=color, **kwargs)


class ClanModeButton(ui.Button):
    LABELS = {
        "overview": "Overview",
        "members": "Members",
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


class ClanView(ui.View):
    MODES = ["overview", "members"]

    def __init__(
        self,
        clan: api.FullClan,
        members_data: Dict[str, List[api.ClanMemberStatistics]],
    ):
        super().__init__(timeout=180)

        self.clan = clan
        self.members_count = len(list(members_data.values())[0])
        self.members_data = members_data
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

    async def set_active(self, new_mode: str):
        for mode, button in self.mode_buttons.items():
            button.style = button.get_style(mode == new_mode)

        # clear even if last mode was members is intentional
        for button in self.page_buttons:
            self.remove_item(button)
        if self.type_select:
            self.remove_item(self.type_select)

        match new_mode:
            case "overview":
                embed = ClanEmbed(self.clan, self.members_data)
                await self.message.edit(embed=embed, view=self)
            case "members":
                for num in range(self.members_pages):
                    button = MembersPageButton(num, num == 0)
                    self.page_buttons.append(button)
                    self.add_item(button)

                self.selected_page = 0
                self.type_select = BattleTypeSelect(default_only=True)
                self.add_item(self.type_select)
                await self.update_members_embed()

    async def update_members_embed(self):
        await self.message.edit(
            embed=ClanMembersEmbed(
                self.clan,
                self.members_data[self.selected_battle_type],
                self.selected_page,
            ),
            view=self,
        )

    async def set_active_page(self, page: int):
        self.selected_page = page

        for button in self.page_buttons:
            button.style = MembersPageButton.get_style(button.value == page)

        await self.update_members_embed()

    async def update_battle_type(self, battle_type: str):
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
            name="Members",
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
        "days_in_clan",
    ]
    HEADERS = ["Name", "W/B", "D/B", "F/B", "Days"]
    FLOAT_FMT = ["", ".1f", ".0f", ".2f", ".0f"]

    def __init__(
        self, clan: api.FullClan, members: List[api.ClanMemberStatistics], page: int
    ):
        super().__init__(
            clan,
            title=f"Clan Members (Page {page + 1})",
            description=f"""```{self.get_table(members, page)}```""",
        )

        clan_name = discord.utils.escape_markdown(f"[{clan.clan.tag}] {clan.clan.name}")
        self.set_author(icon_url=assets.get("WG_LOGO"), name=clan_name)

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
        if clan is None:
            await interaction.followup.send("No clans found.")
            return

        if not (members := await api.get_clan_members(clan.region, clan.clan.id)):
            await interaction.followup.send("Failed to fetch clan members.")
            return

        members_data = {api.DEFAULT_BATTLE_TYPE: members}
        view = ClanView(clan, members_data)
        view.message = await interaction.followup.send(
            embed=ClanEmbed(clan, members_data), view=view
        )


async def setup(bot: Track):
    await bot.add_cog(ClansCog(bot))
