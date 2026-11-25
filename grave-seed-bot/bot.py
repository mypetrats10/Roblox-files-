"""Grave Without a Stone seed catalogue bot.

Submitting seeds happens on a panel: a pinned message with one button per ranking.
A button opens a form for the seed, why it got that ranking, and images. Instant
Complete asks for the map, the building and where the flare gun is.

Slash commands:
  /panel       (admins) post the submission panel in this channel
  /checksetup  (admins) show which channel each ranking posts to
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
MAPS = [m.strip() for m in os.getenv("MAPS", "").split(",") if m.strip()][:25]
MAX_IMAGES = 10
BOT_NAME = os.getenv("BOT_NAME", "").strip()  # name on every channel post; defaults to the bot's own
CHECK_CHANNEL_NAMES = os.getenv("CHECK_CHANNEL_NAMES", "true").lower() != "false"
# A tier's channel name must contain this word, e.g. #great-seeds for "great"
CHANNEL_KEYWORDS = {"mediocre": "mediocre", "good": "good", "great": "great",
                    "amazing": "amazing", "perfect": "perfect", "instant": "instant"}
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".gif", ".webp")

TIER_CHOICES = [app_commands.Choice(name=v["label"], value=k) for k, v in TIERS.items()]

db = SeedDB(DB_PATH)


# ---------- embeds ----------

def seed_embed(s, image_name: str | None = None) -> discord.Embed:
    tier = TIERS[s.tier]
    e = discord.Embed(title=f"Seed: {s.seed}", color=tier["color"])
    e.add_field(name="Ranking", value=tier["label"], inline=True)
    e.add_field(name="Submitted by", value=f"<@{s.submitter_id}>", inline=True)
    if s.tier == "instant":
        e.add_field(name="Map", value=s.map, inline=True)
        e.add_field(name="Building", value=s.building, inline=True)
        e.add_field(name="Where the flare gun is", value=s.location[:1024], inline=False)
    else:
        e.add_field(name=f"Why it's {tier['label']}", value=s.reason[:1024], inline=False)
    if image_name:
        e.set_image(url=f"attachment://{image_name}")
    elif s.images:
        e.set_image(url=s.images.split("\n")[0])
    e.timestamp = datetime.fromtimestamp(s.created_at, tz=timezone.utc)
    e.set_footer(text=f"Catalogue entry #{s.id}")
    return e


def panel_embed() -> discord.Embed:
    e = discord.Embed(
        title="Seed Submissions",
        description=(
            "Found a seed worth sharing? Pick its ranking below and fill in the form.\n\n"
            "**Every seed:** the seed and why it earned that ranking. Images are optional "
            f"(up to {MAX_IMAGES}).\n"
            "**Instant Complete:** the map, the building, and exactly where the flare gun is.\n\n"
            "Seeds that are already catalogued are turned away, with a link to the existing post. "
            "Use **Look up a seed** to check first."
        ),
        color=0x5865F2,
    )
    e.set_footer(text="Grave Without a Stone seed catalogue")
    return e


def duplicate_message(existing) -> str:
    where = f" Posted here: {existing.message_url}" if existing.message_url else ""
    return (f"**{existing.seed}** is already catalogued as "
            f"**{TIERS[existing.tier]['label']}** by {existing.submitter_name}.{where}")


def seed_post(s, files=()) -> discord.ui.LayoutView:
    """The channel post: one card holding the details and every image, sent as one message."""
    tier = TIERS[s.tier]
    esc = discord.utils.escape_markdown
    header = discord.ui.TextDisplay(
        f"## Seed: {esc(s.seed)}\n**{tier['label']}** · submitted by <@{s.submitter_id}>")
    if s.tier == "instant":
        details = (f"**Map:** {esc(s.map)}\n**Building:** {esc(s.building)}\n"
                   f"**Where the flare gun is:** {esc(s.location)}")
    else:
        details = f"**Why it's {tier['label']}:** {esc(s.reason)}"
    items = [header, discord.ui.Separator(), discord.ui.TextDisplay(details)]
    if files:
        items.append(discord.ui.MediaGallery(
            *[discord.MediaGalleryItem(f"attachment://{f.filename}") for f in files]))
    items.append(discord.ui.TextDisplay(f"-# Catalogue entry #{s.id} · <t:{s.created_at}:f>"))
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(*items, accent_colour=tier["color"]))
    return view


# ---------- the bot ----------

class SeedBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.http_session: aiohttp.ClientSession | None = None
        self.channel_ids: dict[str, int] = {}   # tier -> channel its webhook posts to
        self.problems: dict[str, str] = {}      # tier -> why it can't take seeds right now

    async def verify_webhooks(self) -> None:
        """Check each ranking's webhook exists and posts to its own, correctly named channel."""
        self.channel_ids.clear()
        self.problems.clear()
        for tier, url in WEBHOOKS.items():
            label = TIERS[tier]["label"]
            if not url:
                self.problems[tier] = f"no webhook set (WEBHOOK_{tier.upper()} in .env)"
                continue
            try:
                hook = await discord.Webhook.from_url(url, session=self.http_session).fetch(prefer_auth=False)
            except (discord.HTTPException, ValueError):
                self.problems[tier] = f"the WEBHOOK_{tier.upper()} URL is invalid or the webhook was deleted"
                continue
            channel = self.get_channel(hook.channel_id)
            name = channel.name if channel else None
            if CHECK_CHANNEL_NAMES:
                if name is None:
                    self.problems[tier] = ("its webhook is in a channel the bot can't see. "
                                           "Make sure the bot is in that server")
                    continue
                if CHANNEL_KEYWORDS[tier] not in name.lower():
                    self.problems[tier] = (f"its webhook posts to #{name}, which doesn't look like the "
                                           f"{label} channel (the name should contain "
                                           f"\"{CHANNEL_KEYWORDS[tier]}\")")
                    continue
            self.channel_ids[tier] = hook.channel_id
        # Two rankings must never share a channel.
        seen: dict[int, str] = {}
        for tier, cid in list(self.channel_ids.items()):
            if cid in seen:
                for t in (tier, seen[cid]):
                    self.problems[t] = (f"{TIERS[tier]['label']} and {TIERS[seen[cid]]['label']} "
                                        "webhooks post to the same channel")
                    self.channel_ids.pop(t, None)
            else:
                seen[cid] = tier

    def post_identity(self) -> dict:
        """Same name and picture on every post, so Discord groups them under one header."""
        return {"username": BOT_NAME or self.user.display_name,
                "avatar_url": self.user.display_avatar.url}

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession()
        self.add_view(PanelView())  # keeps panel buttons working after restarts
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
    print(f"Logged in as {bot.user}. Seeds catalogued: {sum(db.counts().values())}")
    await bot.verify_webhooks()
    for tier, cid in bot.channel_ids.items():
        print(f"  {TIERS[tier]['label']:<17} -> #{bot.get_channel(cid) or cid}")
    for tier, why in bot.problems.items():
        print(f"  {TIERS[tier]['label']:<17} BLOCKED: {why}")


async def catalogue(interaction: discord.Interaction, *, seed: str, tier: str, reason: str,
                    map=None, building=None, location=None, images=()):
    """Save a seed and post it to its ranking channel. The interaction must already be deferred."""
    label = TIERS[tier]["label"]
    send = interaction.followup.send

    existing = db.get(seed)
    if existing:
        await send(duplicate_message(existing), ephemeral=True)
        return

    hook = bot.webhook(tier)
    if hook is None or tier in bot.problems or tier not in bot.channel_ids:
        why = bot.problems.get(tier, "it hasn't been checked yet")
        await send(f"**{label}** seeds can't be submitted right now: {why}. "
                   "Ask a server admin to fix it and run /checksetup.", ephemeral=True)
        return

    bad = [a.filename for a in images if not a.filename.lower().endswith(IMAGE_TYPES)]
    if bad:
        await send(f"Only images can be attached (PNG, JPG, GIF, WEBP). Remove: {', '.join(bad)}",
                   ephemeral=True)
        return

    try:
        entry = db.add(seed, tier, reason, interaction.user.id, str(interaction.user),
                       map=map, building=building, location=location)
    except KeyError:
        await send("Someone catalogued that seed a moment ago.", ephemeral=True)
        return
    except ValueError as err:
        await send(str(err), ephemeral=True)
        return

    try:
        files = []
        for i, a in enumerate(images, 1):
            f = await a.to_file()
            f.filename = f"seed-{entry.id}-{i}{os.path.splitext(a.filename)[1].lower()}"
            files.append(f)
        msg = await hook.send(view=seed_post(entry, files), files=files, wait=True,
                              allowed_mentions=discord.AllowedMentions.none(), **bot.post_identity())
        if msg.channel.id != bot.channel_ids[tier]:
            # Webhook was moved to another channel since the last check: undo and block.
            await hook.delete_message(msg.id)
            bot.problems[tier] = "its webhook was moved to a different channel"
            raise RuntimeError("webhook moved")
        db.set_message(entry.id, msg.id, msg.jump_url, [a.url for a in msg.attachments])
    except discord.HTTPException as err:
        db.remove(seed)  # keep the database and the channels in step
        if err.status == 413:
            reason_text = "the images are too large together. Try fewer or smaller images"
        else:
            reason_text = f"Discord returned error {err.status}. Check that the webhook URL is still valid"
        await send(f"Couldn't post to the {label} channel: {reason_text}. The seed wasn't saved.",
                   ephemeral=True)
        return
    except RuntimeError:
        db.remove(seed)
        await send(f"The {label} webhook now points at a different channel, so the seed wasn't "
                   "saved. Ask a server admin to run /checksetup.", ephemeral=True)
        return

    await send(f"Catalogued **{entry.seed}** as **{label}**. {msg.jump_url}", ephemeral=True)


# ---------- the panel ----------

class SeedForm(discord.ui.Modal):
    """The form a panel button opens. Discord allows five fields per form."""

    def __init__(self, tier: str):
        self.tier = tier
        label = TIERS[tier]["label"]
        super().__init__(title=f"Submit a {label} seed", timeout=900)

        self.seed = discord.ui.TextInput(max_length=100, placeholder="The seed exactly as the game shows it")
        self.add_item(discord.ui.Label(text="Seed", component=self.seed))

        if tier == "instant":
            if MAPS:
                self.map = discord.ui.Select(
                    options=[discord.SelectOption(label=m) for m in MAPS], placeholder="Pick the map")
            else:
                self.map = discord.ui.TextInput(max_length=100)
            self.add_item(discord.ui.Label(text="Map", component=self.map))
            self.building = discord.ui.TextInput(max_length=100, placeholder="e.g. the church")
            self.add_item(discord.ui.Label(text="Building", component=self.building))
            self.location = discord.ui.TextInput(
                style=discord.TextStyle.paragraph, max_length=500,
                placeholder="Floor, room and landmark, e.g. upstairs bedroom, under the bed")
            self.add_item(discord.ui.Label(text="Where the flare gun is", component=self.location))
        else:
            self.reason = discord.ui.TextInput(
                style=discord.TextStyle.paragraph, min_length=3, max_length=1000,
                placeholder="What makes it this good (or this bad)?")
            self.add_item(discord.ui.Label(text=f"Why is this seed {label}?", component=self.reason))

        self.images = discord.ui.FileUpload(required=False, max_values=MAX_IMAGES)
        self.add_item(discord.ui.Label(
            text="Images", description=f"Optional, up to {MAX_IMAGES} screenshots",
            component=self.images))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        fields = {"seed": self.seed.value, "tier": self.tier, "images": self.images.values}
        if self.tier == "instant":
            map_value = self.map.values[0] if isinstance(self.map, discord.ui.Select) else self.map.value
            fields.update(reason="Instant complete", map=map_value,
                          building=self.building.value, location=self.location.value)
        else:
            fields["reason"] = self.reason.value
        await catalogue(interaction, **fields)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"Form error: {error!r}")
        msg = "Something went wrong saving that seed. Please try again."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


class LookupForm(discord.ui.Modal, title="Look up a seed"):
    seed = discord.ui.TextInput(label="Seed", max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        await send_lookup(interaction, self.seed.value)


def tier_button(tier: str, style: discord.ButtonStyle, row: int):
    async def callback(interaction: discord.Interaction):
        await interaction.response.send_modal(SeedForm(tier))
    b = discord.ui.Button(label=TIERS[tier]["label"], style=style,
                          custom_id=f"seedpanel:{tier}", row=row)
    b.callback = callback
    return b


class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        grey, green, blue, red = (discord.ButtonStyle.secondary, discord.ButtonStyle.success,
                                  discord.ButtonStyle.primary, discord.ButtonStyle.danger)
        for tier, style in (("mediocre", grey), ("good", green), ("great", blue),
                            ("amazing", blue), ("perfect", green)):
            self.add_item(tier_button(tier, style, row=0))
        self.add_item(tier_button("instant", red, row=1))

    @discord.ui.button(label="Look up a seed", style=discord.ButtonStyle.secondary,
                       custom_id="seedpanel:lookup", row=1)
    async def lookup_button(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(LookupForm())


# ---------- commands ----------

@bot.tree.command(description="Post the seed submission panel in this channel (admins)")
@app_commands.default_permissions(manage_guild=True)
async def panel(interaction: discord.Interaction):
    await interaction.channel.send(embed=panel_embed(), view=PanelView())
    await interaction.response.send_message(
        "Panel posted. Pin it so it stays easy to find.", ephemeral=True)


@bot.tree.command(description="Check which channel each ranking posts to (admins)")
@app_commands.default_permissions(manage_guild=True)
async def checksetup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    await bot.verify_webhooks()
    lines = []
    for tier, v in TIERS.items():
        if tier in bot.channel_ids:
            lines.append(f"✅ **{v['label']}** → <#{bot.channel_ids[tier]}>")
        else:
            lines.append(f"❌ **{v['label']}**: {bot.problems.get(tier, 'not checked')}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


async def send_lookup(interaction: discord.Interaction, seed: str):
    s = db.get(seed)
    if not s:
        await interaction.response.send_message(
            f"**{seed}** isn't catalogued yet. Use the submission panel to add it.", ephemeral=True)
        return
    await interaction.response.send_message(content=s.message_url or None,
                                            embed=seed_embed(s), ephemeral=True)


@bot.tree.command(description="Check whether a seed is already catalogued")
async def lookup(interaction: discord.Interaction, seed: str):
    await send_lookup(interaction, seed)


@bot.tree.command(name="list", description="Browse catalogued seeds")
@app_commands.describe(ranking="Only show this ranking", page="Page number (25 per page)")
@app_commands.choices(ranking=TIER_CHOICES)
async def list_cmd(interaction: discord.Interaction,
                   ranking: app_commands.Choice[str] | None = None,
                   page: app_commands.Range[int, 1, 1000] = 1):
    tier = ranking.value if ranking else None
    rows = db.list(tier=tier, limit=25, offset=(page - 1) * 25)
    title = f"{ranking.name if ranking else 'All'} seeds, page {page}"
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
        file=discord.File(io.BytesIO(data), filename=name), ephemeral=True)


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
        f"Removed **{s.seed}** ({TIERS[s.tier]['label']}).{note}", ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is missing. Copy .env.example to .env and fill it in.")
    bot.run(TOKEN)
