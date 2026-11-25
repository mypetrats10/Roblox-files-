"""Grave Without a Stone seed catalogue bot.

Slash commands:
  /submit   add a seed (instant-complete seeds also need map, building, location)
  /lookup   check whether a seed is already catalogued
  /list     browse catalogued seeds, optionally by ranking
  /stats    how many seeds are in each ranking
  /export   download the whole catalogue as a CSV
  /remove   (moderators) delete a seed and its channel post
"""
import io
import os
import time
from datetime import datetime, timezone

import aiohttp
import discord
from discord import app_commands
from dotenv import load_dotenv

from seeddb import TIERS, SeedDB

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")  # optional: makes commands appear instantly in one server
DB_PATH = os.getenv("DB_PATH", "seeds.db")
WEBHOOKS = {t: os.getenv(f"WEBHOOK_{t.upper()}", "").strip() for t in TIERS}
MAPS = [m.strip() for m in os.getenv("MAPS", "").split(",") if m.strip()]

TIER_CHOICES = [app_commands.Choice(name=v["label"], value=k) for k, v in TIERS.items()]

db = SeedDB(DB_PATH)


def seed_embed(s) -> discord.Embed:
    tier = TIERS[s.tier]
    e = discord.Embed(title=f"Seed: {s.seed}", color=tier["color"])
    e.add_field(name="Ranking", value=tier["label"], inline=True)
    e.add_field(name="Submitted by", value=f"<@{s.submitter_id}>", inline=True)
    e.add_field(name="Why this ranking", value=s.reason[:1024], inline=False)
    if s.tier == "instant":
        e.add_field(name="Map", value=s.map, inline=True)
        e.add_field(name="Building", value=s.building, inline=True)
        e.add_field(name="Where in the building", value=s.location[:1024], inline=False)
    e.timestamp = datetime.fromtimestamp(s.created_at, tz=timezone.utc)
    e.set_footer(text=f"Catalogue entry #{s.id}")
    return e


class SeedBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.http_session: aiohttp.ClientSession | None = None

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession()
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        await super().close()

    def webhook(self, tier: str) -> discord.Webhook | None:
        url = WEBHOOKS.get(tier)
        if not url:
            return None
        return discord.Webhook.from_url(url, session=self.http_session)


bot = SeedBot()


@bot.event
async def on_ready():
    missing = [t for t, u in WEBHOOKS.items() if not u]
    print(f"Logged in as {bot.user}. Seeds catalogued: {sum(db.counts().values())}")
    if missing:
        print(f"Warning: no webhook set for: {', '.join(missing)}")


async def map_autocomplete(_: discord.Interaction, current: str):
    cur = current.lower()
    return [app_commands.Choice(name=m, value=m) for m in MAPS if cur in m.lower()][:25]


@bot.tree.command(description="Add a seed to the catalogue")
@app_commands.describe(
    seed="The seed",
    ranking="How good the seed is",
    reason="Why it deserves this ranking",
    map="Instant complete only: which map",
    building="Instant complete only: which building it's in",
    location="Instant complete only: where in that building (floor, room, landmark)",
)
@app_commands.choices(ranking=TIER_CHOICES)
@app_commands.autocomplete(map=map_autocomplete)
async def submit(
    interaction: discord.Interaction,
    seed: app_commands.Range[str, 1, 100],
    ranking: app_commands.Choice[str],
    reason: app_commands.Range[str, 3, 1000],
    map: str | None = None,
    building: app_commands.Range[str, 1, 100] | None = None,
    location: app_commands.Range[str, 1, 500] | None = None,
):
    tier = ranking.value
    existing = db.get(seed)
    if existing:
        where = f" Posted here: {existing.message_url}" if existing.message_url else ""
        await interaction.response.send_message(
            f"**{existing.seed}** is already catalogued as **{TIERS[existing.tier]['label']}** "
            f"by {existing.submitter_name}.{where}",
            ephemeral=True,
        )
        return

    if tier == "instant":
        missing = [n for n, v in (("map", map), ("building", building), ("location", location))
                   if not (v or "").strip()]
        if missing:
            await interaction.response.send_message(
                "Instant-complete seeds need the map, the building, and where in the building. "
                f"Missing: **{', '.join(missing)}**. Run /submit again with those filled in.",
                ephemeral=True,
            )
            return
    else:
        map = building = location = None  # only stored for instant-complete seeds

    hook = bot.webhook(tier)
    if hook is None:
        await interaction.response.send_message(
            f"No webhook is set up for **{ranking.name}** yet. Ask a server admin to add "
            f"WEBHOOK_{tier.upper()} to the bot's .env file.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    try:
        entry = db.add(seed, tier, reason, interaction.user.id, str(interaction.user),
                       map=map, building=building, location=location)
    except KeyError:
        await interaction.followup.send("Someone catalogued that seed a moment ago.", ephemeral=True)
        return
    except ValueError as err:
        await interaction.followup.send(str(err), ephemeral=True)
        return

    try:
        msg = await hook.send(embed=seed_embed(entry), wait=True,
                              allowed_mentions=discord.AllowedMentions.none())
        db.set_message(entry.id, msg.id, msg.jump_url)
    except discord.HTTPException as err:
        db.remove(seed)  # keep the database and the channels in step
        await interaction.followup.send(
            f"Couldn't post to the {ranking.name} channel ({err.status}), so the seed wasn't saved. "
            "Check that the webhook URL is still valid.",
            ephemeral=True,
        )
        return

    await interaction.followup.send(
        f"Catalogued **{entry.seed}** as **{ranking.name}**. {msg.jump_url}", ephemeral=True
    )


@bot.tree.command(description="Check whether a seed is already catalogued")
async def lookup(interaction: discord.Interaction, seed: str):
    s = db.get(seed)
    if not s:
        await interaction.response.send_message(
            f"**{seed}** isn't catalogued yet. Use /submit to add it.", ephemeral=True
        )
        return
    content = s.message_url or None
    await interaction.response.send_message(content=content, embed=seed_embed(s), ephemeral=True)


@bot.tree.command(name="list", description="Browse catalogued seeds")
@app_commands.describe(ranking="Only show this ranking", page="Page number (25 per page)")
@app_commands.choices(ranking=TIER_CHOICES)
async def list_cmd(interaction: discord.Interaction,
                   ranking: app_commands.Choice[str] | None = None,
                   page: app_commands.Range[int, 1, 1000] = 1):
    tier = ranking.value if ranking else None
    rows = db.list(tier=tier, limit=25, offset=(page - 1) * 25)
    title = f"{ranking.name if ranking else 'All'} seeds — page {page}"
    if not rows:
        await interaction.response.send_message(f"{title}: nothing here yet.", ephemeral=True)
        return
    lines = []
    for s in rows:
        line = f"`{s.seed}` · **{TIERS[s.tier]['label']}**"
        if s.tier == "instant":
            line += f" · {s.map} / {s.building}"
        if s.message_url:
            line += f" · [post]({s.message_url})"
        lines.append(line)
    e = discord.Embed(title=title, description="\n".join(lines)[:4096],
                      color=TIERS[tier]["color"] if tier else 0x5865F2)
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(description="How many seeds are in each ranking")
async def stats(interaction: discord.Interaction):
    c = db.counts()
    e = discord.Embed(title="Seed catalogue", color=0x5865F2)
    for t, v in TIERS.items():
        e.add_field(name=v["label"], value=str(c[t]), inline=True)
    e.set_footer(text=f"Total: {sum(c.values())}")
    await interaction.response.send_message(embed=e)


@bot.tree.command(description="Download the whole catalogue as a spreadsheet (CSV)")
async def export(interaction: discord.Interaction):
    data = db.export_csv().encode("utf-8")
    name = f"grave-seeds-{time.strftime('%Y-%m-%d')}.csv"
    await interaction.response.send_message(
        file=discord.File(io.BytesIO(data), filename=name), ephemeral=True
    )


@bot.tree.command(description="Remove a seed from the catalogue (moderators)")
@app_commands.default_permissions(manage_messages=True)
async def remove(interaction: discord.Interaction, seed: str):
    s = db.remove(seed)
    if not s:
        await interaction.response.send_message(f"**{seed}** isn't in the catalogue.", ephemeral=True)
        return
    note = ""
    hook = bot.webhook(s.tier)
    if hook and s.message_id:
        try:
            await hook.delete_message(s.message_id)
        except discord.HTTPException:
            note = " The channel post couldn't be deleted, so remove it by hand."
    await interaction.response.send_message(
        f"Removed **{s.seed}** ({TIERS[s.tier]['label']}).{note}", ephemeral=True
    )


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is missing. Copy .env.example to .env and fill it in.")
    bot.run(TOKEN)
