"""Shared visual styling for the bot's embeds — one palette, one helper.

Keeping colors and the base embed in one place means every command looks like
it belongs to the same bot.
"""

import discord

BRAND = discord.Color(0x5865F2)    # blurple — neutral / info
SUCCESS = discord.Color(0x57F287)  # green  — added / logged
WARNING = discord.Color(0xFEE75C)  # yellow — not found / duplicate
DANGER = discord.Color(0xED4245)   # red    — removed / shame
GOLD = discord.Color(0xFFD700)     # gold   — leaderboards


def embed(title=None, description=None, color=BRAND) -> discord.Embed:
    """A base embed with a consistent timestamp footer."""
    e = discord.Embed(title=title, description=description, color=color)
    e.timestamp = discord.utils.utcnow()
    return e


def guild_thumb(interaction: discord.Interaction, embed: discord.Embed) -> None:
    """Set the guild's icon as the embed thumbnail, if it has one."""
    if interaction.guild and interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)
