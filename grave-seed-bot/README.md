# Grave Without a Stone: Seed Catalogue Bot

A Discord bot that keeps one shared database of seeds and posts each new seed to the channel for its ranking:

| Ranking | Channel |
|---|---|
| Mediocre | #mediocre-seeds |
| Good | #good-seeds |
| Great | #great-seeds |
| Amazing | #amazing-seeds |
| Perfect | #perfect-seeds |
| Instant Complete | #instant-complete-seeds (create this one; the name must contain "instant") |

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
- **Always the right channel.** When the bot starts, it checks each webhook. The webhook has to exist, its channel's name has to contain the ranking's word (`#great-seeds` for Great, `#instant-complete-seeds` for Instant Complete), and no two rankings can share a channel. A ranking that fails is blocked, with the reason shown, so nothing gets posted to the wrong place. The bot also confirms where each post actually landed, and if a webhook was moved since the check, it deletes the post and blocks that ranking. Run `/checksetup` after changing webhooks.

Duplicates are blocked for everyone. Seeds are compared ignoring capital letters and spaces, so `Ab12 Cd` and `ab12cd` count as the same seed. If someone submits a seed that's already in, the bot tells them its ranking, who submitted it, and links to the post.

## Commands

| Command | Who | What it does |
|---|---|---|
| `/panel` | Admins (Manage Server) | Posts the submission panel in the current channel |
| `/checksetup` | Admins (Manage Server) | Re-checks every webhook and shows which channel each ranking posts to |
| `/lookup seed` | Everyone | Shows whether a seed is already catalogued, and why it got that ranking |
| `/list [ranking] [page]` | Everyone | Browse seeds, 25 per page |
| `/stats` | Everyone | Number of seeds in each ranking |
| `/export` | Everyone | Downloads the whole catalogue as a CSV file you can open in Excel or Google Sheets |
| `/remove seed` | Moderators (Manage Messages) | Deletes a seed and its channel post |

## Setup

1. **Create the bot.** Go to https://discord.com/developers/applications, click New Application, open **Bot**, and click **Reset Token**. Copy the token.
2. **Invite it.** Open **OAuth2 → URL Generator** and tick `bot` and `applications.commands`. Open the generated URL and pick your server. The bot needs no extra permissions because it posts through webhooks.
3. **Make the webhooks.** For each of the six channels: Edit Channel → Integrations → Webhooks → New Webhook → Copy Webhook URL.
4. **Configure.** Copy `.env.example` to `.env` and paste in the token and the six webhook URLs. Optionally:
   - `GUILD_ID`: your server's ID, so the commands show up straight away. Without it they can take up to an hour to appear.
   - `MAPS`: a comma-separated list of the game's maps. The Instant Complete form then shows a dropdown instead of a text box (25 maps at most).
5. **Run it.** You need Python 3.10 or newer.

   ```bash
   pip install -r requirements.txt
   ```

   ```bash
   python bot.py
   ```
6. **Check the channels.** The console lists each ranking and its channel, and marks any problem as BLOCKED. You can also run `/checksetup` in Discord.
7. **Post the panel.** In the channel where people should submit seeds (for example `#submit-a-seed`), type `/panel`, then pin the message. The panel keeps working after the bot restarts. You only post it once.

The bot only answers while `python bot.py` is running. To keep it online all the time, run it on an always-on PC, a Raspberry Pi, or a bot host.

## Sharing it

To give the bot to another server, send them this folder **without** your `.env` and `seeds.db`. They follow the setup steps with their own bot and webhooks.

Keep the token and webhook URLs private. Anyone who has a webhook URL can post into that channel. If one leaks, delete the webhook in Discord and make a new one.

## Backups

The whole catalogue is in one file, `seeds.db`. Copy that file to back it up. `/export` also gives you a readable copy at any time.

## Tests

```bash
python -m pytest -q
```
