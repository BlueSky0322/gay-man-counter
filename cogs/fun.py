"""Fun / easter-egg commands.

NOTE: /gay is intentionally left out of /info — it's a secret.
"""

import colorsys
import logging
import random
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

import db

log = logging.getLogger(__name__)

ROLE_TTL = timedelta(hours=1)
WORDS = [
    'hai', 'faggot', 'pusswee', 'niggnigg', 'auntyaunty', 'gay', 'lou', 'fun',
    'noob', 'nigger', 'woman', 'man'
]

JAIL_TTL = timedelta(hours=1)
HORNI_ROLE = "horni"
JAIL_CHANNEL = "horny-jail"
SMIRK = "😏"
PINK = discord.Color.from_rgb(255, 105, 180)


def _pastel() -> discord.Color:
    """A soft random pastel: any hue, high lightness, gentle saturation."""
    r, g, b = colorsys.hls_to_rgb(
        random.random(),             # any hue
        random.uniform(0.78, 0.86),  # light
        random.uniform(0.40, 0.65),  # softly saturated
    )
    return discord.Color.from_rgb(int(r * 255), int(g * 255), int(b * 255))


class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # (guild_id, user_id) -> jail expiry (UTC datetime); read by the listener.
        self._jailed: dict[tuple, datetime] = {}
        self.cleanup_loop.start()

    def cog_unload(self):
        # Stop the loop cleanly on /reload so we don't stack duplicates.
        self.cleanup_loop.cancel()

    # ------------------------------------------------------------------ /gay
    @app_commands.command(name="gay", description="no u")
    @app_commands.guild_only()
    async def gay(self, interaction: discord.Interaction):
        # Punchline first so it's always instant, regardless of role perms.
        await interaction.response.send_message("no u")

        guild = interaction.guild
        member = interaction.user
        role_name = f"gay_{random.choice(WORDS)}"
        try:
            role = await guild.create_role(
                name=role_name, colour=_pastel(), reason="/gay"
            )
        except discord.HTTPException:
            return  # bot lacks Manage Roles — the punchline already landed

        # Record expiry BEFORE assigning, so the cleanup loop catches it even if
        # assignment fails for some reason.
        await db.add_temp_role(guild.id, role.id, member.id, discord.utils.utcnow() + ROLE_TTL)
        try:
            await member.add_roles(role, reason="/gay")
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------ /hornyjail
    @app_commands.command(
        name="hornyjail",
        description="Send user(s) to horny-jail: muted, deafened & smirked at for an hour.",
    )
    @app_commands.describe(
        user="Who to jail",
        user2="(optional) another victim",
        user3="(optional) another victim",
    )
    @app_commands.guild_only()
    async def hornyjail(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        user2: discord.Member | None = None,
        user3: discord.Member | None = None,
    ):
        await interaction.response.defer()
        guild = interaction.guild

        # What can we actually do here? Collect anything we're missing so we can
        # tell the user instead of failing silently.
        perms = guild.me.guild_permissions
        missing = [
            name
            for name, ok in (
                ("Manage Channels", perms.manage_channels),
                ("Manage Roles", perms.manage_roles),
                ("Move Members", perms.move_members),
                ("Mute Members", perms.mute_members),
                ("Deafen Members", perms.deafen_members),
            )
            if not ok
        ]

        # Dedupe targets, skip bots.
        targets, seen = [], set()
        for m in (user, user2, user3):
            if m and not m.bot and m.id not in seen:
                seen.add(m.id)
                targets.append(m)
        if not targets:
            await interaction.followup.send("No valid targets. 🤷")
            return

        role = await self._get_or_create_horni_role(guild)
        channel = await self._get_or_create_jail_channel(guild, role)

        expires = discord.utils.utcnow() + JAIL_TTL
        locked, role_only = [], []
        for m in targets:
            if role:
                try:
                    await m.add_roles(role, reason="horny jail")
                except discord.HTTPException:
                    pass
            moved = False
            if channel:
                try:
                    await m.move_to(channel, reason="horny jail")
                    moved = True
                except discord.HTTPException:
                    pass  # not connected to voice
            try:
                await m.edit(mute=True, deafen=True, reason="horny jail")
            except discord.HTTPException:
                pass
            # Track for the smirk listener + persist for cleanup across restarts.
            self._jailed[(guild.id, m.id)] = expires
            await db.add_jail(guild.id, m.id, role.id if role else None, expires)
            (locked if moved else role_only).append(m)

        embed = discord.Embed(
            title="🔒 Horny Jail",
            description=(
                f"Sentenced to **1 hour** — server-muted, deafened, branded "
                f"**@{HORNI_ROLE}**, and smirked {SMIRK} at on every message."
            ),
            color=PINK,
        )
        if locked:
            embed.add_field(
                name="🔇 Locked in voice",
                value=", ".join(m.mention for m in locked),
                inline=False,
            )
        if role_only:
            embed.add_field(
                name="📝 Role + smirk only (not in voice)",
                value=", ".join(m.mention for m in role_only),
                inline=False,
            )
        if missing:
            embed.add_field(
                name="⚠️ I'm missing permissions",
                value="Grant me: " + ", ".join(f"**{m}**" for m in missing),
                inline=False,
            )
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed)

    async def _get_or_create_horni_role(self, guild: discord.Guild):
        role = discord.utils.get(guild.roles, name=HORNI_ROLE)
        if role is None:
            try:
                role = await guild.create_role(
                    name=HORNI_ROLE, colour=PINK, reason="horny jail"
                )
            except discord.HTTPException:
                role = None
        return role

    async def _get_or_create_jail_channel(self, guild: discord.Guild, role):
        channel = discord.utils.get(guild.voice_channels, name=JAIL_CHANNEL)
        if channel is None:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=False, connect=False
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True, connect=True
                ),
            }
            if role:  # the horni role is the key into the private channel
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True, connect=True
                )
            try:
                channel = await guild.create_voice_channel(
                    JAIL_CHANNEL, overwrites=overwrites, reason="horny jail"
                )
            except discord.HTTPException:
                channel = None
        return channel

    @commands.Cog.listener("on_message")
    async def smirk_at_jailed(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        key = (message.guild.id, message.author.id)
        expiry = self._jailed.get(key)
        if not expiry:
            return
        if discord.utils.utcnow() < expiry:
            try:
                await message.add_reaction(SMIRK)
            except discord.HTTPException:
                pass
        else:
            # Sentence served — release now rather than waiting up to a full
            # cleanup tick (otherwise they'd stay muted/deafened for ~60s more).
            jail = await db.get_jail(message.guild.id, message.author.id)
            if jail:
                await self._release(jail)
            else:
                self._jailed.pop(key, None)  # record already gone; clear memory

    async def _unjail(self, jail: dict) -> bool:
        """Undo the mute/deafen/role for one jailed member.

        Returns True when it's safe to forget the sentence (released, or the
        guild/member is genuinely gone), and False on a transient failure so the
        next cleanup tick retries instead of leaving someone stuck muted.
        """
        guild = self.bot.get_guild(jail["guild_id"])
        if guild is None:
            return True  # not in this guild anymore — drop the dead record
        member = guild.get_member(jail["user_id"])
        if member is None:
            # The members intent isn't enabled, so the cache is sparse (and empty
            # right after a restart). Fall back to an explicit fetch rather than
            # silently skipping the un-mute and stranding the user.
            try:
                member = await guild.fetch_member(jail["user_id"])
            except discord.NotFound:
                return True   # member left the guild — nothing to undo
            except discord.HTTPException:
                return False  # transient — retry next tick
        try:
            await member.edit(mute=False, deafen=False, reason="jail over")
        except discord.HTTPException:
            pass
        role = guild.get_role(jail["role_id"]) if jail.get("role_id") else None
        if role:
            try:
                await member.remove_roles(role, reason="jail over")
            except discord.HTTPException:
                pass
        return True

    async def _release(self, jail: dict):
        """Unjail a member and, only if that succeeded, clear their records."""
        if await self._unjail(jail):
            self._jailed.pop((jail["guild_id"], jail["user_id"]), None)
            await db.delete_jail(jail["guild_id"], jail["user_id"])

    # ------------------------------------------------------------ background
    @tasks.loop(seconds=60)
    async def cleanup_loop(self):
        # Guard the whole body: an unexpected error (a malformed doc, a transient
        # Mongo failure) must not kill the loop — if it did, cleanup would stop
        # for good and jailed users would never be released.
        try:
            now = discord.utils.utcnow()
            # Expired gay_* roles — deleting the role also strips it from the wearer.
            for doc in await db.due_temp_roles(now):
                guild = self.bot.get_guild(doc["guild_id"])
                if guild is None:
                    await db.delete_temp_role(doc["_id"])  # not in guild — drop it
                    continue
                role = guild.get_role(doc["_id"])
                if role is not None:
                    try:
                        await role.delete(reason="gay role expired")
                    except discord.NotFound:
                        pass  # already gone
                    except discord.HTTPException:
                        continue  # transient — keep the record, retry next tick
                await db.delete_temp_role(doc["_id"])

            # Released jail sentences.
            for jail in await db.due_jails(now):
                await self._release(jail)
        except Exception:
            log.exception("cleanup_loop iteration failed; will retry next tick")

    @cleanup_loop.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()
        # Rebuild the in-memory jail set after a restart.
        for jail in await db.active_jails():
            self._jailed[(jail["guild_id"], jail["user_id"])] = jail["expires_at"]


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
