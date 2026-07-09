import discord
from discord.ext import commands
from discord import app_commands
import datetime
import os
import asyncio
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
    return "✅ Bot ist am Leben!"

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

# ---------- DEIN BOT-CODE (TICKET, BAN, KICK, ETC.) HIER ----------
# (Den gesamten Code aus deiner vorherigen Datei hier einfügen!)

@bot.event
async def on_ready():
    print(f'✅ Bot gestartet als {bot.user} (ID: {bot.user.id})')
    print('-' * 30)
    
    bot.add_view(TicketView())
    
    try:
        synced = await bot.tree.sync()
        print(f'✅ {len(synced)} Slash-Commands synchronisiert')
    except Exception as e:
        print(f'❌ Fehler bei Sync: {e}')
    
    print('-' * 30)
    print('Bot ist bereit!')

# ... (Hier ALLE deine Commands: !panel, !ban, !kick, TicketView, CloseTicketView, etc.)

# ---------- BOT STARTEN ----------
if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("❌ Kein Token gefunden! Setze DISCORD_TOKEN Environment Variable.")
    
    # Flask Server starten (für Render)
    keep_alive()
    
    # Bot starten
    bot.run(TOKEN)
