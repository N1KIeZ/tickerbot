import discord
from discord.ext import commands
from discord import app_commands
import datetime

# ---------- KONFIGURATION ----------
TOKEN = "MTUyMzcwNjIwODgwNzI5MzAwOQ.Gi0z7O.rjQ1mDiedjngAgcLVe1PjZJa-EoYHzgH5VV2RE"  # Setze deinen Token hier

# IDs aus deiner Nachricht
STAFF_ROLE_ID = 1523143819493773363  # Rolle die !ban, !kick, !panel nutzen darf
TICKET_CHANNEL_ID = 1523143872040140951  # Channel wo das Ticket-Embed gesendet wird
TICKET_CATEGORY_ID = 1523143855271186512  # Kategorie für Ticket-Channels

# -----------------------------------

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Aktive Tickets tracken (um Duplikate zu verhindern)
active_tickets = set()


class TicketView(discord.ui.View):
    """View mit Button zum Ticket öffnen"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📩 Ticket öffnen", style=discord.ButtonStyle.primary, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Prüfen ob User schon ein offenes Ticket hat
        for channel in interaction.guild.channels:
            if isinstance(channel, discord.TextChannel) and channel.name.startswith(f"ticket-{interaction.user.id}"):
                await interaction.response.send_message("Du hast bereits ein offenes Ticket!", ephemeral=True)
                return

        # Berechtigungen für den Ticket-Channel
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        category = interaction.guild.get_channel(TICKET_CATEGORY_ID)
        if not category:
            await interaction.response.send_message("Ticket-Kategorie nicht gefunden! Kontaktiere einen Admin.", ephemeral=True)
            return

        # Channel erstellen
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.id}",
            category=category,
            overwrites=overwrites,
            topic=f"Ticket von {interaction.user} (ID: {interaction.user.id})"
        )

        active_tickets.add(channel.id)

        # Willkommens-Nachricht mit Close-Button
        embed = discord.Embed(
            title="🎫 Ticket erstellt",
            description=f"Hallo {interaction.user.mention},\n\nBitte beschreibe dein Anliegen. Das Team wird dir schnellstmöglich helfen.\n\nZum Schließen klicke auf den **Close**-Button.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Ticket System")

        view = CloseTicketView(channel.id)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Ticket erstellt: {channel.mention}", ephemeral=True)


class CloseTicketView(discord.ui.View):
    """View mit Close-Button für Tickets"""
    def __init__(self, channel_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    @discord.ui.button(label="🔒 Ticket schließen", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel.id != self.channel_id:
            await interaction.response.send_message("Du kannst nur im Ticket-Channel schließen!", ephemeral=True)
            return

        # Prüfen ob User berechtigt ist (Ticket-Ersteller oder Staff)
        is_staff = interaction.user.guild_permissions.manage_channels or any(role.id == STAFF_ROLE_ID for role in interaction.user.roles)
        ticket_owner_id = int(interaction.channel.topic.split("ID: ")[-1].strip())
        
        if not is_staff and interaction.user.id != ticket_owner_id:
            await interaction.response.send_message("Du bist nicht berechtigt dieses Ticket zu schließen!", ephemeral=True)
            return

        # Modal für den Schließgrund
        class CloseModal(discord.ui.Modal, title="Ticket schließen"):
            reason = discord.ui.TextInput(
                label="Grund für das Schließen",
                style=discord.TextStyle.paragraph,
                placeholder="Optional...",
                required=False
            )

            async def on_submit(self, modal_interaction: discord.Interaction):
                reason = self.reason.value or "Kein Grund angegeben."
                channel = modal_interaction.channel

                # Abschiedsnachricht
                embed = discord.Embed(
                    title="🔒 Ticket geschlossen",
                    description=f"Geschlossen von {modal_interaction.user.mention}\nGrund: {reason}",
                    color=discord.Color.dark_red(),
                    timestamp=datetime.datetime.utcnow()
                )
                await channel.send(embed=embed)

                # Transcript erstellen
                transcript = f"Ticket geschlossen am {datetime.datetime.utcnow().isoformat()}\n"
                transcript += f"Channel: #{channel.name}\n"
                transcript += f"Eröffnet von: {channel.topic}\n"
                transcript += f"Geschlossen von: {modal_interaction.user}\n"
                transcript += f"Grund: {reason}\n\n=== Letzte 50 Nachrichten ===\n"
                
                async for msg in channel.history(limit=50):
                    transcript += f"[{msg.created_at}] {msg.author}: {msg.content}\n"

                transcript_file = discord.File(
                    fp=bytes(transcript, 'utf-8'),
                    filename=f"transcript-{channel.name}.txt"
                )

                # Transcript an den Schließer senden
                try:
                    await modal_interaction.user.send(
                        f"📄 Transcript für {channel.mention}",
                        file=transcript_file
                    )
                except:
                    pass  # Wenn DMs deaktiviert sind

                # Channel löschen
                await channel.delete()
                active_tickets.discard(channel.id)

                await modal_interaction.response.send_message("Ticket geschlossen!", ephemeral=True)

        await interaction.response.send_modal(CloseModal())


@bot.event
async def on_ready():
    print(f'✅ Bot gestartet als {bot.user} (ID: {bot.user.id})')
    print('-' * 30)
    
    # Persistent View registrieren
    bot.add_view(TicketView())
    
    # Slash-Commands synchronisieren
    try:
        synced = await bot.tree.sync()
        print(f'✅ {len(synced)} Slash-Commands synchronisiert')
    except Exception as e:
        print(f'❌ Fehler bei Sync: {e}')
    
    print('-' * 30)
    print('Bot ist bereit!')


# ---------- !PANEL COMMAND ----------
@bot.command(name='panel')
@commands.has_role(STAFF_ROLE_ID)
async def panel(ctx):
    """Sendet das Ticket-Embed in den Ticket-Channel"""
    channel = bot.get_channel(TICKET_CHANNEL_ID)
    
    if not channel:
        await ctx.send("❌ Ticket-Channel nicht gefunden! Prüfe die ID.")
        return
    
    embed = discord.Embed(
        title="🎫 Support Tickets",
        description="Klicke auf den Button unten, um ein Ticket zu erstellen.\nUnser Team wird dir schnellstmöglich helfen.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Ticket System - Klicke auf den Button")
    
    view = TicketView()
    await channel.send(embed=embed, view=view)
    await ctx.send(f"✅ Ticket-Panel wurde in {channel.mention} gesendet!")


# ---------- !BAN COMMAND ----------
@bot.command(name='ban')
@commands.has_role(STAFF_ROLE_ID)
async def ban_user(ctx, member: discord.Member, *, reason="Kein Grund angegeben"):
    """Bannt einen User"""
    if member == ctx.author:
        await ctx.send("❌ Du kannst dich nicht selbst bannen!")
        return
    
    if member.guild_permissions.administrator:
        await ctx.send("❌ Du kannst keinen Admin bannen!")
        return
    
    try:
        await member.ban(reason=reason)
        
        embed = discord.Embed(
            title="🔨 User gebannt",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="User", value=f"{member.mention} ({member.name}#{member.discriminator})", inline=False)
        embed.add_field(name="Grund", value=reason, inline=False)
        embed.add_field(name="Gebannt von", value=ctx.author.mention, inline=False)
        embed.set_footer(text=f"User ID: {member.id}")
        
        await ctx.send(embed=embed)
        
        # Optional: User per DM benachrichtigen
        try:
            dm_embed = discord.Embed(
                title="🔨 Du wurdest gebannt",
                description=f"Du wurdest von **{ctx.author}** gebannt.\nGrund: {reason}",
                color=discord.Color.dark_red()
            )
            await member.send(embed=dm_embed)
        except:
            pass
            
    except Exception as e:
        await ctx.send(f"❌ Fehler beim Bannen: {e}")


# ---------- !KICK COMMAND ----------
@bot.command(name='kick')
@commands.has_role(STAFF_ROLE_ID)
async def kick_user(ctx, member: discord.Member, *, reason="Kein Grund angegeben"):
    """Kickt einen User"""
    if member == ctx.author:
        await ctx.send("❌ Du kannst dich nicht selbst kicken!")
        return
    
    if member.guild_permissions.administrator:
        await ctx.send("❌ Du kannst keinen Admin kicken!")
        return
    
    try:
        await member.kick(reason=reason)
        
        embed = discord.Embed(
            title="👢 User gekickt",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="User", value=f"{member.mention} ({member.name}#{member.discriminator})", inline=False)
        embed.add_field(name="Grund", value=reason, inline=False)
        embed.add_field(name="Gekickt von", value=ctx.author.mention, inline=False)
        embed.set_footer(text=f"User ID: {member.id}")
        
        await ctx.send(embed=embed)
        
        # Optional: User per DM benachrichtigen
        try:
            dm_embed = discord.Embed(
                title="👢 Du wurdest gekickt",
                description=f"Du wurdest von **{ctx.author}** gekickt.\nGrund: {reason}",
                color=discord.Color.orange()
            )
            await member.send(embed=dm_embed)
        except:
            pass
            
    except Exception as e:
        await ctx.send(f"❌ Fehler beim Kicken: {e}")


# ---------- FEHLERHANDLUNG ----------
@ban_user.error
async def ban_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ Du hast keine Berechtigung für diesen Befehl!")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Mir fehlen die Berechtigungen für diesen Befehl!")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Member nicht gefunden!")
    else:
        await ctx.send(f"❌ Fehler: {error}")

@kick_user.error
async def kick_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ Du hast keine Berechtigung für diesen Befehl!")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Mir fehlen die Berechtigungen für diesen Befehl!")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Member nicht gefunden!")
    else:
        await ctx.send(f"❌ Fehler: {error}")

@panel.error
async def panel_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ Du hast keine Berechtigung für diesen Befehl!")


# ---------- BOT STARTEN ----------
if __name__ == "__main__":
    bot.run(TOKEN)
