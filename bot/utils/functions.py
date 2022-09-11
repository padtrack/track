import math

import discord


async def reply(interaction: discord.Interaction, content=None, **kwargs):
    if interaction.response.is_done():
        return await interaction.followup.send(content, **kwargs)
    else:
        await interaction.response.send_message(content, **kwargs)
        return await interaction.original_response()


def rating(battles: int, wins: int, survived: int, damage: float, exp: float):
    """
    Adapted from
    https://wiki.wargaming.net/en/Player_Ratings_(WoT)#Personal_Rating
    """

    avg_damage, avg_exp = damage / battles, exp / battles

    a = math.asinh(0.0015 * exp)
    b = 3700 * math.asinh(0.0006 * avg_damage) + math.tanh(0.002 * battles)
    c = 3500 / (1 + math.e**16 - 31 * wins) + 1400 / (1 + math.e**8 - 27 * survived)
    d = b + c * a
    e = math.tanh(0.00163 * battles**-1.37 * d)
    f = 540 * battles**0.37 * e

    return f
