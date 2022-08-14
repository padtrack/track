import discord


async def reply(interaction: discord.Interaction, content, **kwargs):
    if interaction.response.is_done():
        return await interaction.followup.send(content, **kwargs)
    else:
        await interaction.response.send_message(content, **kwargs)
        return await interaction.original_response()
