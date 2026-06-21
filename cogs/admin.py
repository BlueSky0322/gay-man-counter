"""Admin-only board management + maintenance. Gated behind permissions."""

import importlib

import discord
from discord import app_commands
from discord.ext import commands

import db
import theme


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _person_ac(self, interaction: discord.Interaction, current: str):
        names = await db.list_person_names(interaction.guild_id)
        current = current.lower()
        return [
            app_commands.Choice(name=n, value=n)
            for n in names
            if current in n.lower()
        ][:25]

    @app_commands.command(
        name="remove",
        description="Remove a person (and all their mentions) from the board.",
    )
    @app_commands.describe(person="Who to remove")
    @app_commands.autocomplete(person=_person_ac)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction, person: str):
        removed, deleted = await db.remove_person(interaction.guild_id, person)
        if not removed:
            await interaction.response.send_message(
                embed=theme.embed(
                    "⚠️ Not Found",
                    f"**{person}** isn't on the board.",
                    theme.WARNING,
                ),
                ephemeral=True,
            )
            return
        embed = theme.embed(
            "🗑️ Removed", f"**{person}** is off the board.", theme.DANGER
        )
        embed.add_field(
            name="Cleared", value=f"`{deleted}` mention record(s)", inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="reload",
        description="Reload cogs to apply code changes without restarting (owner only).",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def reload(self, interaction: discord.Interaction):
        # Reloading code is powerful — restrict to the bot's owner specifically,
        # not just anyone with Manage Server.
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(
                embed=theme.embed(
                    "⛔ Owner Only",
                    "Only the bot owner can use `/reload`.",
                    theme.DANGER,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Refresh shared helper modules so edits to them apply too. `db` is left
        # alone on purpose — reloading it would drop the live Mongo connection.
        importlib.reload(theme)

        # Reload every currently-loaded cog. reload_extension is safe: if a cog
        # fails to import, it rolls back to the previous working version.
        results = []
        for ext in list(self.bot.extensions.keys()):
            try:
                await self.bot.reload_extension(ext)
                results.append(f"✅ `{ext}`")
            except Exception as e:
                results.append(f"❌ `{ext}` — {type(e).__name__}: {e}")

        # Re-sync commands exactly how startup does (respects global vs DEV_SYNC),
        # so /reload can never create duplicates.
        synced = await self.bot.sync_commands()

        ok = all(line.startswith("✅") for line in results)
        embed = theme.embed(
            "🔄 Reloaded" if ok else "⚠️ Reloaded with errors",
            "\n".join(results),
            theme.SUCCESS if ok else theme.WARNING,
        )
        embed.set_footer(text=f"Sync: {synced}")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
