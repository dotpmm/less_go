import os
import time
import hmac
import hashlib
import threading
import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL")
BOT_API_KEY_ID = "askbookie-bot"
BOT_API_SECRET = os.getenv("BOT_API_KEY")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

EMBED_COLOR = 0x57F287
ERROR_COLOR = 0xED4245
SUCCESS_COLOR = 0x57F287

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

def generate_hmac_headers(method: str, path: str) -> dict:
    timestamp = str(int(time.time()))
    message = f"{timestamp}\n{method.upper()}\n{path}"
    signature = hmac.new(BOT_API_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    return {
        "X-API-Key-Id": BOT_API_KEY_ID,
        "X-API-Signature": signature,
        "X-API-Timestamp": timestamp,
        "Content-Type": "application/json"
    }


def split_text(text: str, max_length: int = 4000) -> list:
    if len(text) <= max_length:
        return [text]
    chunks = []
    lines = text.split('\n')
    current_chunk = ""
    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk)
            if len(line) > max_length:
                for i in range(0, len(line), max_length):
                    chunks.append(line[i:i + max_length])
                current_chunk = ""
            else:
                current_chunk = line
        else:
            current_chunk = current_chunk + "\n" + line if current_chunk else line
    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def create_answer_embeds(question: str, answer: str, sources: list, model: dict, collection: str, request_id: str) -> list:
    chunks = split_text(answer)
    embeds = []
    for i, chunk in enumerate(chunks):
        embed = discord.Embed(color=EMBED_COLOR)
        if i == 0:
            embed.title = question[:256]
        embed.description = chunk
        if i == len(chunks) - 1:
            if sources:
                source_str = ", ".join([f"`{s}`" for s in sources[:10]])
                embed.add_field(name="Slides", value=source_str, inline=True)
            embed.add_field(name="Collection", value=collection, inline=True)
            embed.set_footer(text=f"Page {i + 1}/{len(chunks)} | {model.get('name', 'Unknown')} | {request_id}")
        else:
            embed.set_footer(text=f"Page {i + 1}/{len(chunks)}")
        embeds.append(embed)
    return embeds


def create_error_embed(title: str, description: str) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=ERROR_COLOR)
    embed.set_footer(text="AskBookie Bot")
    return embed


def create_history_embeds(history: list, total: int, limit: int, offset: int) -> list:
    if not history:
        embed = discord.Embed(title="Query History", description="No history found.", color=EMBED_COLOR)
        embed.set_footer(text="AskBookie Bot")
        return [embed]
    embeds = []
    for i, item in enumerate(history[:10]):
        embed = discord.Embed(color=EMBED_COLOR)
        embed.title = f"Query #{item.get('id', offset + i + 1)}"
        query = item.get('query', 'N/A')[:200]
        answer = item.get('answer', 'N/A')[:500]
        embed.add_field(name="Question", value=query, inline=False)
        embed.add_field(name="Answer", value=answer + "..." if len(item.get('answer', '')) > 500 else answer, inline=False)
        embed.add_field(name="Subject", value=item.get('subject', 'N/A'), inline=True)
        embed.add_field(name="Key", value=item.get('key_id', 'N/A'), inline=True)
        embed.set_footer(text=f"{item.get('model_name', 'N/A')} | {item.get('latency_ms', 0):.0f}ms | Total: {total}")
        embeds.append(embed)
    return embeds


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Sync failed: {e}")


@tree.command(name="ask", description="Ask AskBookie a question")
@app_commands.describe(subject="Subject name", unit="Unit number (1-4)", question="Your question")
@app_commands.choices(
    subject=[
        app_commands.Choice(name="MES", value="mes"),
        app_commands.Choice(name="EVS", value="evs"),
        app_commands.Choice(name="Phyton", value="python"),
        app_commands.Choice(name="Physics", value="physics"),
        app_commands.Choice(name="EEE", value="eee"),
        app_commands.Choice(name="Chemistry", value="chemistry"),
        app_commands.Choice(name="EPD", value="epd"),
        app_commands.Choice(name="Statics", value="statics"),
        app_commands.Choice(name="Constitution", value="consti"),
    ],
    unit=[
        app_commands.Choice(name="Unit 1", value=1),
        app_commands.Choice(name="Unit 2", value=2),
        app_commands.Choice(name="Unit 3", value=3),
        app_commands.Choice(name="Unit 4", value=4),
    ]
)
async def ask(interaction: discord.Interaction, subject: str, unit: int, question: str):
    await interaction.response.defer()
    try:
        headers = generate_hmac_headers("POST", "/ask")
        payload = {"query": question, "subject": subject, "unit": unit}
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_BASE_URL}/ask", json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    embeds = create_answer_embeds(
                        question,
                        data.get("answer", "No answer"),
                        data.get("sources", []),
                        data.get("model", {}),
                        data.get("collection", "N/A"),
                        data.get("request_id", "N/A")
                    )
                    for embed in embeds:
                        await interaction.followup.send(embed=embed)
                elif resp.status == 401:
                    await interaction.followup.send(embed=create_error_embed("Unauthorized", "API authentication failed."))
                elif resp.status == 429:
                    await interaction.followup.send(embed=create_error_embed("Rate Limited", "Too many requests. Try again later."))
                else:
                    error = await resp.json()
                    await interaction.followup.send(embed=create_error_embed("Error", error.get("detail", "Unknown error")))
    except Exception as e:
        await interaction.followup.send(embed=create_error_embed("Error", str(e)[:200]))


@tree.command(name="history", description="View query history (admin only)")
@app_commands.describe(limit="Number of results", offset="Offset for pagination")
async def history(interaction: discord.Interaction, limit: int = 10, offset: int = 0):
    if interaction.user.id != ADMIN_USER_ID:
        await interaction.response.send_message(embed=create_error_embed("Forbidden", "Only the admin can view history."), ephemeral=True)
        return
    await interaction.response.defer()
    try:
        headers = generate_hmac_headers("GET", "/history")
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE_URL}/history?limit={limit}&offset={offset}", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    embeds = create_history_embeds(data.get("history", []), data.get("total", 0), limit, offset)
                    for embed in embeds:
                        await interaction.followup.send(embed=embed)
                elif resp.status == 403:
                    await interaction.followup.send(embed=create_error_embed("Forbidden", "Admin API key required."))
                else:
                    error = await resp.json()
                    await interaction.followup.send(embed=create_error_embed("Error", error.get("detail", "Unknown error")))
    except Exception as e:
        await interaction.followup.send(embed=create_error_embed("Error", str(e)[:200]))

app = Flask(__name__)

@app.route("/")
def health():
    return {"status": "ok", "bot": "AskBookie Discord Bot"}

@app.route("/health")
def health_check():
    return {"status": "healthy"}

def run_discord_bot():
    print("Starting Discord bot...")
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    discord_thread = threading.Thread(target=run_discord_bot, daemon=True)
    discord_thread.start()
    
    from gunicorn.app.base import BaseApplication
    
    class GunicornApp(BaseApplication):
        def __init__(self, application, options=None):
            self.options = options or {}
            self.application = application
            super().__init__()
        
        def load_config(self):
            for key, value in self.options.items():
                self.cfg.set(key.lower(), value)
        
        def load(self):
            return self.application
    
    port = int(os.getenv("PORT", 10000))
    options = {
        "bind": f"0.0.0.0:{port}",
        "workers": 1,
        "threads": 2,
        "accesslog": "-",
        "loglevel": "warning",
    }
    print(f"Starting gunicorn on port {port}...")
    GunicornApp(app, options).run()


