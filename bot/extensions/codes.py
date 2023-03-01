from __future__ import annotations
from typing import Dict, List, Optional, Set

import collections
import csv
import io
import json
import os
import re
import time

from discord.ext import commands
from discord import app_commands, ui
import discord


DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../assets/private/cc_data.json"
)
CODES_PATTERN = re.compile("(CC[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5})")
GUILD_ID = 395502204695609345


class CodesModal(ui.Modal):
    def __init__(self, cog: CodesCog, category: str):
        super().__init__(
            title="Add Codes to Pool",
        )

        self.cog: CodesCog = cog
        self.category: str = category

        self.input = ui.TextInput(
            label="Input",
            style=discord.TextStyle.long,
            placeholder="Paste here!",
            required=True,
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.process_codes(interaction, self.category, self.input.value)


class DefinitionsModal(ui.Modal):
    TIERS = 4  # includes 0

    def __init__(self, cog: CodesCog):
        super().__init__(title="Definitions")

        self.cog: CodesCog = cog
        self.text_inputs: List[ui.TextInput] = []

        placeholder = " ".join(CodesCog.CODE_TYPES)
        for tier in range(self.TIERS):
            self.text_inputs.append(
                ui.TextInput(
                    label=f"Tier {tier}",
                    style=discord.TextStyle.short,
                    placeholder=placeholder,
                    required=True,
                )
            )
            self.add_item(self.text_inputs[tier])

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.process_definitions(
            interaction, [text_input.value for text_input in self.text_inputs]
        )


class TemplateModal(ui.Modal):
    def __init__(self, cog: CodesCog):
        super().__init__(title="Template")

        self.cog: CodesCog = cog
        self.input = ui.TextInput(
            label="Input",
            style=discord.TextStyle.long,
            placeholder="Paste here!",
            required=True,
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        view = TemplateView(self.cog, self.input.value)
        codes = {
            t: ["CC1SOME-2FAKE-3CODE"] * self.cog.definitions[2][index]
            for index, t in enumerate(self.cog.CODE_TYPES)
        }

        await interaction.response.send_message(
            self.cog.format_message(self.input.value, codes),
            embed=discord.Embed(
                title="Preview",
                description="Generated for Tier 2/0. Does this look correct?",
            ),
            view=view,
        )
        view.message = await interaction.original_response()


class TemplateView(ui.View):
    def __init__(self, cog: CodesCog, template: str):
        super().__init__(timeout=180.0)

        self.cog: CodesCog = cog
        self.template: str = template
        self.message: Optional[discord.Message] = None

    @ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, _button: discord.Button):
        await self.disable()
        await self.cog.distribute_codes(interaction, self.template)

    async def on_timeout(self) -> None:
        await self.disable()

    async def disable(self) -> None:
        # noinspection PyUnresolvedReferences
        self.children[0].disabled = True
        await self.message.edit(view=self)


class ContributorsView(ui.View):
    def __init__(self, cog: CodesCog, contributors: Dict[int, List[int, int]]):
        super().__init__(timeout=180.0)

        self.cog: CodesCog = cog
        self.contributors: Dict[int, List[int, int]] = contributors
        self.message: Optional[discord.Message] = None

    @ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, _button: discord.Button):
        await self.disable()
        await self.cog.process_contributors(interaction, self.contributors)

    async def on_timeout(self) -> None:
        await self.disable()

    async def disable(self) -> None:
        # noinspection PyUnresolvedReferences
        self.children[0].disabled = True
        await self.message.edit(view=self)


# https://stackoverflow.com/a/8230505
class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)


@app_commands.guilds(GUILD_ID)
class CodesCog(commands.GroupCog, name="codes"):
    CODE_TYPES = [
        "CC",
        "EVENT",
        "CAMO",
    ]
    CODE_TYPES_CHOICES = [app_commands.Choice(name=t, value=t) for t in CODE_TYPES]
    DEFAULT_DEFINITIONS = [[0, 0, 0], [5, 5, 15], [7, 7, 20], [14, 14, 25]]

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.pools: Dict[str, Set[str]] = {t: set() for t in CodesCog.CODE_TYPES}
        self.contributors: Dict[int, List[int, int, str]] = {}
        self.pools_updated: Optional[float] = None
        self.contributors_updated: Optional[float] = None
        self.definitions: List[List[int]] = CodesCog.DEFAULT_DEFINITIONS

        try:
            with open(DATA_PATH) as fp:
                data = json.load(fp)

                for t, codes in data["pools"].items():
                    self.pools[t].update(codes)

                self.contributors.update(data["contributors"])
                self.pools_updated = data["pools_updated"]
                self.contributors_updated = data["contributors_updated"]
                self.definitions = data["definitions"]
        except FileNotFoundError:
            pass

    # noinspection SpellCheckingInspection
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id not in [
            180431943664402432,  # Gaishu
            362357860530651137,  # Ahskance
            376545699833184268,  # Boggzy
        ]:
            interaction.extras["ignore_error"] = True
            await interaction.response.send_message("You can't use this command.")
            return False
        else:
            return True

    @staticmethod
    def format_message(template: str, assigned_codes: Dict[str, List[str]]):
        kwargs = {t: " • ".join(codes) for t, codes in assigned_codes.items()}
        return template.format(**kwargs)

    @property
    def required_to_distribute(self) -> collections.Counter:
        counts = collections.Counter()
        for tier, multi_tier in self.contributors.values():
            for t, count in zip(CodesCog.CODE_TYPES, self.definitions[tier]):
                counts[t] += count
            for t, count in zip(CodesCog.CODE_TYPES, self.definitions[multi_tier]):
                counts[t] += count

        return counts

    @property
    def data(self):
        return {
            "pools": self.pools,
            "contributors": self.contributors,
            "pools_updated": self.pools_updated,
            "contributors_updated": self.contributors_updated,
            "definitions": self.definitions,
        }

    def save(self):
        with open(DATA_PATH, "w") as fp:
            json.dump(
                self.data,
                fp,
                cls=SetEncoder,
            )

    async def process_codes(
        self, interaction: discord.Interaction, category: str, string: str
    ):
        matches = re.findall(CODES_PATTERN, string)

        before = len(self.pools[category])
        self.pools[category].update(matches)
        self.pools_updated = time.time()
        self.save()
        after = len(self.pools[category])

        await interaction.response.send_message(
            f"Found `{len(matches)}` codes, "
            f'pool "{category}" `{before}` -> `{after}`.'
        )

    async def process_contributors(
        self,
        interaction: discord.Interaction,
        contributors: Dict[int, List[int, int]],
    ):
        before = len(self.contributors)
        self.contributors = contributors
        self.contributors_updated = time.time()
        self.save()
        after = len(self.contributors)

        await interaction.response.send_message(
            f"Contributors `{before}` -> `{after}`."
        )

    async def process_definitions(
        self, interaction: discord.Interaction, strings: List[str]
    ):
        definitions = []

        for tier, string in enumerate(strings):
            tokens = string.split()

            if len(tokens) != len(CodesCog.CODE_TYPES):
                await interaction.response.send_message(
                    f"Invalid number of tokens for Tier {tier}."
                )
                return

            try:
                definitions.append([int(token) for token in tokens])
            except ValueError as e:
                await interaction.response.send_message(str(e))

        self.definitions = definitions
        self.save()

        await interaction.response.send_message(f"Definitions updated.")

    async def distribute_codes(self, interaction: discord.Interaction, template: str):
        await interaction.response.defer()

        pools: Dict[str, List[str]] = {t: list(pool) for t, pool in self.pools.items()}

        assigned_codes: Dict[int, Dict[str, List[str]]] = {}
        failed: List[int] = []

        prefix = collections.Counter()

        for user_id, (tier, multi_tier) in self.contributors.items():
            try:
                user = await self.bot.fetch_user(user_id)
            except (discord.NotFound, discord.HTTPException):
                continue

            try:
                amounts = collections.Counter()
                for index, t in enumerate(CodesCog.CODE_TYPES):
                    amounts[t] += self.definitions[tier][index]
                    amounts[t] += self.definitions[multi_tier][index]

                codes: Dict[str, List[str]] = {
                    t: pools[t][prefix[t] : prefix[t] + amounts[t]]
                    for t in CodesCog.CODE_TYPES
                }
                assigned_codes[user_id] = codes
                prefix += amounts

                if sum(amounts.values()):
                    message = self.format_message(template, codes)
                    if len(message) <= 2000:
                        await user.send(message)
                    else:
                        with io.BytesIO(bytes(message, encoding="utf-8")) as fp:
                            file = discord.File(fp, filename="codes.txt")
                            await user.send(file=file)
            except (discord.HTTPException, discord.Forbidden):
                failed.append(user_id)

        for t in CodesCog.CODE_TYPES:
            pools[t] = pools[t][prefix[t] :]

            for user_id in failed:
                pools[t].extend(assigned_codes[user_id][t])

        self.pools = {t: set(pool) for t, pool in pools.items()}
        self.pools_updated = time.time()
        self.save()

        results = {"assigned_codes": assigned_codes, "failed": failed}

        try:
            with io.BytesIO(
                bytes(json.dumps(results, indent=4, cls=SetEncoder), encoding="utf-8")
            ) as fp:
                file = discord.File(fp, filename="results.json")
                await interaction.followup.send("Done!", file=file)
        except (discord.HTTPException, discord.NotFound, discord.Forbidden):
            path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                f"../assets/private/results_{interaction.id}.json",
            )
            with open(path, "w") as fp:
                json.dump(results, fp)

    @app_commands.command(description="Export internal data.")
    async def export(self, interaction: discord.Interaction):
        with io.BytesIO(
            bytes(json.dumps(self.data, indent=4, cls=SetEncoder), encoding="utf-8")
        ) as fp:
            file = discord.File(fp, filename="export.json")
            await interaction.response.send_message(file=file)

    @app_commands.command(description="Clear all codes from a pool.")
    @app_commands.choices(category=CODE_TYPES_CHOICES)
    async def clear(self, interaction: discord.Interaction, category: str) -> None:
        self.pools[category].clear()
        self.save()
        await interaction.response.send_message(f'Pool "{category}" cleared.')

    @app_commands.command(description="Add codes to a pool with a paste.")
    @app_commands.choices(category=CODE_TYPES_CHOICES)
    async def paste(self, interaction: discord.Interaction, category: str) -> None:
        await interaction.response.send_modal(CodesModal(self, category))

    @app_commands.command(description="Add codes to a pool with a CSV file.")
    @app_commands.choices(category=CODE_TYPES_CHOICES)
    async def csv(
        self,
        interaction: discord.Interaction,
        category: str,
        attachment: discord.Attachment,
    ) -> None:
        fp = io.BytesIO()
        await attachment.save(fp)
        await self.process_codes(interaction, category, fp.read().decode("utf-8"))

    @app_commands.command(description="Update contributors list.")
    async def contributors(
        self, interaction: discord.Interaction, attachment: discord.Attachment
    ) -> None:
        await interaction.response.defer()

        fp = io.BytesIO()
        await attachment.save(fp)
        guild = await self.bot.fetch_guild(GUILD_ID)
        contributors = {}

        with io.TextIOWrapper(fp, encoding="utf-8-sig") as text:
            reader = csv.reader(text, delimiter=";")

            for row in reader:
                try:
                    user_id = int(row[0])
                    tier = int(row[1]) if row[1] else 0
                    multi_tier = int(row[2]) if row[2] else 0
                except ValueError as e:
                    await interaction.followup.send(str(e))
                    return

                contributors[user_id] = tier, multi_tier

            contributors_ids = list(contributors.keys())
            chunks = [
                contributors_ids[x : x + 100]
                for x in range(0, len(contributors_ids), 100)
            ]
            results = []

            for chunk in chunks:
                query = await guild.query_members(user_ids=chunk)
                results.extend(user.id for user in query)

            skipped = [user_id for user_id in contributors if user_id not in results]
            contributors = {k: v for k, v in contributors.items() if k not in skipped}

        view = ContributorsView(self, contributors)

        message = f"Found `{len(contributors)}` contributors. "
        if skipped:
            message += " Skipped:\n"
            message += "\n".join(f"- {user_id}" for user_id in skipped)

        view.message = await interaction.followup.send(
            message,
            view=view,
        )

    @app_commands.command(description="View required pool sizes to distribute.")
    async def required(self, interaction: discord.Interaction):
        counts = self.required_to_distribute
        message = "\n".join(f"{t}: `{counts[t]}`" for t in CodesCog.CODE_TYPES)

        await interaction.response.send_message(message)

    @app_commands.command(description="Change tier definitions.")
    async def define(self, interaction: discord.Interaction):
        await interaction.response.send_modal(DefinitionsModal(self))

    @app_commands.command(description="Distributes codes with a given template.")
    async def distribute(self, interaction: discord.Interaction):
        counts = self.required_to_distribute

        for t in CodesCog.CODE_TYPES:
            if len(self.pools[t]) < counts[t]:
                await interaction.response.send_message(
                    f'Pool "{t}" does not have enough codes.'
                )
                return

        await interaction.response.send_modal(TemplateModal(self))


async def setup(bot: commands.Bot):
    await bot.add_cog(CodesCog(bot))
