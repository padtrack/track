from typing import Optional

import asyncio
import json
import os
import secrets

from discord.ext import commands
from discord import app_commands, ui
import discord


DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../assets/private/roll_data.json"
)


@app_commands.guild_only()
class RollCog(commands.GroupCog, name="roll"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = {}
        self.lock = asyncio.Lock()

        # HACK: maybe don't use JSON
        def int_keys(x):
            if isinstance(x, dict):
                d = {}
                for k, v in x.items():
                    try:
                        d[int(k)] = v
                    except ValueError:
                        d[k] = v

                return d
            return x

        try:
            with open(DATA_PATH) as fp:
                self.data = json.load(fp, object_hook=int_keys)
        except FileNotFoundError:
            pass

    @app_commands.command(description="Opens a group roll session.")
    @app_commands.describe(
        description="Optional message appended to embed's description.",
        maximum="The maximum value (inclusive). Defaults to 100.",
        role1="User having this OR another listed role can roll.",
        role2="User having this OR another listed role can roll.",
        role3="User having this OR another listed role can roll.",
        role4="User having this OR another listed role can roll.",
        role5="User having this OR another listed role can roll.",
    )
    @app_commands.checks.has_permissions(manage_guild=True, manage_messages=True)
    async def start(
        self,
        interaction: discord.Interaction,
        description: str = "",
        maximum: int = 100,
        role1: Optional[discord.Role] = None,
        role2: Optional[discord.Role] = None,
        role3: Optional[discord.Role] = None,
        role4: Optional[discord.Role] = None,
        role5: Optional[discord.Role] = None,
    ):
        await interaction.response.defer()

        if maximum <= 1:
            await interaction.followup.send(f"maximum ({maximum}) should be > 1.")
            return

        async with self.lock:
            if interaction.channel_id in self.data:
                await interaction.followup.send(
                    "There is already a session active in this channel.\n"
                    "You can abort it using the close command."
                )
                return

            require = list(set(r.id for r in [role1, role2, role3, role4, role5] if r is not None))
            self.data[interaction.channel_id] = {
                "max": maximum,
                "roles": require,
                "rolls": {},
            }
            embed = discord.Embed(
                title="Group Roll Session",
                description=f"Values: `0` to `{maximum}`\n"
                            f"Required Roles: {' '.join(f'<@&{r}>' for r in require) if require else 'None'}\n"
                            f"{description}",
            )
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url)
            embed.set_footer(text="Type \"roll\" to roll")
            await interaction.followup.send(embed=embed)

            self.save()

    @app_commands.command(description="Closes the group roll session in this channel.")
    @app_commands.checks.has_permissions(manage_guild=True, manage_messages=True)
    async def close(self, interaction: discord.Interaction):
        await interaction.response.defer()

        async with self.lock:
            if interaction.channel_id not in self.data:
                await interaction.followup.send("No active session?")
                return

            rolls = self.data.pop(interaction.channel_id)["rolls"]

            if not rolls:
                await interaction.followup.send("Session cancelled.")
                return

            rolls = [
                (k, v) for k, v in sorted(rolls.items(), key=lambda i: i[1], reverse=True)
            ]
            high = rolls[0][1]
            winners = [k for k, v in rolls if v == high]

            if len(winners) > 1:
                await interaction.followup.send(
                    f"The result is a tie @ `{high}`: " + ", ".join(f"<@{uid}>" for uid in winners)
                )
                return

            await interaction.followup.send(
                f"<@{winners[0]}> wins with a roll of `{high}`."
            )

            self.save()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.content != "roll":
            return

        async with self.lock:
            if message.channel.id in self.data:
                data = self.data[message.channel.id]
                if message.author.id in data["rolls"]:
                    return

                if data["roles"]:
                    for role_id in data["roles"]:
                        if message.author.get_role(role_id):
                            break
                    else:
                        return

                roll = secrets.randbelow(data["max"] + 1)
                await message.reply(f"You rolled a `{roll}`.")
                data["rolls"][message.author.id] = roll

                self.save()

    def save(self):
        with open(DATA_PATH, "w") as fp:
            json.dump(self.data, fp)


async def setup(bot: commands.Bot):
    await bot.add_cog(RollCog(bot))
