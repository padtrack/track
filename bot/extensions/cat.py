import concurrent.futures
import random

from discord.ext import commands, tasks
from discord import app_commands
import discord
import tweepy

from bot.utils.logs import logger
from config import cfg


TWITTER_USERNAME = "unicouniuni3"
PER_FETCH = 25
GUILD_IDS = [
    339499487049547776,
    348633192972156928,
    430696180654014475,
    590412879119777799,
    718826317608517692,
    750943854215036950,
    990805648927240192,
]


executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
images = set()


def scrape():
    global images

    client = tweepy.Client(bearer_token=cfg.twitter.token)
    user = client.get_user(username=TWITTER_USERNAME).data
    next_token = None

    while True:
        response = client.get_users_tweets(
            user.id,
            expansions="attachments.media_keys",
            media_fields="url",
            max_results=PER_FETCH,
            pagination_token=next_token,
        )
        if not response.data:
            return

        for tweet in response.data:
            if not tweet.attachments:
                continue

            for media_key in tweet.attachments["media_keys"]:
                url = next(
                    media.url
                    for media in response.includes["media"]
                    if media.media_key == media_key
                )

                if not url:
                    continue

                if (pair := (tweet.id, url)) in images:
                    return

                images.add(pair)

        try:
            next_token = response.meta["next_token"]
        except KeyError:
            return


class CatCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot
        self.task_scrape.start()

    @tasks.loop(hours=4)
    async def task_scrape(self):
        global images

        logger.info("Loading Cats...")
        await self.bot.loop.run_in_executor(executor, scrape)
        logger.info("Cats loaded")

    @app_commands.command(name="cat", description="cat", extras={"category": "fun"})
    @app_commands.guilds(*GUILD_IDS)
    async def cat(self, interaction: discord.Interaction):
        global images

        if not images:
            await interaction.response.send_message("Cats unavailable.")
            return

        await interaction.response.send_message(
            random.choice([pair[1] for pair in images])
        )


async def setup(bot: commands.Bot):
    if not cfg.twitter.token:
        logger.warn("No twitter token found, Cat extension not loaded")
        return

    await bot.add_cog(CatCog(bot))
