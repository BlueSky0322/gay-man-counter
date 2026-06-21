"""General utility commands."""

import time

import discord
from discord import app_commands
from discord.ext import commands

import theme


class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Check the bot's latency and uptime.")
    async def ping(self, interaction: discord.Interaction):
        # Gateway (heartbeat) latency is already tracked by the client.
        ws_latency = round(self.bot.latency * 1000)

        # Measure API round-trip by timing the initial response, then edit it
        # with the full result.
        start = time.perf_counter()
        await interaction.response.send_message(
            embed=theme.embed(description="🏓 Pinging...", color=theme.BRAND)
        )
        api_latency = round((time.perf_counter() - start) * 1000)

        # Health status from the worse of the two latencies.
        worst = max(ws_latency, api_latency)
        if worst < 150:
            status, color = "Excellent", theme.SUCCESS
        elif worst < 300:
            status, color = "Good", theme.WARNING
        else:
            status, color = "Sluggish", theme.DANGER

        embed = theme.embed("🏓 Pong!", color=color)
        embed.add_field(name="📡 Gateway", value=f"`{ws_latency} ms`", inline=True)
        embed.add_field(name="⚡ API", value=f"`{api_latency} ms`", inline=True)
        embed.add_field(name="📶 Status", value=status, inline=True)

        start_time = getattr(self.bot, "start_time", None)
        if start_time:
            # Discord renders this as a live relative timestamp, e.g. "2 hours ago".
            embed.add_field(
                name="⏱️ Uptime",
                value=f"Online since {discord.utils.format_dt(start_time, 'R')}",
                inline=False,
            )
        embed.set_footer(text=self.bot.user.name)
        await interaction.edit_original_response(embed=embed)

    @app_commands.command(name="info", description="List every command with examples.")
    async def info(self, interaction: discord.Interaction):
        embed = theme.embed(
            "ℹ️ Commands",
            "Everything this bot can do. The `person` field autocompletes from "
            "names already on the board.",
            theme.BRAND,
        )
        embed.add_field(
            name="📋 The Gay Men Board",
            value=(
                "`/mention person:<name> [by:@user]` — log a mention (credit someone else with `by`)\n"
                "`/board [person:<name>]` — full board, or one person's detail card\n"
                "\n"
                "*e.g.* `/mention person:Dave` → `/board`"
            ),
            inline=False,
        )
        embed.add_field(
            name="🏆 Leaderboards",
            value=(
                "`/leaderboard` — overall top mentioners (everyone)\n"
                "`/leaderboard person:<name>` — top mentioners of one person\n"
                "`/leaderboard-self` — which person gets mentioned the most\n"
                "`/gayest-man` — spotlight the single biggest mentioner\n"
                "`/pusswee` — crowns the biggest dodger (never mentions the most guys)\n"
                "\n"
                "*e.g.* `/leaderboard person:Dave`"
            ),
            inline=False,
        )
        embed.add_field(
            name="🔧 Utility",
            value="`/ping` — latency & uptime\n`/info` — this list",
            inline=False,
        )
        embed.add_field(
            name="🤖 Auto-detect",
            value=(
                "Just **say a tracked name** in chat and it counts automatically. "
                "I'll react 🏳️‍🌈. (10 seconds per person; `/mention` still works "
                "for manual logs.)"
            ),
            inline=False,
        )
        embed.add_field(
            name="🔨 Moderation · needs Moderate Members",
            value="`/hornyjail user:<@user> [user2] [user3]` — mute, deafen, `horni` role + smirk 😏 for 1h",
            inline=False,
        )
        embed.add_field(
            name="🛡️ Admin · needs Manage Server",
            value=(
                "`/add name:<name>` — start tracking someone\n"
                "`/remove person:<name>` — remove someone & wipe their counts\n"
                "`/reload` — hot-reload cogs after code edits (owner only)"
            ),
            inline=False,
        )
        embed.set_footer(text=f"{self.bot.user.name} • 12 commands")
        if interaction.guild and interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
