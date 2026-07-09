import discord
from discord.ext import commands
from discord import app_commands
import datetime
import os
import threading
from flask import Flask

# ---------- KONFIGURATION ----------
TOKEN = os.getenv('DISCORD_TOKEN')

# Deine IDs
STAFF_ROLE_ID = 1523143819493773363
TICKET_CHANNEL_ID = 1523143872040140951
TICKET_CATEGORY_ID = 1523143855271186512

# -----------------------------------

# Flask Server für Render
app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is alive!"

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

# Aktive Tickets tracken
active_tickets = set()


# ---------- TICKET VIEWS ----------
class TicketView(discord.ui.View):
    """View with two buttons: Buy and Support"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🛒 Buy Ticket", style=discord.ButtonStyle.success, custom_id="buy_ticket")
    async def buy_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "buy")

    @discord.ui.button(label="🆘 Support Ticket", style=discord.ButtonStyle.primary, custom_id="support_ticket")
    async def support_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "support")

    async def create_ticket(self, interaction: discord.Interaction, ticket_type: str):
        # Check if user already has an open ticket
        for channel in interaction.guild.channels:
            if isinstance(channel, discord.TextChannel) and channel.name.startswith(f"{ticket_type}-{interaction.user.id}"):
                await interaction.response.send_message("You already have an open ticket!", ephemeral=True)
                return

        # Permissions for the ticket channel
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        category = interaction.guild.get_channel(TICKET_CATEGORY_ID)
        if not category:
            await interaction.response.send_message("Ticket category not found! Contact an admin.", ephemeral=True)
            return

        # Create channel with type-specific name
        channel_name = f"{ticket_type}-{interaction.user.id}"
        channel = await interaction.guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"{ticket_type.capitalize()} ticket from {interaction.user} (ID: {interaction.user.id})"
        )

        active_tickets.add(channel.id)

        # Welcome message with Close button
        embed = discord.Embed(
            title=f"🎫 {ticket_type.capitalize()} Ticket Created",
            description=f"Hello {interaction.user.mention},\n\nPlease describe your issue. The team will assist you shortly.\n\n**Ticket Type:** {ticket_type.capitalize()}\n\nClick the **Close** button below to close this ticket.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        embed.set_footer(text="Ticket System")

        view = CloseTicketView(channel.id)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ {ticket_type.capitalize()} ticket created: {channel.mention}", ephemeral=True)


class CloseTicketView(discord.ui.View):
    """View with Close button for tickets"""
    def __init__(self, channel_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel.id != self.channel_id:
            await interaction.response.send_message("You can only close this ticket in the ticket channel!", ephemeral=True)
            return

        # Check if user is authorized (ticket creator or staff)
        is_staff = interaction.user.guild_permissions.manage_channels or any(role.id == STAFF_ROLE_ID for role in interaction.user.roles)
        ticket_owner_id = int(interaction.channel.topic.split("ID: ")[-1].strip())
        
        if not is_staff and interaction.user.id != ticket_owner_id:
            await interaction.response.send_message("You are not authorized to close this ticket!", ephemeral=True)
            return

        # Modal for closing reason
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

                # Farewell message
                embed = discord.Embed(
                    title="🔒 Ticket Closed",
                    description=f"Closed by {modal_interaction.user.mention}\nReason: {reason}",
                    color=discord.Color.dark_red(),
                    timestamp=datetime.datetime.now(datetime.UTC)
                )
                await channel.send(embed=embed)

                # Create transcript
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

                # Send transcript to closer
                try:
                    await modal_interaction.user.send(
                        f"📄 Transcript for {channel.mention}",
                        file=transcript_file
                    )
                except:
                    pass  # If DMs are disabled

                # Delete channel
                await channel.delete()
                active_tickets.discard(channel.id)

                await modal_interaction.response.send_message("Ticket closed!", ephemeral=True)

        await interaction.response.send_modal(CloseModal())


# ---------- BOT EVENTS ----------
@bot.event
async def on_ready():
    print(f'✅ Bot started as {bot.user} (ID: {bot.user.id})')
    print('-' * 30)
    
    # Register persistent view
    bot.add_view(TicketView())
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f'✅ {len(synced)} Slash-Commands synchronized')
    except Exception as e:
        print(f'❌ Error during sync: {e}')
    
    print('-' * 30)
    print('Bot is ready!')


# ---------- !PANEL COMMAND ----------
@bot.command(name='panel')
@commands.has_role(STAFF_ROLE_ID)
async def panel(ctx):
    """Sends the ticket embed with Buy and Support buttons"""
    channel = bot.get_channel(TICKET_CHANNEL_ID)
    
    if not channel:
        await ctx.send("❌ Ticket channel not found! Check the ID.")
        return
    
    embed = discord.Embed(
        title="🎫 Support & Buy Tickets",
        description="Click a button below to create a ticket:\n\n🛒 **Buy Ticket** - For purchase inquiries\n🆘 **Support Ticket** - For general support\n\nOur team will assist you shortly!",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Ticket System - Click a button")
    
    view = TicketView()
    await channel.send(embed=embed, view=view)
    await ctx.send(f"✅ Ticket panel sent to {channel.mention}!")


# ---------- !CSM COMMAND ----------
@bot.command(name='csm')
@commands.has_role(STAFF_ROLE_ID)
async def csm(ctx, channel: discord.TextChannel, *, message: str):
    """Sends a normal message to a specific channel (Usage: !csm #channel Your message here)"""
    try:
        await channel.send(message)
        await ctx.send(f"✅ Message sent to {channel.mention}!", delete_after=5)
        
    except discord.Forbidden:
        await ctx.send(f"❌ I don't have permission to send messages in {channel.mention}!")
    except discord.HTTPException as e:
        await ctx.send(f"❌ Failed to send message: {e}")
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {e}")


# ---------- !CLEAR COMMAND ----------
@bot.command(name='clear')
@commands.has_role(STAFF_ROLE_ID)
async def clear_channel(ctx, channel: discord.TextChannel):
    """Clears all messages by deleting and recreating the channel (Usage: !clear #channel)"""
    
    # Confirm with the user
    await ctx.send(f"⚠️ Are you sure you want to **DELETE and RECREATE** {channel.mention}? This will delete **ALL** messages and is **IRREVERSIBLE**!\nReply with `yes` to confirm or `no` to cancel. (You have 15 seconds)")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["yes", "no"]
    
    try:
        response = await bot.wait_for('message', timeout=15.0, check=check)
        
        if response.content.lower() == "no":
            await ctx.send("❌ Clear command cancelled.")
            return
        
        # User confirmed with "yes"
        await ctx.send(f"🗑️ Deleting and recreating {channel.mention}...")
        
        # Save channel properties before deletion
        channel_name = channel.name
        channel_topic = channel.topic
        channel_position = channel.position
        channel_category = channel.category
        channel_slowmode_delay = channel.slowmode_delay
        channel_nsfw = channel.nsfw
        
        # Save permission overwrites
        overwrites = channel.overwrites
        
        # Delete the channel
        await channel.delete()
        
        # Create new channel with same properties
        new_channel = await ctx.guild.create_text_channel(
            name=channel_name,
            topic=channel_topic,
            position=channel_position,
            category=channel_category,
            slowmode_delay=channel_slowmode_delay,
            nsfw=channel_nsfw,
            overwrites=overwrites
        )
        
        # Send confirmation in the new channel
        embed = discord.Embed(
            title="🧹 Channel Cleared",
            description=f"Successfully **cleared** this channel!\n\nAll messages have been deleted and the channel was recreated with the same settings.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        embed.add_field(name="Channel Name", value=f"#{channel_name}", inline=True)
        embed.add_field(name="Category", value=channel_category.name if channel_category else "None", inline=True)
        embed.add_field(name="Cleared by", value=ctx.author.mention, inline=True)
        embed.set_footer(text=f"Channel ID: {new_channel.id}")
        
        await new_channel.send(embed=embed)
        
        # Also send a confirmation in the command channel
        await ctx.send(f"✅ Channel {new_channel.mention} has been successfully cleared and recreated!")
        
    except TimeoutError:
        await ctx.send("❌ Clear command timed out. Please try again and respond with `yes` or `no` within 15 seconds.")
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to delete or recreate this channel!")
    except discord.HTTPException as e:
        await ctx.send(f"❌ Failed to clear channel: {e}")
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {e}")


# ---------- !BAN COMMAND ----------
@bot.command(name='ban')
@commands.has_role(STAFF_ROLE_ID)
async def ban_user(ctx, member: discord.Member, *, reason="No reason provided"):
    """Bans a user"""
    if member == ctx.author:
        await ctx.send("❌ You can't ban yourself!")
        return
    
    if member.guild_permissions.administrator:
        await ctx.send("❌ You can't ban an admin!")
        return
    
    try:
        await member.ban(reason=reason)
        
        embed = discord.Embed(
            title="🔨 User Banned",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        embed.add_field(name="User", value=f"{member.mention} ({member.name}#{member.discriminator})", inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Banned by", value=ctx.author.mention, inline=False)
        embed.set_footer(text=f"User ID: {member.id}")
        
        await ctx.send(embed=embed)
        
        # DM the user
        try:
            dm_embed = discord.Embed(
                title="🔨 You have been banned",
                description=f"You were banned by **{ctx.author}**.\nReason: {reason}",
                color=discord.Color.dark_red()
            )
            await member.send(embed=dm_embed)
        except:
            pass
            
    except Exception as e:
        await ctx.send(f"❌ Error during ban: {e}")


# ---------- !KICK COMMAND ----------
@bot.command(name='kick')
@commands.has_role(STAFF_ROLE_ID)
async def kick_user(ctx, member: discord.Member, *, reason="No reason provided"):
    """Kicks a user"""
    if member == ctx.author:
        await ctx.send("❌ You can't kick yourself!")
        return
    
    if member.guild_permissions.administrator:
        await ctx.send("❌ You can't kick an admin!")
        return
    
    try:
        await member.kick(reason=reason)
        
        embed = discord.Embed(
            title="👢 User Kicked",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        embed.add_field(name="User", value=f"{member.mention} ({member.name}#{member.discriminator})", inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Kicked by", value=ctx.author.mention, inline=False)
        embed.set_footer(text=f"User ID: {member.id}")
        
        await ctx.send(embed=embed)
        
        # DM the user
        try:
            dm_embed = discord.Embed(
                title="👢 You have been kicked",
                description=f"You were kicked by **{ctx.author}**.\nReason: {reason}",
                color=discord.Color.orange()
            )
            await member.send(embed=dm_embed)
        except:
            pass
            
    except Exception as e:
        await ctx.send(f"❌ Error during kick: {e}")


# ---------- ERROR HANDLING ----------
@ban_user.error
async def ban_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ You don't have permission to use this command!")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ I'm missing permissions for this command!")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Member not found!")
    else:
        await ctx.send(f"❌ Error: {error}")

@kick_user.error
async def kick_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ You don't have permission to use this command!")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ I'm missing permissions for this command!")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Member not found!")
    else:
        await ctx.send(f"❌ Error: {error}")

@panel.error
async def panel_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ You don't have permission to use this command!")

@csm.error
async def csm_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ You don't have permission to use this command!")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("❌ Channel not found! Usage: `!csm #channel Your message`")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing arguments! Usage: `!csm #channel Your message`")
    else:
        await ctx.send(f"❌ Error: {error}")

@clear_channel.error
async def clear_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ You don't have permission to use this command!")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("❌ Channel not found! Usage: `!clear #channel`")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing argument! Usage: `!clear #channel`")
    else:
        await ctx.send(f"❌ Error: {error}")


# ---------- BOT START ----------
if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("❌ No token found! Set DISCORD_TOKEN Environment Variable.")
    
    # Start Flask server (for Render)
    keep_alive()
    
    # Start bot
    bot.run(TOKEN)
