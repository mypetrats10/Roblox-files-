# Grave Without a Stone: Seed Catalogue Bot

A Discord bot that keeps one shared database of seeds and posts each new seed to the channel for its ranking:

| Ranking | Channel |
|---|---|
| Mediocre | #mediocre-seeds |
| Good | #good-seeds |
| Great | #great-seeds |
| Amazing | #amazing-seeds |
| Perfect | #perfect-seeds |
| Instant Complete | #instant-complete-seeds |

`/setup` reuses channels you already have (any channel whose name contains "seed" and the ranking's word, such as `#great-seeds`) and creates the rest, along with a `#submit-a-seed` channel for the panel. It makes all the webhooks itself.

## Submitting seeds

Seeds are submitted from a **panel**: a message with one button per ranking. Nobody needs to type a command.

```
 Seed Submissions
 [Mediocre] [Good] [Great] [Amazing] [Perfect]
 [Instant Complete] [Look up a seed]
```

Clicking a ranking opens a form:

| Ranking | Form fields |
|---|---|
| Mediocre to Perfect | Seed, why it's that ranking, images (optional, up to 10) |
| Instant Complete | Seed, map, building, where the flare gun is, images (optional, up to 10) |

## How seeds are posted

- **One message per seed.** The details and all the images sit together in one card, coloured by ranking. Nothing is split across messages and no image appears twice.
- **One name.** Every post uses the same name and picture (the bot's, or `BOT_NAME`), so Discord groups back-to-back posts under a single header.
- **Always the right channel.** `/setup` records which channel belongs to each ranking. When the bot starts, it checks every webhook still posts to that channel. If someone deletes a webhook, the bot makes a new one by itself. If a webhook gets moved, or its channel is deleted, that ranking is blocked with the reason shown until an admin runs `/setup` again, so nothing lands in the wrong place. The bot also checks where each post actually landed, and deletes it if it ended up somewhere else.

Duplicates are blocked for everyone. Seeds are compared ignoring capital letters and spaces, so `Ab12 Cd` and `ab12cd` count as the same seed. If someone submits a seed that's already in, the bot tells them its ranking, who submitted it, and links to the post.

## Commands

| Command | Who | What it does |
|---|---|---|
| `/setup` | Admins (Manage Server) | Finds or creates the seed channels, makes their webhooks, and posts and pins the panel. Safe to run again: it reuses everything and repairs what's broken |
| `/checksetup` | Admins (Manage Server) | Shows which channel each ranking posts to, and any problems |
| `/lookup seed` | Everyone | Shows whether a seed is already catalogued, and why it got that ranking |
| `/list [ranking] [page]` | Everyone | Browse seeds, 25 per page |
| `/stats` | Everyone | Number of seeds in each ranking |
| `/export` | Everyone | Downloads the whole catalogue as a CSV file you can open in Excel or Google Sheets |
| `/remove seed` | Moderators (Manage Messages) | Deletes a seed and its channel post |

## Setup

You only paste one thing: the bot token. The bot makes its own channels and webhooks.

1. **Create the bot.** Go to https://discord.com/developers/applications, click **New Application**, open **Bot**, and click **Reset Token**. Copy the token.
2. **Configure.** Copy `.env.example` to `.env` and paste the token after `DISCORD_TOKEN=`. Optionally:
   - `GUILD_ID`: your server's ID, so the commands show up straight away. Without it they can take up to an hour to appear.
   - `MAPS`: a comma-separated list of the game's maps. The Instant Complete form then shows a dropdown instead of a text box (25 maps at most).
3. **Run it.** You need Python 3.10 or newer.

   ```bash
   pip install -r requirements.txt
   ```

   ```bash
   python bot.py
   ```
4. **Invite it.** The bot's window prints an invite link. Open it and choose your server. The link already asks for the permissions the bot needs: Manage Channels, Manage Webhooks and Manage Messages, plus the basics.
5. **Run `/setup`** in your server. The bot replies with each ranking's channel and a link to the pinned panel. That's everything.

Channels the bot creates are read-only for members, so only seed posts appear there. Channels you already had are left as they are.

The bot only answers while `python bot.py` is running. To keep it online all the time, run it on an always-on PC, a Raspberry Pi, or a bot host.

## Sharing it

Each running copy of the bot keeps one catalogue for one server. To give the bot to another server, send them this folder **without** your `.env` and `seeds.db`. They follow the setup steps with their own bot.

Keep the token private. If it leaks, reset it in the developer portal and put the new one in `.env`. The webhook links the bot makes are stored in `seeds.db`, so keep that file private too. If one leaks, delete that webhook in the channel's settings, and the bot makes a fresh one the next time it starts or someone runs `/checksetup`.

## Backups

The whole catalogue is in one file, `seeds.db`. Copy that file to back it up. `/export` also gives you a readable copy at any time.

## Tests

```bash
python -m pytest -q
```
