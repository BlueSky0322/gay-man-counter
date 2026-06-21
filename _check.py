"""Offline sanity check: verifies Mongo connectivity and that every cog loads
and registers its commands — without connecting to Discord."""

import asyncio
import pathlib

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).with_name(".env"))

import db
from bot import INITIAL_EXTENSIONS, CounterBot


async def main():
    await db.ping()
    await db.ensure_indexes()
    print("MONGO_OK")

    bot = CounterBot()
    for ext in INITIAL_EXTENSIONS:
        await bot.load_extension(ext)
    cmds = sorted(c.qualified_name for c in bot.tree.walk_commands())
    print("COMMANDS:", ", ".join(cmds))
    await bot.close()


asyncio.run(main())
