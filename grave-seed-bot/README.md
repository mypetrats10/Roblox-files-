# Grave Without a Stone: Seed Catalogue Bot

A Discord bot that keeps one shared database of seeds and posts each new seed to the channel for its ranking:

| Ranking | Channel |
|---|---|
| Mediocre | #mediocre-seeds |
| Good | #good-seeds |
| Great | #great-seeds |
| Amazing | #amazing-seeds |
| Perfect | #perfect-seeds |
| Instant Complete | #instant-complete-seeds (create this one) |

Every submission needs a **reason** for its ranking. An **Instant Complete** seed also needs the **map**, the **building**, and **where in that building**. The bot won't save it until all three are filled in.

Duplicates are blocked for everyone. Seeds are compared ignoring capital letters and spaces, so `Ab12 Cd` and `ab12cd` count as the same seed. If someone tries to submit a seed that's already in, the bot tells them its ranking, who submitted it, and links to the post.

## Commands

| Command | Who | What it does |
|---|---|---|
| `/submit seed ranking reason [map building location]` | Everyone | Adds a seed and posts it to its ranking channel |
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
   - `MAPS`: a comma-separated list of the game's maps. People get them as suggestions when they type the map.
5. **Run it.** You need Python 3.10 or newer.

   ```bash
   pip install -r requirements.txt
   ```

   ```bash
   python bot.py
   ```

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
