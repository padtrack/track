import discord


async def reply(interaction: discord.Interaction, content, **kwargs):
    if interaction.response.is_done():
        return await interaction.followup.send(content, **kwargs)
    else:
        return await interaction.response.send_message(content, **kwargs)
