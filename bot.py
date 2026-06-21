import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

import db

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("counterbot")

INITIAL_EXTENSIONS = (
    "cogs.board",
    "cogs.admin",
    "cogs.general",
    "cogs.autodetect",
    "cogs.fun",
)


class CounterBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # required to read chat for auto-detect
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Record when we came online, for the /ping uptime display.
        self.start_time = discord.utils.utcnow()

        # 1. Make sure the database is reachable before we go online.
        await db.ping()
        await db.ensure_indexes()
        log.info("Connected to MongoDB.")

        # 2. Load feature modules (cogs).
        for ext in INITIAL_EXTENSIONS:
            await self.load_extension(ext)
            log.info("Loaded extension: %s", ext)

        # 3. Register slash commands. If DEV_GUILD_ID is set, sync to that one
        #    server for instant updates; otherwise sync globally (slower to
        #    propagate, but available everywhere the bot is added).
        dev_guild = os.environ.get("DEV_GUILD_ID")
        if dev_guild:
            guild = discord.Object(id=int(dev_guild))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d commands to dev guild %s (instant).", len(synced), dev_guild)
            # Clear any stale GLOBAL commands (e.g. an old /ping) so they don't
            # show up as duplicates alongside the guild copies.
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
        else:
            synced = await self.tree.sync()
            log.info("Synced %d commands globally (~up to 1h to appear).", len(synced))


bot = CounterBot()


@bot.event
async def on_ready():
    log.info("Logged in as %s (id: %s)", bot.user, bot.user.id)


async def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is missing. Add it to your .env file.")
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
