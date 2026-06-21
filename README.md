# gay man counter

A Discord bot built around one running joke: a **"days since he was mentioned"** board. Add people to the board, and every time someone brings one of them up (by typing their name _or_ @mentioning them) the clock resets and the mentioner gets credit. Leaderboards, spotlights, and a couple of prank commands round it out.

Everything is **per-server** (scoped by guild ID), so each server it's in keeps its own independent board.

---

## Features

- **The board** — track any number of people; see how long since each was last mentioned.
- **Auto-detect** — the bot watches chat and logs a mention automatically when a tracked name is typed (whole-word match) or a tagged member is @mentioned. Reacts 🏳️‍🌈, with a short per-person cooldown to stop farming.
- **Manual logging** — `/mention` for deliberate or backdated logs, and you can credit someone else.
- **Leaderboards & spotlights** — who mentions the most, who gets mentioned the most, the single biggest mentioner, and the biggest "dodger".
- **Prank commands** — `/hornyjail` (temporary mute/deafen/role + smirk reactions) and a hidden easter egg.
- **Live config** — `/reload` hot-swaps cog code without a restart.

---

## Commands

### Anyone

| Command                                | What it does                                                       |
| -------------------------------------- | ------------------------------------------------------------------ |
| `/mention person:<name> [by:@user]`    | Log a mention — resets the clock, credits you (or `by`)            |
| `/board [person:<name>]`               | Full board (sorted by longest streak), or one person's detail card |
| `/list`                                | Plain alphabetical roster of every tracked name                    |
| `/leaderboard [person:<name>]`         | Overall top mentioners, or for one person                          |
| `/leaderboard-self`                    | Which tracked person gets mentioned the most                       |
| `/gayest-man`                          | Spotlight: the user with the most mentions overall                 |
| `/pusswee`                             | Spotlight: the active player who's dodged the most people          |
| `/hornyjail user:<@u> [user2] [user3]` | Mute, deafen, `horni` role + 😏 on every message for 1h            |
| `/ping`                                | Bot latency & uptime                                               |
| `/info`                                | In-Discord command list                                            |

### Admins (Manage Server)

| Command                                       | What it does                                                              |
| --------------------------------------------- | ------------------------------------------------------------------------- |
| `/add name:<name>` **or** `/add user:@member` | Track a typed name, or tag a member (tag also enables @mention detection) |
| `/remove person:<name>`                       | Remove a person and wipe their mention counts                             |
| `/reload`                                     | _(owner only)_ Hot-reload cogs after code edits                           |

> There's also a hidden easter-egg command not listed in `/info`.

---

## Tech stack

- **Python 3.11** + [discord.py](https://github.com/Rapptz/discord.py) 2.x (slash commands / app commands)
- **MongoDB Atlas** via [motor](https://motor.readthedocs.io/) (async driver)

## Project structure

```
discord-bot/
├─ bot.py             # entry point: intents, cog loading, command sync
├─ db.py              # MongoDB data layer (persons, mentions, temp roles, jails)
├─ theme.py           # shared embed colour palette + base-embed helper
├─ cogs/
│  ├─ board.py        # /mention /board /list /add /leaderboard /leaderboard-self
│  │                  #   /gayest-man /pusswee
│  ├─ admin.py        # /remove /reload
│  ├─ general.py      # /ping /info
│  ├─ autodetect.py   # chat listener (no commands) — typed names + @mentions
│  └─ fun.py          # /gay /hornyjail + background cleanup loop
├─ requirements.txt
├─ _check.py          # offline sanity check (DB connectivity + cogs load + command list)
├─ .env               # secrets — gitignored
└─ .gitignore
```

---

## Setup

### 1. Install

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure `.env` for local dev

```ini
# Bot token — Discord Developer Portal → your app → Bot → Reset Token
DISCORD_TOKEN=...

# MongoDB Atlas connection string
MONGO_URI=mongodb+srv://user:pass@cluster.xxxxx.mongodb.net/

# Optional — instant command sync to ONE server while developing.
# DEV_GUILD_ID=123456789012345678
# DEV_SYNC=1
```

In the Developer Portal → **Bot** tab, enable the **Message Content** privileged intent (required for auto-detect).

### 3. Run

```powershell
python bot.py
```

The bot stays online only while this process runs. (See _Hosting_ below for always-on.)

To sanity-check without connecting to Discord (verifies Mongo + that all cogs load):

```powershell
python _check.py
```

---

## Command sync

Slash commands are registered with Discord in one of two modes (see `CounterBot.sync_commands`):

- **Global (default)** — commands work in **every** server the bot is in, including newly added ones. Can take **up to ~1 hour** to first appear or update.
- **Dev (`DEV_SYNC=1` + `DEV_GUILD_ID`)** — syncs **instantly** to that one server. Use while iterating, then unset to go back to global.

`/reload` re-runs the _same_ sync logic, so it never creates duplicate commands.

---

## Inviting the bot

Generate an invite from **OAuth2 → URL Generator** with scopes `bot` + `applications.commands`, or use a link with the permissions integer below.

**Required bot permissions** (integer `297880656`):

| Group   | Permissions                                                     |
| ------- | --------------------------------------------------------------- |
| General | View Channels, Manage Roles, Manage Channels                    |
| Text    | Send Messages, Embed Links, Read Message History, Add Reactions |
| Voice   | Mute Members, Deafen Members, Move Members                      |

```
https://discord.com/oauth2/authorize?client_id=<APP_ID>&permissions=297880656&scope=bot+applications.commands
```

After inviting, drag the bot's role **high** in Server Settings → Roles — it can only mute/move/assign-roles to members below its own role.

---

## Customizing

- **Message wording & embeds** live in the `cogs/` files (mostly `board.py`); colours are in `theme.py`.
- **Auto-detect tunables** (`REACT_EMOJI`, `COOLDOWN_SECONDS`, `CACHE_TTL_SECONDS`) are constants at the top of `cogs/autodetect.py`.
- Edit, then run **`/reload`** in Discord — no restart needed for code/text changes. (Changing intents or _adding/removing_ commands still needs a restart / resync.)

---

## Hosting

Currently run locally. To keep it online 24/7, host it on an always-on machine (e.g. an Oracle Cloud free-tier VPS, a Raspberry Pi, or as a Windows service via NSSM). The MongoDB data lives in Atlas, so it persists across restarts and moves with the bot.
