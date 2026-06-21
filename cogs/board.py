"""Public commands for the 'days since he was mentioned' board.

This is the file to tweak if you want to reword the bot's replies or restyle
the embeds — every user-facing message below is built right here. Colors live
in ../theme.py.
"""

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import db
import theme


def _now() -> datetime:
    return datetime.now(timezone.utc)


def humanize(delta) -> str:
    """Turn a timedelta into a short string like '5d 2h' or '12m'."""
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    mins, _ = divmod(secs, 60)
    hrs, m = divmod(mins, 60)
    days, h = divmod(hrs, 24)
    parts = []
    if days:
        parts.append(f"{days}d")
    if h:
        parts.append(f"{h}h")
    if m and not days:  # once we're into days, minutes are just noise
        parts.append(f"{m}m")
    return " ".join(parts) if parts else "0m"


def _dot(delta) -> str:
    """A recency indicator for the board."""
    if delta is None:
        return "🧊"  # never mentioned
    secs = delta.total_seconds()
    if secs < 86400:  # < 1 day
        return "🔴"
    if secs < 7 * 86400:  # < 1 week
        return "🟡"
    return "🟢"  # been a while


def _bar(value: int, top: int, width: int = 12) -> str:
    """A little progress bar, scaled against the top value."""
    if not top or value <= 0:
        return "▱" * width
    filled = max(1, round(value / top * width))
    return "▰" * filled + "▱" * (width - filled)


def _missing(person: str) -> discord.Embed:
    return theme.embed(
        "⚠️ Not on the Board",
        f"**{person}** isn't tracked yet. Add him with `/add`.",
        theme.WARNING,
    )


class Board(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _thumb(self, interaction: discord.Interaction, embed: discord.Embed):
        if interaction.guild and interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

    async def _person_ac(self, interaction: discord.Interaction, current: str):
        """Autocomplete the `person` argument from names already on the board."""
        names = await db.list_person_names(interaction.guild_id)
        current = current.lower()
        return [
            app_commands.Choice(name=n, value=n)
            for n in names
            if current in n.lower()
        ][:25]

    @app_commands.command(
        name="board",
        description="The whole board, or one person's detail card if you pass a name.",
    )
    @app_commands.describe(
        person="Leave blank for the full board; pick someone for their detail card"
    )
    @app_commands.autocomplete(person=_person_ac)
    @app_commands.guild_only()
    async def board(
        self, interaction: discord.Interaction, person: str | None = None
    ):
        # A name routes to the detail card (this absorbed the old /since command).
        if person is not None:
            await self._detail(interaction, person)
            return

        people = await db.list_persons(interaction.guild_id)
        if not people:
            await interaction.response.send_message(
                embed=theme.embed(
                    "📋 The Board",
                    "Nobody's tracked yet. Add someone with `/add`.",
                    theme.BRAND,
                )
            )
            return
        now = _now()
        totals = await db.totals_by_person(interaction.guild_id)

        def streak(p):
            return (now - p["last_mention_at"]) if p["last_mention_at"] else None

        # Longest clean streak first; never-mentioned names float to the top.
        people.sort(
            key=lambda p: streak(p).total_seconds() if streak(p) else float("inf"),
            reverse=True,
        )

        lines = []
        for p in people:
            s = streak(p)
            total = totals.get(p["name_lower"], 0)
            dot = _dot(s)
            if s is None:
                lines.append(f"{dot} **{p['name']}** — never mentioned · `{total}`")
            else:
                when = discord.utils.format_dt(p["last_mention_at"], "R")
                lines.append(
                    f"{dot} **{p['name']}** — last {when} by <@{p['last_mention_by']}> · `{total}`"
                )

        embed = theme.embed(
            f"📋 The Board — {interaction.guild.name}", "\n".join(lines), theme.BRAND
        )
        embed.set_footer(text=f"{len(people)} tracked  •  🔴 <1d   🟡 <1w   🟢 longer   🧊 never")
        self._thumb(interaction, embed)
        await interaction.response.send_message(embed=embed)

    async def _detail(self, interaction: discord.Interaction, person: str):
        """Detail card for one person — used by /board when given a name."""
        p = await db.get_person(interaction.guild_id, person)
        if p is None:
            await interaction.response.send_message(embed=_missing(person), ephemeral=True)
            return

        total = await db.total_mentions(interaction.guild_id, person)
        top = await db.top_mentioner(interaction.guild_id, person)
        s = (_now() - p["last_mention_at"]) if p["last_mention_at"] else None

        if s is None:
            color = theme.BRAND
        elif s.total_seconds() > 7 * 86400:
            color = theme.SUCCESS
        else:
            color = theme.WARNING

        embed = theme.embed(f"⏱️ {p['name']}", color=color)
        if s is None:
            embed.add_field(name="Last mentioned", value="Never 🧊", inline=True)
            embed.add_field(name="By", value="—", inline=True)
        else:
            embed.add_field(
                name="Last mentioned",
                value=discord.utils.format_dt(p["last_mention_at"], "R"),
                inline=True,
            )
            embed.add_field(name="By", value=f"<@{p['last_mention_by']}>", inline=True)
        embed.add_field(name="All-time", value=f"`{total}` mentions", inline=True)
        embed.add_field(
            name="🏆 Top mentioner",
            value=f"<@{top['user_id']}> · `{top['count']}`" if top else "Nobody yet",
            inline=True,
        )
        embed.add_field(
            name="Added",
            value=f"{discord.utils.format_dt(p['created_at'], 'R')} by <@{p['added_by']}>",
            inline=False,
        )
        self._thumb(interaction, embed)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="mention",
        description="Log a mention — resets the clock. Optionally credit someone else.",
    )
    @app_commands.describe(
        person="Who got mentioned",
        by="Who mentioned him (defaults to you)",
    )
    @app_commands.autocomplete(person=_person_ac)
    @app_commands.guild_only()
    async def mention(
        self,
        interaction: discord.Interaction,
        person: str,
        by: discord.Member | None = None,
    ):
        # Credit `by` if given (picked from server members), else the invoker.
        credited = by or interaction.user
        prev, count = await db.log_mention(interaction.guild_id, person, credited.id)
        if prev is None:
            await interaction.response.send_message(
                embed=theme.embed(
                    "⚠️ Not on the Board",
                    f"**{person}** isn't tracked yet. Add gaymen with `/add` first.",
                    theme.WARNING,
                ),
                ephemeral=True,
            )
            return

        rank = await db.rank_of(interaction.guild_id, person, credited.id)
        total = await db.total_mentions(interaction.guild_id, person)
        if prev["last_mention_at"]:
            streak_val = f"**{humanize(_now() - prev['last_mention_at'])}** of peace, gone. 你就是酱咯"
        else:
            streak_val = f"First mention on the board! Kinda sus that **{credited.display_name}** mentioned **{prev['name']}**, but ok."

        embed = theme.embed(
            "📢 Mention Logged",
            f"**{credited.display_name}** mentioned **{prev['name']}** again la. Clock reset to **0**.",
            theme.SUCCESS,
        )
        embed.set_author(
            name=credited.display_name, icon_url=credited.display_avatar.url
        )
        embed.add_field(name="⏱️ Streak broken", value=streak_val, inline=False)
        embed.add_field(name="🎯 Tally", value=f"`{count}`", inline=True)
        if rank:
            embed.add_field(name="🏆 Rank", value=f"#{rank}", inline=True)
        embed.add_field(name="📊 All-time", value=f"`{total}`", inline=True)
        # Make it transparent when one person logs on another's behalf.
        if credited.id != interaction.user.id:
            embed.set_footer(text=f"Logged by {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="add", description="Add a new person to the board.")
    @app_commands.describe(name="The name to track")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def add(self, interaction: discord.Interaction, name: str):
        ok = await db.add_person(interaction.guild_id, name, interaction.user.id)
        clean = name.strip()
        if not ok:
            existing = await db.get_person(interaction.guild_id, clean)
            embed = theme.embed(
                "⚠️ Already Tracked",
                f"**{existing['name']}** is already on the board.",
                theme.WARNING,
            )
            embed.add_field(
                name="Added",
                value=f"{discord.utils.format_dt(existing['created_at'], 'R')} by <@{existing['added_by']}>",
                inline=False,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = theme.embed(
            "✅ Added to the Board",
            f"**{clean}** is now being tracked.",
            theme.SUCCESS,
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url,
        )
        embed.add_field(
            name="Next", value=f"Log a sighting with `/mention person:{clean}`", inline=False
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="leaderboard",
        description="Top mentioners — overall, or for one person if you pass one.",
    )
    @app_commands.describe(person="Leave blank for the overall board; pick someone for just them")
    @app_commands.autocomplete(person=_person_ac)
    @app_commands.guild_only()
    async def leaderboard(
        self, interaction: discord.Interaction, person: str | None = None
    ):
        medals = {0: "🥇", 1: "🥈", 2: "🥉"}

        # --- Overall leaderboard: top users across ALL tracked people ---
        if person is None:
            totals = await db.totals_by_user(interaction.guild_id)
            if not totals:
                await interaction.response.send_message(
                    embed=theme.embed(
                        "🏆 Overall Leaderboard",
                        "Nobody has mentioned anyone yet. Use `/mention` to get started.",
                        theme.GOLD,
                    )
                )
                return
            rows = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:10]
            top_count = rows[0][1]
            lines = [
                f"{medals.get(i, f'`#{i + 1}`')} <@{uid}> — **{cnt}**\n{_bar(cnt, top_count)}"
                for i, (uid, cnt) in enumerate(rows)
            ]
            embed = theme.embed(
                f"🏆 Overall Leaderboard — {interaction.guild.name}",
                "\n".join(lines),
                theme.GOLD,
            )
            embed.set_footer(
                text=f"{sum(totals.values())} total mentions  •  {len(totals)} players"
            )
            self._thumb(interaction, embed)
            await interaction.response.send_message(embed=embed)
            return

        # --- Single-person leaderboard ---
        p = await db.get_person(interaction.guild_id, person)
        if p is None:
            await interaction.response.send_message(embed=_missing(person), ephemeral=True)
            return
        rows = await db.leaderboard(interaction.guild_id, person, 10)
        if not rows:
            await interaction.response.send_message(
                embed=theme.embed(
                    f"🏆 {p['name']}",
                    f"Nobody has mentioned **{p['name']}** yet.",
                    theme.GOLD,
                )
            )
            return
        top_count = rows[0]["count"]
        lines = [
            f"{medals.get(i, f'`#{i + 1}`')} <@{r['user_id']}> — **{r['count']}**\n{_bar(r['count'], top_count)}"
            for i, r in enumerate(rows)
        ]
        total = await db.total_mentions(interaction.guild_id, person)
        embed = theme.embed(
            f"🏆 Top Mentioners — {p['name']}", "\n".join(lines), theme.GOLD
        )
        embed.set_footer(text=f"{total} total mentions of {p['name']}")
        self._thumb(interaction, embed)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="leaderboard-self",
        description="Which tracked person gets mentioned the most, by everyone.",
    )
    @app_commands.guild_only()
    async def leaderboard_self(self, interaction: discord.Interaction):
        people = await db.list_persons(interaction.guild_id)
        if not people:
            await interaction.response.send_message(
                embed=theme.embed(
                    "👑 Most Mentioned",
                    "The board is empty. Add someone with `/add`.",
                    theme.GOLD,
                )
            )
            return
        totals = await db.totals_by_person(interaction.guild_id)
        if not any(totals.values()):
            await interaction.response.send_message(
                embed=theme.embed(
                    "👑 Most Mentioned",
                    "No mentions logged yet. Use `/mention` to get the board moving.",
                    theme.GOLD,
                )
            )
            return
        # Rank the people themselves by total mentions (zeros included, at the bottom).
        rows = sorted(
            ((p["name"], totals.get(p["name_lower"], 0)) for p in people),
            key=lambda kv: kv[1],
            reverse=True,
        )[:10]
        top_count = rows[0][1]
        medals = {0: "🥇", 1: "🥈", 2: "🥉"}
        lines = [
            f"{medals.get(i, f'`#{i + 1}`')} **{name}** — **{cnt}**\n{_bar(cnt, top_count)}"
            for i, (name, cnt) in enumerate(rows)
        ]
        embed = theme.embed(
            f"👑 Most Mentioned — {interaction.guild.name}",
            "\n".join(lines),
            theme.GOLD,
        )
        embed.set_footer(
            text=f"{sum(totals.values())} total mentions  •  {len(people)} tracked"
        )
        self._thumb(interaction, embed)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="gayest-man",
        description="Spotlight the user with the most mentions across everyone.",
    )
    @app_commands.guild_only()
    async def gayest_man(self, interaction: discord.Interaction):
        totals = await db.totals_by_user(interaction.guild_id)
        if not totals:
            await interaction.response.send_message(
                embed=theme.embed(
                    "👑 The Gayest Man",
                    "Nobody has mentioned anyone yet. Use `/mention` to crown someone.",
                    theme.GOLD,
                )
            )
            return

        ranking = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        winner_id, winner_total = ranking[0]

        # Their favourite target — the person they mention most.
        fav = await db.favorite_target(interaction.guild_id, winner_id)
        fav_text = "—"
        if fav:
            people = await db.list_persons(interaction.guild_id)
            name_map = {p["name_lower"]: p["name"] for p in people}
            fav_name = name_map.get(fav["name_lower"], fav["name_lower"])
            fav_text = f"**{fav_name}** · `{fav['count']}`"

        # How far ahead of the runner-up.
        if len(ranking) > 1:
            second_id, second_total = ranking[1]
            lead = f"**+{winner_total - second_total}** over <@{second_id}>"
        else:
            lead = "uncontested 👑"

        embed = theme.embed(
            "👑 The Gayest Man",
            f"The crown goes to <@{winner_id}> with **{winner_total}** total mention(s).",
            theme.GOLD,
        )
        embed.add_field(name="🎯 Total mentions", value=f"`{winner_total}`", inline=True)
        embed.add_field(name="💘 Favourite target", value=fav_text, inline=True)
        embed.add_field(name="📈 Lead", value=lead, inline=True)
        embed.set_footer(text=f"{len(totals)} players in the running")

        # Show the winner's avatar if we can resolve the member.
        member = interaction.guild.get_member(winner_id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(winner_id)
            except discord.HTTPException:
                member = None
        if member:
            embed.set_thumbnail(url=member.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="pusswee",
        description="Crowns the biggest dodger — who's never mentioned the most guys.",
    )
    @app_commands.guild_only()
    async def pusswee(self, interaction: discord.Interaction):
        people = await db.list_persons(interaction.guild_id)
        if not people:
            await interaction.response.send_message(
                embed=theme.embed(
                    "🐱 The Biggest Pusswee",
                    "The board is empty. Add someone with `/add`.",
                    theme.BRAND,
                )
            )
            return
        tracked = {p["name_lower"]: p["name"] for p in people}
        tracked_set = set(tracked)

        mentioned = await db.mentioned_names_by_user(interaction.guild_id)
        if not mentioned:
            await interaction.response.send_message(
                embed=theme.embed(
                    "🐱 The Biggest Pusswee",
                    "Nobody has mentioned anyone yet — no players to judge.",
                    theme.BRAND,
                )
            )
            return
        totals = await db.totals_by_user(interaction.guild_id)

        # For each active player: which tracked guys they've NEVER mentioned.
        # Most dodged wins; tie-break on fewest total mentions (the bigger coward).
        ranking = [(uid, tracked_set - said) for uid, said in mentioned.items()]
        ranking.sort(key=lambda r: (-len(r[1]), totals.get(r[0], 0)))

        winner_id, dodged = ranking[0]
        if not dodged:
            await interaction.response.send_message(
                embed=theme.embed(
                    "🫡 No Pusswees Here",
                    "Everyone who plays has mentioned every single guy. Respect.",
                    theme.SUCCESS,
                )
            )
            return

        dodged_names = sorted(tracked[nl] for nl in dodged)
        shown = ", ".join(f"**{n}**" for n in dodged_names[:10])
        if len(dodged_names) > 10:
            shown += f", +{len(dodged_names) - 10} more"

        embed = theme.embed(
            "🐱 The Biggest Pusswee",
            f"The shame goes to <@{winner_id}> — never mentioned **{len(dodged)}** "
            f"of **{len(tracked_set)}** guys.",
            theme.DANGER,
        )
        embed.add_field(name="🙈 Never mentioned", value=shown, inline=False)
        embed.add_field(
            name="🗣️ Total mentions", value=f"`{totals.get(winner_id, 0)}`", inline=True
        )
        if len(ranking) > 1:
            second_id, second_dodged = ranking[1]
            diff = len(dodged) - len(second_dodged)
            margin = (
                f"**+{diff}** more dodged than <@{second_id}>"
                if diff > 0
                else "neck-and-neck"
            )
        else:
            margin = "uncontested 🐱"
        embed.add_field(name="📉 Margin", value=margin, inline=True)
        embed.set_footer(text=f"{len(mentioned)} active players")

        # Show the loser's avatar if we can resolve the member.
        member = interaction.guild.get_member(winner_id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(winner_id)
            except discord.HTTPException:
                member = None
        if member:
            embed.set_thumbnail(url=member.display_avatar.url)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Board(bot))
