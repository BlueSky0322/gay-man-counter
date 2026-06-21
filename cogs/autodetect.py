"""Auto-detect: watch chat and log a mention whenever a tracked name appears.

Tunables are the three constants below — tweak and `/reload`.
"""

import re
import time

import discord
from discord.ext import commands

import db

REACT_EMOJI = "📢"        # reaction added to a message that triggered a count
COOLDOWN_SECONDS = 60      # per (user, name): ignore repeats within this window
CACHE_TTL_SECONDS = 30     # how long the per-guild name list is cached in memory


class AutoDetect(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> {"expires": float, "regex": Pattern|None, "names": set[str]}
        self._cache: dict[int, dict] = {}
        # (guild_id, user_id, name_lower) -> last trigger time (monotonic seconds)
        self._cooldowns: dict[tuple, float] = {}

    async def _name_index(self, guild_id: int):
        """Cached (compiled_regex|None, set_of_name_lowers) for a guild.

        Rebuilt at most once per CACHE_TTL_SECONDS, so a newly /add-ed name
        starts being detected within that window.
        """
        now = time.monotonic()
        entry = self._cache.get(guild_id)
        if entry is None or entry["expires"] < now:
            names = {p["name_lower"] for p in await db.list_persons(guild_id)}
            if names:
                # \b...\b = whole-word match, so "Dave" won't fire on "Davenport".
                pattern = r"\b(" + "|".join(re.escape(n) for n in names) + r")\b"
                regex = re.compile(pattern, re.IGNORECASE)
            else:
                regex = None
            entry = {"expires": now + CACHE_TTL_SECONDS, "regex": regex, "names": names}
            self._cache[guild_id] = entry
        return entry["regex"], entry["names"]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bots (including ourselves) and DMs.
        if message.author.bot or message.guild is None:
            return

        regex, names = await self._name_index(message.guild.id)
        if regex is None:
            return

        # Every tracked name present in the message (each counted at most once).
        found = {m.lower() for m in regex.findall(message.content)} & names
        if not found:
            return

        now = time.monotonic()
        logged_any = False
        for name_lower in found:
            key = (message.guild.id, message.author.id, name_lower)
            if now - self._cooldowns.get(key, 0.0) < COOLDOWN_SECONDS:
                continue  # this user already triggered this name recently
            self._cooldowns[key] = now
            prev, _ = await db.log_mention(
                message.guild.id, name_lower, message.author.id
            )
            if prev is not None:  # None only if the name was removed mid-flight
                logged_any = True

        if logged_any:
            try:
                await message.add_reaction(REACT_EMOJI)
            except discord.HTTPException:
                pass  # missing permission, message deleted, etc. — counting still worked


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoDetect(bot))
