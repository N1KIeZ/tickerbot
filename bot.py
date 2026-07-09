import discord
from discord.ext import commands
from discord import app_commands
import datetime
import os
import threading
import json
import urllib.request
import urllib.error
from flask import Flask

# ---------- CONFIGURATION ----------
TOKEN = os.getenv('DISCORD_TOKEN')

# Your IDs
STAFF_ROLE_ID = 1523143819493773363
TICKET_CHANNEL_ID = 1523143872040140951
TICKET_CATEGORY_ID = 1523143855271186512

# Key system config
API_BASE = os.getenv('API_BASE', 'https://website-0bcg.onrender.com')
BOT_SECRET = os.getenv('BOT_SECRET', 'CHANGE_ME_TO_A_RANDOM_STRING')

# -----------------------------------

# Flask Server for Render
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 10000)))

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

# Discord Bot Setup
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Active tickets track
active_tickets = set()


# ---------- API HELPERS ----------
def api_post(path, data):
    """POST JSON to the website API."""
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        API_BASE + path,
        data=body,
        method='POST',
        headers={'Content-Type': 'application/json'}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode('utf-8'))
            return {'success': False, 'message': data.get('detail') or str(data)}
        except Exception:
            return {'success': False, 'message': f'HTTP {e.code}'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


# ---------- FILTER SYSTEM ----------
FILTER_WORDS = {
    "cheat": "scheat",
    "spoof": "w00fer",
    "hack": "h4ck",
    "crack": "cr4ck",
    "exploit": "3xpl01t",
    "bypass": "byp4ss",
    "inject": "1nj3ct",
    "mod": "m0d",
    "wallhack": "wallh4ck",
    "aimbot": "4imb0t",
    "scam": "sc4m",
    "fraud": "fr4ud"
}

filter_enabled = False

def get_filtered_words():
    return list(FILTER_WORDS.keys())

def get_suggestion(word):
    return FILTER_WORDS.get(word.lower(), "***")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        await bot.process_commands(message)
        return

    if filter_enabled:
        filtered_words = get_filtered_words()
        content_lower = message.content.lower()
        words = content_lower.split()

        for word in words:
            clean_word = ''.join(c for c in word if c.isalnum())

            if clean_word in filtered_words:
                try:
                    await message.delete()
                    suggestion = get_suggestion(clean_word)
                    warning = discord.Embed(
                        title="Message Filtered",
                        description=f"Your message was removed because it contained a blocked word.\n\nPlease use alternative words like **{suggestion}** instead.",
                        color=discord.Color.red(),
                        timestamp=datetime.datetime.now(datetime.UTC)
                    )
                    warning.set_footer(text=f"Filtered in #{message.channel.name}")
                    await message.channel.send(
                        f"{message.author.mention}",
                        embed=warning,
                        delete_after=10
                    )
                    break
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass

    await bot.process_commands(message)


# ---------- TICKET VIEWS ----------
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Buy Ticket", style=discord.ButtonStyle.success, custom_id="buy_ticket")
    async def buy_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "buy")

    @discord.ui.button(label="Support Ticket", style=discord.ButtonStyle.primary, custom_id="support_ticket")
    async def support_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "support")

    async def create_ticket(self, interaction: discord.Interaction, ticket_type: str):
        for channel in interaction.guild.channels:
            if isinstance(channel, discord.TextChannel) and channel.name.startswith(f"{ticket_type}-{interaction.user.id}"):
                await interaction.response.send_message("You already have an open ticket!", ephemeral=True)
                return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        category = interaction.guild.get_channel(TICKET_CATEGORY_ID)
        if not category:
            await interaction.response.send_message("Ticket category not found! Contact an admin.", ephemeral=True)
            return

        channel_name = f"{ticket_type}-{interaction.user.id}"
        channel = await interaction.guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"{ticket_type.capitalize()} ticket from {interaction.user} (ID: {interaction.user.id})"
        )

        active_tickets.add(channel.id)

        embed = discord.Embed(
            title=f"{ticket_type.capitalize()} Ticket Created",
            description=f"Hello {interaction.user.mention},\n\nPlease describe your issue. The team will assist you shortly.\n\n**Ticket Type:** {ticket_type.capitalize()}\n\nClick the **Close** button below to close this ticket.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        embed.set_footer(text="Ticket System")

        view = CloseTicketView(channel.id)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"{ticket_type.capitalize()} ticket created: {channel.mention}", ephemeral=True)


class CloseTicketView(discord.ui.View):
    def __init__(self, channel_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel.id != self.channel_id:
            await interaction.response.send_message("You can only close this ticket in the ticket channel!", ephemeral=True)
            return

        is_staff = interaction.user.guild_permissions.manage_channels or any(role.id == STAFF_ROLE_ID for role in interaction.user.roles)
        ticket_owner_id = int(interaction.channel.topic.split("ID: ")[-1].strip())

        if not is_staff and interaction.user.id != ticket_owner_id:
            await interaction.response.send_message("You are not authorized to close this ticket!", ephemeral=True)
            return

        class CloseModal(discord.ui.Modal, title="Close Ticket"):
            reason = discord.ui.TextInput(
                label="Reason for closing",
                style=discord.TextStyle.paragraph,
                placeholder="Optional...",
                required=False
            )

            async def on_submit(self, modal_interaction: discord.Interaction):
                reason = self.reason.value or "No reason provided."
                channel = modal_interaction.channel

                embed = discord.Embed(
                    title="Ticket Closed",
                    description=f"Closed by {modal_interaction.user.mention}\nReason: {reason}",
                    color=discord.Color.dark_red(),
                    timestamp=datetime.datetime.now(datetime.UTC)
                )
                await channel.send(embed=embed)

                transcript = f"Ticket closed at {datetime.datetime.now(datetime.UTC).isoformat()}\n"
                transcript += f"Channel: #{channel.name}\n"
                transcript += f"Opened by: {channel.topic}\n"
                transcript += f"Closed by: {modal_interaction.user}\n"
                transcript += f"Reason: {reason}\n\n=== Last 50 Messages ===\n"

                async for msg in channel.history(limit=50):
                    transcript += f"[{msg.created_at}] {msg.author}: {msg.content}\n"

                transcript_file = discord.File(
                    fp=bytes(transcript, 'utf-8'),
                    filename=f"transcript-{channel.name}.txt"
                )

                try:
                    await modal_interaction.user.send(
                        f"Transcript for {channel.mention}",
                        file=transcript_file
                    )
                except:
                    pass

                await channel.delete()
                active_tickets.discard(channel.id)
                await modal_interaction.response.send_message("Ticket closed!", ephemeral=True)

        await interaction.response.send_modal(CloseModal())


# ---------- BOT EVENTS ----------
@bot.event
async def on_ready():
    print(f'Bot started as {bot.user} (ID: {bot.user.id})')
    print('-' * 30)

    bot.add_view(TicketView())

    try:
        synced = await bot.tree.sync()
        print(f'{len(synced)} Slash-Commands synchronized')
    except Exception as e:
        print(f'Error during sync: {e}')

    print('-' * 30)
    print('Bot is ready!')


# ---------- !GENKEY COMMAND ----------
@bot.command(name='genkey')
@commands.has_role(STAFF_ROLE_ID)
async def genkey(ctx, duration: str = "lifetime", amount: int = 1):
    """
    Generate license keys with a specified duration.
    Usage: !genkey <duration> [amount]
    Durations: 5m, 30m, 1h, day, week, month, year, lifetime
    Examples:
      !genkey 5m       - One 5-minute key
      !genkey week 5   - Five 1-week keys
      !genkey lifetime - One lifetime key
    """
    if amount < 1 or amount > 25:
        await ctx.send("Amount must be between 1 and 25.")
        return

    result = api_post('/api/bot/genkey', {
        'duration': duration,
        'amount': amount,
        'secret': BOT_SECRET,
    })

    if not result.get('success'):
        await ctx.send(f"Failed to generate keys: {result.get('message', 'Unknown error')}\n> Debug: secret length={len(BOT_SECRET)}, first6={BOT_SECRET[:6]}...")
        return

    keys = result.get('keys', [])
    if not keys:
        await ctx.send("No keys were generated.")
        return

    embed = discord.Embed(
        title=f"Generated {len(keys)} Key(s)",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.UTC)
    )

    key_list = []
    for k in keys:
        exp = k.get('expires_at')
        dur = k.get('duration', 'lifetime')
        if exp:
            key_list.append(f"`{k['key']}` ({dur}, expires: {exp[:10]})")
        else:
            key_list.append(f"`{k['key']}` ({dur})")

    # Split into chunks if too many keys
    chunk_size = 10
    for i in range(0, len(key_list), chunk_size):
        chunk = key_list[i:i+chunk_size]
        embed.add_field(
            name=f"Keys {i+1}-{min(i+chunk_size, len(key_list))}",
            value="\n".join(chunk),
            inline=False
        )

    embed.set_footer(text=f"Generated by {ctx.author}")
    await ctx.send(embed=embed)

    # Also send as plain text for easy copying
    plain_keys = "\n".join([k['key'] for k in keys])
    try:
        await ctx.author.send(f"Your generated keys:\n```\n{plain_keys}\n```")
    except discord.Forbidden:
        pass


# ---------- !VERIFY COMMAND ----------
@bot.command(name='verify')
@commands.has_role(STAFF_ROLE_ID)
async def verify(ctx, key: str = None):
    """
    Verify a license key's validity.
    Usage: !verify <key>
    """
    if not key:
        await ctx.send("Usage: `!verify <key>`")
        return

    result = api_post('/api/bot/verify', {
        'key': key.strip(),
        'secret': BOT_SECRET,
    })

    status = result.get('status', 'unknown')
    valid = result.get('valid', False)
    message = result.get('message', 'Unknown')

    if status == 'banned':
        color = discord.Color.dark_red()
        emoji = "BANNED"
    elif status == 'expired':
        color = discord.Color.orange()
        emoji = "EXPIRED"
    elif status == 'invalid':
        color = discord.Color.red()
        emoji = "INVALID"
    elif status == 'not_found':
        color = discord.Color.red()
        emoji = "NOT FOUND"
    elif valid and status == 'available':
        color = discord.Color.blue()
        emoji = "UNUSED"
    elif valid and status == 'active':
        color = discord.Color.green()
        emoji = "ACTIVE"
    else:
        color = discord.Color.greyple()
        emoji = status.upper()

    embed = discord.Embed(
        title=f"Key Verification: {emoji}",
        description=f"**Key:** `{key.strip()}`\n**Status:** {message}",
        color=color,
        timestamp=datetime.datetime.now(datetime.UTC)
    )

    if result.get('duration'):
        embed.add_field(name="Duration", value=result['duration'], inline=True)
    if result.get('expires_at'):
        embed.add_field(name="Expires", value=result['expires_at'][:10], inline=True)
    if result.get('hwid'):
        embed.add_field(name="HWID", value=f"`{result['hwid'][:20]}...`", inline=False)
    if result.get('activated_at'):
        embed.add_field(name="Activated", value=result['activated_at'][:10], inline=True)

    embed.set_footer(text=f"Checked by {ctx.author}")
    await ctx.send(embed=embed)


# ---------- !REVOKE COMMAND ----------
@bot.command(name='revoke')
@commands.has_role(STAFF_ROLE_ID)
async def revoke(ctx, key: str = None):
    """
    Revoke (ban) a license key.
    Usage: !revoke <key>
    """
    if not key:
        await ctx.send("Usage: `!revoke <key>`")
        return

    result = api_post('/api/bot/revoke', {
        'key': key.strip(),
        'secret': BOT_SECRET,
    })

    if result.get('success'):
        embed = discord.Embed(
            title="Key Revoked",
            description=f"Key `{key.strip()}` has been **permanently revoked**.",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        embed.set_footer(text=f"Revoked by {ctx.author}")
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"Failed to revoke key: {result.get('message', 'Unknown error')}")


# ---------- !KEYS COMMAND ----------
@bot.command(name='keys')
@commands.has_role(STAFF_ROLE_ID)
async def keys_list(ctx):
    """
    List stock of available keys.
    Usage: !keys
    """
    result = api_post('/api/bot/verify', {'key': 'STOCK_CHECK', 'secret': BOT_SECRET})
    # Use a direct stock endpoint instead - let's just report from the API
    embed = discord.Embed(
        title="Key Stock",
        description="Use `!genkey`, `!verify <key>`, or `!revoke <key>` to manage keys.",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    embed.add_field(name="Generate", value="`!genkey <duration> [amount]`", inline=False)
    embed.add_field(name="Verify", value="`!verify <key>`", inline=False)
    embed.add_field(name="Revoke", value="`!revoke <key>`", inline=False)
    await ctx.send(embed=embed)


# ---------- PANEL COMMAND ----------
@bot.command(name='panel')
@commands.has_role(STAFF_ROLE_ID)
async def panel(ctx):
    channel = bot.get_channel(TICKET_CHANNEL_ID)

    if not channel:
        await ctx.send("Ticket channel not found! Check the ID.")
        return

    embed = discord.Embed(
        title="Support & Buy Tickets",
        description="Click a button below to create a ticket:\n\n**Buy Ticket** - For purchase inquiries\n**Support Ticket** - For general support\n\nOur team will assist you shortly!",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Ticket System - Click a button")

    view = TicketView()
    await channel.send(embed=embed, view=view)
    await ctx.send(f"Ticket panel sent to {channel.mention}!")


# ---------- FILTER COMMAND ----------
@bot.command(name='filter')
@commands.has_role(STAFF_ROLE_ID)
async def filter_command(ctx):
    global filter_enabled
    filter_enabled = not filter_enabled

    if filter_enabled:
        embed = discord.Embed(
            title="Global Filter ENABLED",
            description="The word filter is now **active** in **ALL** channels!",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        word_list = "\n".join([f"`{word}` -> `{FILTER_WORDS[word]}`" for word in FILTER_WORDS.keys()])
        embed.add_field(name="Filtered Words", value=word_list, inline=False)
        embed.set_footer(text=f"Enabled by {ctx.author}")
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="Global Filter DISABLED",
            description="The word filter is now **inactive** in all channels.",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        embed.set_footer(text=f"Disabled by {ctx.author}")
        await ctx.send(embed=embed)


# ---------- CSM COMMAND ----------
@bot.command(name='csm')
@commands.has_role(STAFF_ROLE_ID)
async def csm(ctx, channel: discord.TextChannel, *, message: str):
    try:
        await channel.send(message)
        await ctx.send(f"Message sent to {channel.mention}!", delete_after=5)
    except discord.Forbidden:
        await ctx.send(f"I don't have permission to send messages in {channel.mention}!")
    except discord.HTTPException as e:
        await ctx.send(f"Failed to send message: {e}")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")


# ---------- CLEAR COMMAND ----------
@bot.command(name='clear')
@commands.has_role(STAFF_ROLE_ID)
async def clear_channel(ctx, channel: discord.TextChannel):
    await ctx.send(f"Are you sure you want to **DELETE and RECREATE** {channel.mention}? This will delete **ALL** messages!\nReply with `yes` to confirm or `no` to cancel. (15 seconds)")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["yes", "no"]

    try:
        response = await bot.wait_for('message', timeout=15.0, check=check)

        if response.content.lower() == "no":
            await ctx.send("Clear command cancelled.")
            return

        await ctx.send(f"Deleting and recreating {channel.mention}...")

        channel_name = channel.name
        channel_topic = channel.topic
        channel_position = channel.position
        channel_category = channel.category
        channel_slowmode_delay = channel.slowmode_delay
        channel_nsfw = channel.nsfw
        overwrites = channel.overwrites

        await channel.delete()

        new_channel = await ctx.guild.create_text_channel(
            name=channel_name,
            topic=channel_topic,
            position=channel_position,
            category=channel_category,
            slowmode_delay=channel_slowmode_delay,
            nsfw=channel_nsfw,
            overwrites=overwrites
        )

        embed = discord.Embed(
            title="Channel Cleared",
            description=f"Successfully **cleared** this channel!",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        await new_channel.send(embed=embed)
        await ctx.send(f"Channel {new_channel.mention} has been successfully cleared!")

    except TimeoutError:
        await ctx.send("Clear command timed out.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to delete or recreate this channel!")
    except discord.HTTPException as e:
        await ctx.send(f"Failed to clear channel: {e}")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")


# ---------- PAYMENT COMMANDS ----------
@bot.command(name='ppl')
@commands.has_role(STAFF_ROLE_ID)
async def ppl(ctx):
    embed = discord.Embed(
        title="PayPal - Family & Friends",
        description="Please send the payment via **PayPal Family & Friends** to:",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    embed.add_field(name="Email", value="**irinamai1978@aim.com**", inline=False)
    embed.add_field(name="After Payment", value="Please send a **screenshot** of the payment proof.", inline=False)
    embed.set_footer(text="Payment System | PayPal")
    await ctx.send(embed=embed)


@bot.command(name='crypto')
@commands.has_role(STAFF_ROLE_ID)
async def crypto(ctx):
    embed = discord.Embed(
        title="Cryptocurrency Payment",
        description="Please send the payment to:",
        color=discord.Color.gold(),
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    embed.add_field(name="Wallet Address", value="**LKUStekx6U5e6VERZAE2ag9xeN5Pv7H4Ck**", inline=False)
    embed.add_field(name="Network", value="USDT (BEP-20 / ERC-20)", inline=False)
    embed.set_footer(text="Payment System | Cryptocurrency")
    await ctx.send(embed=embed)


# ---------- MODERATION ----------
@bot.command(name='ban')
@commands.has_role(STAFF_ROLE_ID)
async def ban_user(ctx, member: discord.Member, *, reason="No reason provided"):
    if member == ctx.author:
        await ctx.send("You can't ban yourself!")
        return
    if member.guild_permissions.administrator:
        await ctx.send("You can't ban an admin!")
        return
    try:
        await member.ban(reason=reason)
        embed = discord.Embed(title="User Banned", color=discord.Color.dark_red(),
                              timestamp=datetime.datetime.now(datetime.UTC))
        embed.add_field(name="User", value=f"{member.mention}", inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Banned by", value=ctx.author.mention, inline=False)
        await ctx.send(embed=embed)
        try:
            await member.send(f"You were banned by **{ctx.author}**.\nReason: {reason}")
        except:
            pass
    except Exception as e:
        await ctx.send(f"Error during ban: {e}")


@bot.command(name='kick')
@commands.has_role(STAFF_ROLE_ID)
async def kick_user(ctx, member: discord.Member, *, reason="No reason provided"):
    if member == ctx.author:
        await ctx.send("You can't kick yourself!")
        return
    if member.guild_permissions.administrator:
        await ctx.send("You can't kick an admin!")
        return
    try:
        await member.kick(reason=reason)
        embed = discord.Embed(title="User Kicked", color=discord.Color.orange(),
                              timestamp=datetime.datetime.now(datetime.UTC))
        embed.add_field(name="User", value=f"{member.mention}", inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Kicked by", value=ctx.author.mention, inline=False)
        await ctx.send(embed=embed)
        try:
            await member.send(f"You were kicked by **{ctx.author}**.\nReason: {reason}")
        except:
            pass
    except Exception as e:
        await ctx.send(f"Error during kick: {e}")


# ---------- ERROR HANDLING ----------
@genkey.error
async def genkey_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You don't have permission to use this command!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: `!genkey <duration> [amount]`\nDurations: `5m`, `30m`, `1h`, `day`, `week`, `month`, `year`, `lifetime`")
    else:
        await ctx.send(f"Error: {error}")

@verify.error
async def verify_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You don't have permission to use this command!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: `!verify <key>`")
    else:
        await ctx.send(f"Error: {error}")

@revoke.error
async def revoke_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You don't have permission to use this command!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: `!revoke <key>`")
    else:
        await ctx.send(f"Error: {error}")

@ban_user.error
async def ban_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You don't have permission to use this command!")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found!")
    else:
        await ctx.send(f"Error: {error}")

@kick_user.error
async def kick_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You don't have permission to use this command!")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found!")
    else:
        await ctx.send(f"Error: {error}")

@panel.error
async def panel_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You don't have permission to use this command!")

@csm.error
async def csm_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You don't have permission to use this command!")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("Channel not found! Usage: `!csm #channel Your message`")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing arguments! Usage: `!csm #channel Your message`")
    else:
        await ctx.send(f"Error: {error}")

@clear_channel.error
async def clear_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You don't have permission to use this command!")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("Channel not found! Usage: `!clear #channel`")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing argument! Usage: `!clear #channel`")
    else:
        await ctx.send(f"Error: {error}")

@filter_command.error
async def filter_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You don't have permission to use this command!")
    else:
        await ctx.send(f"Error: {error}")


# ---------- BOT START ----------
if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("No token found! Set DISCORD_TOKEN Environment Variable.")

    keep_alive()
    bot.run(TOKEN)
