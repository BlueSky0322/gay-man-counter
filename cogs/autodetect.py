"""Auto-detect: watch chat and log a mention whenever a tracked name appears.

Tunables are the three constants below — tweak and `/reload`.
"""

import re
import time

import discord
from discord.ext import commands

import db

REACT_EMOJI = "🏳️‍🌈"        # reaction added to a message that triggered a count
COOLDOWN_SECONDS = 10      # per (user, name): ignore repeats within this window
CACHE_TTL_SECONDS = 30     # how long the per-guild name list is cached in memory


def _ascii_word(ch: str) -> bool:
    """A char that ASCII-delimits words (letters, digits, underscore).

    Deliberately ASCII-only: CJK and other scripts are excluded so names in
    those scripts match as substrings. Python's `\\b` never fires between two
    CJK chars (they're all `\\w`), which is why bare `\\b` boundaries silently
    fail to detect e.g. 阿强 inside 今天阿强很帅.
    """
    return ch.isascii() and (ch.isalnum() or ch == "_")


def _name_pattern(name: str) -> str:
    """An escaped name with word boundaries only on its ASCII-word edges.

    'Dave' won't fire inside 'Davenport'; CJK names like '阿强' match even when
    embedded in running CJK text; 'C++' matches despite the trailing '+'.
    """
    esc = re.escape(name)
    left = r"(?<![A-Za-z0-9_])" if name and _ascii_word(name[0]) else ""
    right = r"(?![A-Za-z0-9_])" if name and _ascii_word(name[-1]) else ""
    return f"{left}{esc}{right}"


class AutoDetect(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> {"expires": float, "regex": Pattern|None, "names": set[str]}
        self._cache: dict[int, dict] = {}
        # (guild_id, user_id, name_lower) -> last trigger time (monotonic seconds)
        self._cooldowns: dict[tuple, float] = {}

    async def _name_index(self, guild_id: int):
        """Cached (regex|None, name_lowers set, {user_id: name_lower}) for a guild.

        Rebuilt at most once per CACHE_TTL_SECONDS, so a newly /add-ed name — or a
        newly tagged member — starts being detected within that window.
        """
        now = time.monotonic()
        entry = self._cache.get(guild_id)
        if entry is None or entry["expires"] < now:
            people = await db.list_persons(guild_id)
            names = {p["name_lower"] for p in people}
            # Persons added by tagging a member carry a user_id, so we can also
            # catch when that member is @mentioned (not just when their name is typed).
            mentions = {
                p["user_id"]: p["name_lower"] for p in people if p.get("user_id")
            }
            if names:
                # Per-name boundaries (see _name_pattern): whole-word for ASCII
                # names, substring for CJK/punctuation-edged names.
                pattern = "(" + "|".join(_name_pattern(n) for n in names) + ")"
                regex = re.compile(pattern, re.IGNORECASE)
            else:
                regex = None
            entry = {
                "expires": now + CACHE_TTL_SECONDS,
                "regex": regex,
                "names": names,
                "mentions": mentions,
            }
            self._cache[guild_id] = entry
        return entry["regex"], entry["names"], entry["mentions"]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bots (including ourselves) and DMs.
        if message.author.bot or message.guild is None:
            return

        regex, names, mentions = await self._name_index(message.guild.id)
        if regex is None and not mentions:
            return

        # Every tracked person present — typed names + @mentions of tagged
        # members — each counted at most once.
        found = set()
        if regex is not None:
            found |= {m.lower() for m in regex.findall(message.content)} & names
        for u in message.mentions:
            name_lower = mentions.get(u.id)
            if name_lower:
                found.add(name_lower)
        if not found:
            return

        now = time.monotonic()
        logged_any = False
        for name_lower in found:
            key = (message.guild.id, message.author.id, name_lower)
            if now - self._cooldowns.get(key, 0.0) < COOLDOWN_SECONDS:
                continue  # this user already triggered this name recently
            prev, _ = await db.log_mention(
                message.guild.id, name_lower, message.author.id
            )
            if prev is not None:  # None only if the name was removed mid-flight
                # Arm the cooldown only once the mention is actually recorded, so
                # a failed or no-op log doesn't suppress the next real attempt.
                self._cooldowns[key] = now
                logged_any = True

        if logged_any:
            try:
                await message.add_reaction(REACT_EMOJI)
            except discord.HTTPException:
                pass  # missing permission, message deleted, etc. — counting still worked


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoDetect(bot))
