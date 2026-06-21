# gay man counter

A Discord bot for the running joke about a "days since he was mentioned" board. You add people to the board. When someone brings one of them up in chat, by typing their name or @mentioning them, the clock resets and whoever did it gets credit.

There are also leaderboards, a few spotlight commands, and a couple of prank commands.

Everything is per-server (scoped by guild ID), so each server keeps its own board.

---

## Features

- **The board:** track any number of people and see how long it's been since each was last mentioned.
- **Auto-detect:** the bot watches chat and counts a mention when a tracked name is typed (whole-word match) or a tagged member is @mentioned. It reacts with 🏳️‍🌈 and uses a short per-person cooldown to stop farming.
- **Manual logging:** use `/mention` for deliberate or backdated logs. You can also credit someone else.
- **Leaderboards and spotlights:** who mentions the most, who gets mentioned the most, the single biggest mentioner, and the biggest dodger.
- **Prank commands:** `/hornyjail` (temporary mute, deafen, role, and smirk reactions) plus a hidden easter egg.
- **Live config:** `/reload` swaps cog code without a restart.

---

## Commands

### Anyone

| Command | What it does |
| --- | --- |
| `/mention person:<name> [by:@user]` | Logs a mention. Resets the clock and credits you, or whoever you pass to `by`. |
| `/board [person:<name>]` | The full board, sorted by longest streak. Pass a name for that person's detail card. |
| `/list` | Plain alphabetical roster of every tracked name. |
| `/leaderboard [person:<name>]` | Top mentioners overall, or for one person. |
| `/leaderboard-self` | Which tracked person gets mentioned the most. |
| `/gayest-man` | Spotlight on the user with the most mentions overall. |
| `/pusswee` | Spotlight on the active player who has dodged the most people. |
| `/hornyjail user:<@u> [user2] [user3]` | Mutes, deafens, adds the `horni` role, and smirks 😏 at every message for an hour. |
| `/ping` | Bot latency and uptime. |
| `/info` | In-Discord command list. |

### Admins (Manage Server)

| Command | What it does |
| --- | --- |
| `/add name:<name>` or `/add user:@member` | Track a typed name, or tag a member. Tagging also turns on @mention detection. |
| `/remove person:<name>` | Removes a person and wipes their mention counts. |
| `/reload` | Owner only. Hot-reloads cogs after code edits. |

There's also a hidden easter-egg command that isn't listed in `/info`.

---

## Screenshots

Placeholders. Drop your own captures into a `docs/` folder and update the paths.

| Command | Preview |
| --- | --- |
| `/board` | ![/board](docs/board.png) |
| `/leaderboard` | ![/leaderboard](docs/leaderboard.png) |
| `/gayest-man` | ![/gayest-man](docs/gayest-man.png) |

---

## Tech stack

- Python 3.11 with [discord.py](https://github.com/Rapptz/discord.py) 2.x (slash / app commands)
- [MongoDB Atlas](https://www.mongodb.com/atlas) via the async [motor](https://motor.readthedocs.io/) driver

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
│  ├─ autodetect.py   # chat listener (no commands): typed names + @mentions
│  └─ fun.py          # /gay /hornyjail + background cleanup loop
├─ requirements.txt
├─ _check.py          # offline sanity check (DB connectivity + cogs load + command list)
├─ .env               # secrets, gitignored
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
# Bot token, from Discord Developer Portal -> your app -> Bot -> Reset Token
DISCORD_TOKEN=...

# MongoDB Atlas connection string
MONGO_URI=mongodb+srv://user:pass@cluster.xxxxx.mongodb.net/

# Optional: instant command sync to ONE server while developing.
# DEV_GUILD_ID=123456789012345678
# DEV_SYNC=1
```

In the Developer Portal, on the **Bot** tab, turn on the **Message Content** privileged intent. Auto-detect needs it.

### 3. Run

```powershell
python bot.py
```

The bot is online only while this process runs. See [Hosting](#hosting) for always-on.

To sanity-check without connecting to Discord (it verifies Mongo and that every cog loads):

```powershell
python _check.py
```

---

## Command sync

Slash commands register with Discord in one of two modes (see `CounterBot.sync_commands`):

- **Global (default).** Commands work in every server the bot is in, including new ones. They can take up to about an hour to first appear or update.
- **Dev (`DEV_SYNC=1` plus `DEV_GUILD_ID`).** Syncs instantly to that one server. Use it while iterating, then unset it to go back to global.

`/reload` runs the same sync logic, so it won't create duplicate commands.

---

## Inviting the bot

Generate an invite from **OAuth2 -> URL Generator** with the `bot` and `applications.commands` scopes, or use a link with the permissions integer below.

Required bot permissions (integer `297880656`):

| Group | Permissions |
| --- | --- |
| General | View Channels, Manage Roles, Manage Channels |
| Text | Send Messages, Embed Links, Read Message History, Add Reactions |
| Voice | Mute Members, Deafen Members, Move Members |

```
https://discord.com/oauth2/authorize?client_id=<APP_ID>&permissions=297880656&scope=bot+applications.commands
```

After inviting, move the bot's role high in Server Settings -> Roles. It can only mute, move, or assign roles to members below its own role.

---

## Customizing

- Message wording and embeds live in the `cogs/` files, mostly `board.py`. Colours are in `theme.py`.
- Auto-detect knobs (`REACT_EMOJI`, `COOLDOWN_SECONDS`, `CACHE_TTL_SECONDS`) are constants at the top of `cogs/autodetect.py`.
- Edit a file, then run `/reload` in Discord. Code and text changes apply with no restart. Changing intents, or adding or removing commands, still needs a restart or resync.

---

## Hosting

Right now it runs locally. To keep it online 24/7, run it on an always-on machine such as an Oracle Cloud free-tier VPS, a Raspberry Pi, or a Windows service via NSSM. The data lives in MongoDB Atlas, so it survives restarts and moves with the bot.

---

## Troubleshooting

### `NoNameservers`, `getaddrinfo failed`, or `ServerSelectionTimeoutError` at startup

The bot can't resolve the MongoDB Atlas hostnames. The `mongodb+srv://` URI needs DNS SRV and TXT lookups, and some routers fail them intermittently.

`dns_fix.py` already handles this. It's imported first by `db.py` and routes all DNS through public resolvers (`1.1.1.1` and `8.8.8.8`) instead of the local one. This covers both dnspython's SRV lookups and `socket.getaddrinfo`, which is why the module is there.

If it still fails, your network may block outbound DNS (port 53) to those servers. Either change the IPs in `PUBLIC_DNS` at the top of `dns_fix.py` to a resolver your network allows, or set your OS or router DNS to `1.1.1.1` and `8.8.8.8`.

Note: this is MongoDB Atlas, which is cloud-hosted. There's no local MongoDB, and Compass does not need to be open for the bot to connect.

---

## License

Released under the [MIT License](LICENSE).
