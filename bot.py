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
        intents.members = True # populates member cache for /leaderboard
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

        # 3. Register slash commands (global by default; DEV_SYNC=1 in .env for
        #    instant single-guild syncing). Shared with /reload via sync_commands.
        log.info("Synced %s", await self.sync_commands())

    async def sync_commands(self) -> str:
        """Sync app commands per the current mode; returns a one-line summary.

        GLOBAL by default — commands work in every server the bot is in, but can
        take up to ~1h to appear/update. With DEV_SYNC=1 (and DEV_GUILD_ID set),
        syncs instantly to that one guild instead. Shared by startup AND /reload,
        so the two can never drift apart and cause duplicate commands.
        """
        dev_guild = os.environ.get("DEV_GUILD_ID")
        if os.environ.get("DEV_SYNC") and dev_guild:
            guild = discord.Object(id=int(dev_guild))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            # Keep the global scope empty so it can't duplicate the guild copies.
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            return f"{len(synced)} commands → guild {dev_guild} (instant)"

        synced = await self.tree.sync()
        if dev_guild:
            # Drop any leftover per-guild commands so they don't duplicate globals.
            guild = discord.Object(id=int(dev_guild))
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
        return f"{len(synced)} commands globally (~up to 1h to appear/update)"


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
