import discord
from discord import app_commands
from discord.ext import commands
from requests import get, post
from time import time
from datetime import datetime
import asyncio
import os
from dotenv import load_dotenv
from keep_alive import keep_alive

load_dotenv()

# Start Flask web server for uptime monitoring
keep_alive()

# ============ CONFIGURATION ============
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
ROBLOX_COOKIE = os.getenv('ROBLOX_COOKIE')
GROUP_ID = os.getenv('GROUP_ID', '58205447')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')

STOCK_CHANNEL_ID = 1452696556581945376
PENDING_CHANNEL_ID = 1461323551859675300
BUYER_ROLE_ID = 1415426910887874680
ADMIN_PURCHASES_CHANNEL_ID = 1461328282824867866

# Product URLs
SHIRT_URL_1 = 'https://roblox.com/catalog/71762183936778/1'
SHIRT_URL_5 = 'https://roblox.com/catalog/71505947663591/5'

# Prices
PRICE_1_ROBUX = 700
PRICE_1_USD = 4

# Emojis
EMOJI_ROBUX = '<:emoji:1459920013476626496>'
EMOJI_ARROW = '<:emoji:1452723011001127094>'
EMOJI_VALIDATE = '<:emoji:1455958141937127577>'

# Stock storage (in production, use a database)
stock = []  # List of dicts: [{'username': 'user', 'password': 'pass', 'cookie': 'cookie'}]
used_purchase_ids = set()

# Purchase history tracking
# Format: {'discord_id': [{'accounts': [...], 'date': datetime, 'quantity': int, 'robux': int}]}
purchase_history = {}

# ============ BOT SETUP ============
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
tree = bot.tree

def log(text):
    timestamp = datetime.utcfromtimestamp(time()).strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] → {text}")

# ============ STOCK FUNCTIONS ============
async def update_stock_channel():
    """Update stock channel name based on stock count"""
    try:
        channel = bot.get_channel(STOCK_CHANNEL_ID)
        if not channel:
            return
        
        stock_count = len(stock)
        
        if stock_count == 0:
            new_name = "🔴 (OUT OF STOCK)"
        elif stock_count == 1:
            new_name = "🟡 (1 ACCOUNT)"
        elif stock_count == 2:
            new_name = "🟡 (2 ACCOUNTS)"
        elif stock_count == 3:
            new_name = "🟡 (3 ACCOUNTS)"
        else:  # 4 or more
            new_name = f"🟢 ({stock_count} ACCOUNTS)"
        
        if channel.name != new_name:
            await channel.edit(name=new_name)
            log(f'📊 Updated stock channel: {new_name}')
            
        # Notify if stock is low (3 or less)
        if stock_count <= 3 and stock_count > 0:
            pending_channel = bot.get_channel(PENDING_CHANNEL_ID)
            if pending_channel:
                embed = discord.Embed(
                    title="Low Stock Alert",
                    description=f"Stock is running low!\n\n**Current Stock:** {stock_count} account(s)\n**Status:** Need more accounts",
                    color=0xFFA500  # Orange
                )
                embed.timestamp = datetime.utcnow()
                await pending_channel.send("@everyone", embed=embed)
                
        elif stock_count == 0:
            pending_channel = bot.get_channel(PENDING_CHANNEL_ID)
            if pending_channel:
                embed = discord.Embed(
                    title="Out of Stock",
                    description="**All accounts have been sold!**\n\nPlease add more stock immediately.",
                    color=0xFF0000  # Red
                )
                embed.timestamp = datetime.utcnow()
                await pending_channel.send("@everyone", embed=embed)
                
    except Exception as e:
        log(f'<:emoji:1456014722343108729> Error updating stock channel: {e}')

# ============ ROBLOX API FUNCTIONS ============
def get_roblox_user_id(username):
    try:
        response = post('https://users.roblox.com/v1/usernames/users', json={
            "usernames": [username],
            "excludeBannedUsers": True
        })
        data = response.json()
        if data.get('data') and len(data['data']) > 0:
            return data['data'][0]['id']
        return None
    except Exception as e:
        log(f'Error getting user ID: {e}')
        return None

def get_recent_sales(limit=10):
    try:
        response = get(
            f'https://economy.roblox.com/v2/groups/{GROUP_ID}/transactions?cursor=&limit={limit}&transactionType=Sale',
            cookies={'.ROBLOSECURITY': ROBLOX_COOKIE}
        )
        
        if response.status_code == 200:
            return response.json().get('data', [])
        else:
            log(f'Failed to get sales: {response.status_code}')
            return []
    except Exception as e:
        log(f'Error getting recent sales: {e}')
        return []

def check_user_purchase(username, user_id):
    try:
        recent_sales = get_recent_sales(limit=10)
        
        for sale in recent_sales:
            purchase_id = sale.get('idHash')
            
            if purchase_id in used_purchase_ids:
                continue
            
            if sale.get('agent', {}).get('id') == user_id:
                return True, sale
        
        return False, "No recent purchase found"
    except Exception as e:
        log(f'Error checking purchase: {e}')
        return False, str(e)

# ============ BOT EVENTS ============
@bot.event
async def on_ready():
    log(f'<:emoji:1458478740064440535> Logged in as {bot.user.name}')
    
    # Load existing purchases
    try:
        existing_sales = get_recent_sales(limit=50)
        for sale in existing_sales:
            used_purchase_ids.add(sale.get('idHash'))
        log(f'<:emoji:1458478740064440535> Marked {len(used_purchase_ids)} existing purchases as used')
    except Exception as e:
        log(f'Could not load existing purchases: {e}')
    
    # Update stock channel
    await update_stock_channel()
    
    try:
        synced = await tree.sync()
        log(f'<:emoji:1458478740064440535> Synced {len(synced)} commands')
    except Exception as e:
        log(f'<:emoji:1456014722343108729> Error syncing commands: {e}')

# ============ COMMANDS ============
@tree.command(name="buy", description="Purchase ranked account")
@app_commands.describe(
    username="Your Roblox username",
    quantity="Number of accounts (1 or 5)"
)
@app_commands.choices(quantity=[
    app_commands.Choice(name="1 Account", value=1),
    app_commands.Choice(name="5 Accounts", value=5)
])
async def buy_command(interaction: discord.Interaction, username: str, quantity: int):
    await interaction.response.defer(ephemeral=True)
    
    user_id = get_roblox_user_id(username)
    if not user_id:
        await interaction.followup.send(f"<:emoji:1456014722343108729> Roblox user '{username}' not found!", ephemeral=True)
        return
    
    # Check stock
    if len(stock) < quantity:
        await interaction.followup.send(
            f"<:emoji:1456014722343108729> Not enough stock! Available: {len(stock)}, Requested: {quantity}",
            ephemeral=True
        )
        return
    
    # Create purchase message
    if quantity == 1:
        message = f"**RANKED ELIGIBLE ACCOUNT**\n{PRICE_1_ROBUX} {EMOJI_ROBUX} / ${PRICE_1_USD} {EMOJI_ARROW}\n\nShirt link: {SHIRT_URL_1}"
    else:
        message = f"**RANKED ELIGIBLE ACCOUNTS (5)**\n3500 {EMOJI_ROBUX} / $15 {EMOJI_ARROW}\n\nShirt link: {SHIRT_URL_5}"
    
    # Create validate button
    class ValidateView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=1800)  # 30 minutes
        
        @discord.ui.button(label="Validate Purchase", style=discord.ButtonStyle.primary, emoji=EMOJI_VALIDATE)
        async def validate_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
            if button_interaction.user.id != interaction.user.id:
                await button_interaction.response.send_message("<:emoji:1456014722343108729> This is not your purchase!", ephemeral=True)
                return
            
            await button_interaction.response.defer(ephemeral=True)
            
            # Check stock again
            if len(stock) < quantity:
                # Send clean embed to pending channel
                pending_channel = bot.get_channel(PENDING_CHANNEL_ID)
                if pending_channel:
                    embed = discord.Embed(
                        title="Pending Order - No Stock",
                        description=f"**Customer:** {interaction.user.mention}\n**Discord:** {interaction.user.name}#{interaction.user.discriminator}\n**Roblox Username:** {username}\n**Quantity:** {quantity} account(s)\n\n**Status:** Waiting for stock to be added",
                        color=0xFF0000  # Red
                    )
                    embed.set_footer(text=f"User ID: {interaction.user.id}")
                    embed.timestamp = datetime.utcnow()
                    await pending_channel.send("@everyone", embed=embed)
                
                await button_interaction.followup.send(
                    "<:emoji:1456014722343108729> **Are you sure you want to buy?**\n\nThere is no stock available. You will be added to the waitlist.",
                    ephemeral=True
                )
                return
            
            # Monitor purchase
            asyncio.create_task(monitor_and_deliver(button_interaction, username, user_id, quantity))
    
    view = ValidateView()
    await interaction.followup.send(message, view=view, ephemeral=True)
    log(f'📦 Purchase request: {interaction.user.name} - Roblox: {username} - Quantity: {quantity}')

async def monitor_and_deliver(interaction, roblox_username, user_id, quantity):
    """Monitor purchase and deliver accounts"""
    log(f'Monitoring purchase for {roblox_username} ({quantity} accounts)')
    
    await interaction.followup.send("Waiting for purchase confirmation...", ephemeral=True)
    
    max_attempts = 60
    attempt = 0
    
    while attempt < max_attempts:
        purchased, result = check_user_purchase(roblox_username, user_id)
        
        if purchased:
            sale = result
            purchase_id = sale.get('idHash')
            used_purchase_ids.add(purchase_id)
            
            log(f'<:emoji:1458478740064440535> Purchase confirmed for {roblox_username}! Delivering...')
            
            # Get accounts from stock
            if len(stock) < quantity:
                await interaction.followup.send("<:emoji:1456014722343108729> Stock depleted! Contact admin.", ephemeral=True)
                return
            
            accounts = [stock.pop(0) for _ in range(quantity)]
            await update_stock_channel()
            
            # Send DM with accounts
            try:
                dm_channel = await interaction.user.create_dm()
                
                # Create account details message
                account_text = ""
                for i, acc in enumerate(accounts, 1):
                    account_text += f"**Account {i}:**\n```ts\n{acc['username']}:{acc['password']}```\n"
                
                dm_message = f"**Here is your __ranked eligible account__**\n\n{account_text}\n**PC:** use ```ts user:Pass``` or **mobile** do `user:pass`\n\n**Cookie files attached below:**"
                
                # Create cookie files
                files = []
                for i, acc in enumerate(accounts, 1):
                    cookie_content = acc['cookie']
                    file = discord.File(
                        fp=cookie_content.encode(),
                        filename=f"account_{i}_cookie.txt"
                    )
                    files.append(file)
                
                await dm_channel.send(dm_message, files=files)
                log(f'📧 Delivered {quantity} account(s) to {interaction.user.name}')
                
                # Generate custom order ID
                import random
                import string
                order_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                
                # Track purchase in history
                if interaction.user.id not in purchase_history:
                    purchase_history[interaction.user.id] = []
                
                purchase_data = {
                    'order_id': order_id,
                    'accounts': accounts,
                    'date': datetime.utcnow(),
                    'quantity': quantity,
                    'robux': sale.get('currency', {}).get('amount', 0),
                    'roblox_username': roblox_username,
                    'discord_user_id': interaction.user.id,
                    'discord_username': f"{interaction.user.name}#{interaction.user.discriminator}"
                }
                purchase_history[interaction.user.id].append(purchase_data)
                
                # Log to admin purchases channel
                try:
                    admin_channel = bot.get_channel(ADMIN_PURCHASES_CHANNEL_ID)
                    if admin_channel:
                        log_embed = discord.Embed(
                            title=f"📦 Order #{order_id}",
                            description="**New purchase delivered**",
                            color=0x00FF00  # Green
                        )
                        
                        log_embed.add_field(name="Discord User", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
                        log_embed.add_field(name="Roblox Username", value=roblox_username, inline=True)
                        log_embed.add_field(name="Quantity", value=f"{quantity} account(s)", inline=True)
                        log_embed.add_field(name="Robux Paid", value=f"{sale.get('currency', {}).get('amount', 0):,}", inline=True)
                        
                        # Add account details
                        for i, acc in enumerate(accounts, 1):
                            log_embed.add_field(
                                name=f"Account {i}",
                                value=f"**Username:** `{acc['username']}`\n**Password:** `{acc['password']}`\n**Cookie:** `{acc['cookie'][:50]}...`",
                                inline=False
                            )
                        
                        log_embed.set_footer(text=f"Order ID: {order_id}")
                        log_embed.timestamp = datetime.utcnow()
                        
                        await admin_channel.send(embed=log_embed)
                        log(f'📊 Logged order {order_id} to admin channel')
                except Exception as e:
                    log(f'Could not log to admin channel: {e}')
                
                # Assign buyer role
                try:
                    guild = interaction.guild
                    if guild:
                        member = guild.get_member(interaction.user.id)
                        if member:
                            buyer_role = guild.get_role(BUYER_ROLE_ID)
                            if buyer_role and buyer_role not in member.roles:
                                await member.add_roles(buyer_role)
                                log(f'<:emoji:1458478740064440535> Assigned buyer role to {interaction.user.name}')
                except Exception as e:
                    log(f'Could not assign buyer role: {e}')
                
                await interaction.followup.send(f"<:emoji:1458478740064440535> Purchase confirmed! Check your DMs!\n**Order ID:** `{order_id}`", ephemeral=True)
                
                # Send webhook notification
                if WEBHOOK_URL:
                    webhook_data = {
                        "embeds": [{
                            "title": "Purchase Completed",
                            "description": f"**User:** {interaction.user.mention}\n**Roblox:** {roblox_username}\n**Quantity:** {quantity}\n**Remaining Stock:** {len(stock)}",
                            "color": 10181046,
                            "timestamp": datetime.utcnow().isoformat()
                        }]
                    }
                    post(WEBHOOK_URL, json=webhook_data)
                
                return
                
            except discord.Forbidden:
                log(f'<:emoji:1456014722343108729> Cannot DM {interaction.user.name}')
                await interaction.followup.send("<:emoji:1456014722343108729> Cannot send DM! Enable DMs and contact admin.", ephemeral=True)
                # Put accounts back
                stock.extend(accounts)
                await update_stock_channel()
                return
            except Exception as e:
                log(f'<:emoji:1456014722343108729> Error delivering: {e}')
                await interaction.followup.send(f"<:emoji:1456014722343108729> Error: {str(e)}", ephemeral=True)
                stock.extend(accounts)
                await update_stock_channel()
                return
        
        await asyncio.sleep(30)
        attempt += 1
    
    log(f'Purchase timeout for {roblox_username}')
    await interaction.followup.send("Purchase not detected after 30 minutes.", ephemeral=True)

@tree.command(name="addstock", description="fr")
@app_commands.describe(account="fr")
async def addstock_command(interaction: discord.Interaction, account: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("<:emoji:1456014722343108729> Admin only!", ephemeral=True)
        return
    
    try:
        parts = account.split(':', 2)
        if len(parts) != 3:
            await interaction.response.send_message("<:emoji:1456014722343108729> Invalid format! Use: username:password:cookie", ephemeral=True)
            return
        
        username, password, cookie = parts
        stock.append({
            'username': username,
            'password': password,
            'cookie': cookie
        })
        
        await update_stock_channel()
        await interaction.response.send_message(f"<:emoji:1458478740064440535> Added account! Total stock: {len(stock)}", ephemeral=True)
        log(f'📦 Added stock: {username} - Total: {len(stock)}')
        
    except Exception as e:
        await interaction.response.send_message(f"<:emoji:1456014722343108729> Error: {str(e)}", ephemeral=True)

@tree.command(name="stock", description="fr")
async def stock_command(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("<:emoji:1456014722343108729> Admin only!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="📦 Stock Information",
        description=f"**Current Stock:** {len(stock)} account(s)",
        color=0x9b59b6  # Purple
    )
    
    if len(stock) > 0:
        accounts_list = "\n".join([f"{i+1}. `{acc['username']}`" for i, acc in enumerate(stock[:10])])
        if len(stock) > 10:
            accounts_list += f"\n...and {len(stock) - 10} more"
        embed.add_field(name="Accounts in Stock", value=accounts_list, inline=False)
    
    embed.timestamp = datetime.utcnow()
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="removestock", description="fr")
@app_commands.describe(username="fr")
async def removestock_command(interaction: discord.Interaction, username: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("<:emoji:1456014722343108729> Admin only!", ephemeral=True)
        return
    
    # Find and remove account
    for i, acc in enumerate(stock):
        if acc['username'].lower() == username.lower():
            removed = stock.pop(i)
            await update_stock_channel()
            await interaction.response.send_message(
                f"<:emoji:1458478740064440535> Removed account: `{removed['username']}`\nRemaining stock: {len(stock)}",
                ephemeral=True
            )
            log(f'🗑️ Removed stock: {removed["username"]} - Remaining: {len(stock)}')
            return
    
    await interaction.response.send_message(f"<:emoji:1456014722343108729> Account `{username}` not found in stock!", ephemeral=True)

@tree.command(name="topbuyers", description="fr")
async def topbuyers_command(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("<:emoji:1456014722343108729> Admin only!", ephemeral=True)
        return
    
    if not purchase_history:
        await interaction.response.send_message("📊 No purchase history yet!", ephemeral=True)
        return
    
    # Calculate total purchases per user
    buyer_stats = {}
    for user_id, purchases in purchase_history.items():
        total_accounts = sum(p['quantity'] for p in purchases)
        total_robux = sum(p['robux'] for p in purchases)
        total_purchases = len(purchases)
        buyer_stats[user_id] = {
            'accounts': total_accounts,
            'robux': total_robux,
            'purchases': total_purchases
        }
    
    # Sort by total ROBUX spent (not accounts)
    sorted_buyers = sorted(buyer_stats.items(), key=lambda x: x[1]['robux'], reverse=True)
    
    embed = discord.Embed(
        title="Top Buyers - All Time",
        description="Top customers by **total Robux spent**",
        color=0xFFD700  # Gold
    )
    
    for i, (user_id, stats) in enumerate(sorted_buyers[:10], 1):
        user = bot.get_user(user_id)
        username = user.name if user else f"User {user_id}"
        
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        medal = medals.get(i, f"#{i}")
        
        embed.add_field(
            name=f"{medal} {username}",
            value=f"**Robux Spent:** {stats['robux']:,}\n**Accounts:** {stats['accounts']}\n**Orders:** {stats['purchases']}",
            inline=True
        )
    
    embed.set_footer(text=f"Total Customers: {len(purchase_history)}")
    embed.timestamp = datetime.utcnow()
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="customerinfo", description="fr")
@app_commands.describe(user="fr")
async def customerinfo_command(interaction: discord.Interaction, user: discord.User):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("<:emoji:1456014722343108729> Admin only!", ephemeral=True)
        return
    
    if user.id not in purchase_history:
        await interaction.response.send_message(f"<:emoji:1456014722343108729> {user.name} has no purchase history!", ephemeral=True)
        return
    
    purchases = purchase_history[user.id]
    total_accounts = sum(p['quantity'] for p in purchases)
    total_robux = sum(p['robux'] for p in purchases)
    
    embed = discord.Embed(
        title=f"📊 Customer Info - {user.name}",
        description=f"**Discord:** {user.mention}\n**User ID:** {user.id}",
        color=0x9b59b6
    )
    
    embed.add_field(name="Total Accounts Purchased", value=str(total_accounts), inline=True)
    embed.add_field(name="Total Robux Spent", value=f"{total_robux:,}", inline=True)
    embed.add_field(name="Total Orders", value=str(len(purchases)), inline=True)
    
    # Show recent purchases
    recent = purchases[-5:]  # Last 5
    purchase_text = ""
    for i, p in enumerate(reversed(recent), 1):
        date_str = p['date'].strftime('%Y-%m-%d %H:%M')
        purchase_text += f"**{i}.** {p['quantity']} account(s) - {p['robux']} Robux - {date_str}\n"
    
    embed.add_field(name="Recent Purchases", value=purchase_text or "None", inline=False)
    
    embed.set_thumbnail(url=user.display_avatar.url if user.display_avatar else None)
    embed.timestamp = datetime.utcnow()
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="orderid", description="fr")
@app_commands.describe(order_id="fr")
async def orderid_command(interaction: discord.Interaction, order_id: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("<:emoji:1456014722343108729> Admin only!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    # Search for order ID in purchase history
    found_order = None
    found_user_id = None
    
    for user_id, purchases in purchase_history.items():
        for purchase in purchases:
            if purchase.get('order_id', '').upper() == order_id.upper():
                found_order = purchase
                found_user_id = user_id
                break
        if found_order:
            break
    
    if not found_order:
        await interaction.followup.send(f"<:emoji:1456014722343108729> Order ID `{order_id}` not found!", ephemeral=True)
        return
    
    # Send full order details to admin's DM
    try:
        dm_channel = await interaction.user.create_dm()
        
        embed = discord.Embed(
            title=f"📦 Order #{found_order['order_id']}",
            description="**Full Order Details**",
            color=0x9b59b6
        )
        
        # Buyer info
        buyer_user = bot.get_user(found_user_id)
        buyer_name = buyer_user.name if buyer_user else f"User {found_user_id}"
        
        embed.add_field(name="Discord Buyer", value=f"{buyer_name} ({found_user_id})", inline=False)
        embed.add_field(name="Roblox Username", value=found_order['roblox_username'], inline=True)
        embed.add_field(name="Quantity", value=f"{found_order['quantity']} account(s)", inline=True)
        embed.add_field(name="Robux Paid", value=f"{found_order['robux']:,}", inline=True)
        embed.add_field(name="Order Date", value=found_order['date'].strftime('%Y-%m-%d %H:%M:%S UTC'), inline=False)
        
        # Account details
        for i, acc in enumerate(found_order['accounts'], 1):
            embed.add_field(
                name=f"Account {i} - {acc['username']}",
                value=f"**Username:** `{acc['username']}`\n**Password:** `{acc['password']}`\n**Cookie:** `{acc['cookie'][:50]}...`",
                inline=False
            )
        
        embed.set_footer(text=f"Order ID: {found_order['order_id']}")
        embed.timestamp = found_order['date']
        
        # Send cookie files
        files = []
        for i, acc in enumerate(found_order['accounts'], 1):
            cookie_file = discord.File(
                fp=acc['cookie'].encode(),
                filename=f"{acc['username']}_cookie.txt"
            )
            files.append(cookie_file)
        
        await dm_channel.send(embed=embed, files=files)
        await interaction.followup.send(f"<:emoji:1458478740064440535> Order details sent to your DMs!", ephemeral=True)
        log(f"📋 {interaction.user.name} looked up order {order_id}")
        
    except discord.Forbidden:
        await interaction.followup.send("<:emoji:1456014722343108729> Cannot send DMs! Enable DMs.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"<:emoji:1456014722343108729> Error: {str(e)}", ephemeral=True)

@tree.command(name="announce", description="fr")
@app_commands.describe(
    channel="fr",
    message="fr"
)
async def announce_command(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("<:emoji:1456014722343108729> Admin only!", ephemeral=True)
        return
    
    # Get all members with buyer role
    buyer_role = interaction.guild.get_role(BUYER_ROLE_ID)
    if not buyer_role:
        await interaction.response.send_message("<:emoji:1456014722343108729> Buyer role not found!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="📢 Announcement",
        description=message,
        color=0xFF0000  # Red
    )
    embed.set_footer(text=f"Sent by {interaction.user.name}")
    embed.timestamp = datetime.utcnow()
    
    # Mention the role in the channel
    await channel.send(f"{buyer_role.mention}", embed=embed)
    await interaction.response.send_message(f"<:emoji:1458478740064440535> Announcement sent to {channel.mention}!", ephemeral=True)
    log(f"📢 {interaction.user.name} sent announcement to {channel.name}")

@tree.command(name="clearstock", description="fr")
async def clearstock_command(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("<:emoji:1456014722343108729> Admin only!", ephemeral=True)
        return
    
    # Confirmation
    class ConfirmView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=30)
            self.value = None
        
        @discord.ui.button(label="Yes, Clear All Stock", style=discord.ButtonStyle.danger)
        async def confirm_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
            if button_interaction.user.id != interaction.user.id:
                await button_interaction.response.send_message("<:emoji:1456014722343108729> Not your button!", ephemeral=True)
                return
            
            removed_count = len(stock)
            stock.clear()  # Clear the list
            
            await button_interaction.response.send_message(f"<:emoji:1458478740064440535> Cleared {removed_count} accounts from stock!", ephemeral=True)
            log(f"🗑️ {interaction.user.name} cleared all stock ({removed_count} accounts)")
            
            # Update stock channel to show out of stock
            await update_stock_channel()
            
            self.stop()
        
        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
            if button_interaction.user.id != interaction.user.id:
                await button_interaction.response.send_message("<:emoji:1456014722343108729> Not your button!", ephemeral=True)
                return
            
            await button_interaction.response.send_message("<:emoji:1456014722343108729> Cancelled", ephemeral=True)
            self.stop()
    
    view = ConfirmView()
    await interaction.response.send_message(
        f"**Are you sure you want to clear ALL stock?**\n\nThis will remove **{len(stock)} account(s)**!\n\nChannel will show: 🔴 (OUT OF STOCK)",
        view=view,
        ephemeral=True
    )

@tree.command(name="test", description="fr")
@app_commands.describe(
    user="fr",
    quantity="fr"
)
@app_commands.choices(quantity=[
    app_commands.Choice(name="1 Account", value=1),
    app_commands.Choice(name="5 Accounts", value=5)
])
async def test_command(interaction: discord.Interaction, user: discord.User, quantity: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("<:emoji:1456014722343108729> Admin only!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    # Check stock
    if len(stock) < quantity:
        await interaction.followup.send(
            f"<:emoji:1456014722343108729> Not enough stock! Available: {len(stock)}, Requested: {quantity}",
            ephemeral=True
        )
        return
    
    # Get accounts from stock (FREE - NO PURCHASE CHECK)
    accounts = [stock.pop(0) for _ in range(quantity)]
    await update_stock_channel()
    
    # Send DM with accounts (NO LOGGING, NO TRACKING)
    try:
        dm_channel = await user.create_dm()
        
        # Create account details message
        account_text = ""
        for i, acc in enumerate(accounts, 1):
            account_text += f"**Account {i}:**\n```ts\n{acc['username']}:{acc['password']}```\n"
        
        dm_message = f"**TEST DELIVERY - Here is your __ranked eligible account__**\n\n{account_text}\n**PC:** use ```ts user:Pass``` or **mobile** do `user:pass`\n\n**Cookie files attached below:**"
        
        # Create cookie files
        files = []
        for i, acc in enumerate(accounts, 1):
            cookie_content = acc['cookie']
            cookie_file = discord.File(
                fp=cookie_content.encode(),
                filename=f"account_{i}_cookie.txt"
            )
            files.append(cookie_file)
        
        await dm_channel.send(dm_message, files=files)
        
        # Assign buyer role
        try:
            guild = interaction.guild
            if guild:
                member = guild.get_member(user.id)
                if member:
                    buyer_role = guild.get_role(BUYER_ROLE_ID)
                    if buyer_role and buyer_role not in member.roles:
                        await member.add_roles(buyer_role)
                        log(f'<:emoji:1458478740064440535> Assigned buyer role to {user.name}')
        except Exception as e:
            log(f'Could not assign buyer role: {e}')
        
        await interaction.followup.send(
            f"<:emoji:1458478740064440535> Test delivery sent to {user.mention}!\n**Quantity:** {quantity} account(s)\n**No logging, no purchase required**",
            ephemeral=True
        )
        log(f"TEST: {interaction.user.name} sent {quantity} account(s) to {user.name} (FREE)")
        
    except discord.Forbidden:
        log(f'<:emoji:1456014722343108729> Cannot DM {user.name}')
        await interaction.followup.send(f"<:emoji:1456014722343108729> Cannot send DM to {user.mention}! Enable DMs.", ephemeral=True)
        # Put accounts back
        stock.extend(accounts)
        await update_stock_channel()
        return
    except Exception as e:
        log(f'<:emoji:1456014722343108729> Error in test delivery: {e}')
        await interaction.followup.send(f"<:emoji:1456014722343108729> Error: {str(e)}", ephemeral=True)
        stock.extend(accounts)
        await update_stock_channel()
        return

@tree.command(name="purchasehistory", description="View your purchase history")
@app_commands.describe(roblox_username="Your Roblox username")
async def purchasehistory_command(interaction: discord.Interaction, roblox_username: str):
    # Check if user has buyer role
    member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
    if not member or BUYER_ROLE_ID not in [role.id for role in member.roles]:
        await interaction.response.send_message("<:emoji:1456014722343108729> You need the Buyer role to use this command!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    # Get Roblox user ID
    user_id = get_roblox_user_id(roblox_username)
    if not user_id:
        await interaction.followup.send(f"<:emoji:1456014722343108729> Roblox user '{roblox_username}' not found!", ephemeral=True)
        return
    
    # Get ALL sales from group
    log(f"📊 Fetching all group sales for {roblox_username}...")
    all_purchases = []
    cursor = ""
    
    try:
        # Fetch sales with pagination (get all sales)
        for _ in range(10):  # Max 10 pages (100 sales)
            response = get(
                f'https://economy.roblox.com/v2/groups/{GROUP_ID}/transactions?cursor={cursor}&limit=100&transactionType=Sale',
                cookies={'.ROBLOSECURITY': ROBLOX_COOKIE}
            )
            
            if response.status_code != 200:
                break
            
            data = response.json()
            sales = data.get('data', [])
            
            # Filter sales by this user
            for sale in sales:
                if sale.get('agent', {}).get('id') == user_id:
                    all_purchases.append({
                        'date': datetime.strptime(sale.get('created', ''), '%Y-%m-%dT%H:%M:%S.%fZ'),
                        'robux': sale.get('currency', {}).get('amount', 0),
                        'item': sale.get('details', {}).get('name', 'Unknown Item'),
                        'purchase_id': sale.get('idHash', 'unknown')
                    })
            
            cursor = data.get('nextPageCursor', '')
            if not cursor:
                break
        
        if not all_purchases:
            await interaction.followup.send(
                f"<:emoji:1456014722343108729> No purchase history found for Roblox user '{roblox_username}'!",
                ephemeral=True
            )
            return
        
        # Sort by date (newest first)
        all_purchases.sort(key=lambda x: x['date'], reverse=True)
        
        await interaction.followup.send(
            f"📧 Found {len(all_purchases)} purchase(s)! Sending to DMs...",
            ephemeral=True
        )
        
        # Send to DMs
        dm_channel = await interaction.user.create_dm()
        
        # Header embed
        header_embed = discord.Embed(
            title=f"📦 Purchase History for {roblox_username}",
            description=f"**Total Purchases:** {len(all_purchases)}\n**Total Robux Spent:** {sum(p['robux'] for p in all_purchases):,}",
            color=0x9b59b6
        )
        header_embed.set_footer(text="All group sales from transaction history")
        header_embed.timestamp = datetime.utcnow()
        await dm_channel.send(embed=header_embed)
        
        # Send purchases (10 per embed to avoid limits)
        for page_num, i in enumerate(range(0, len(all_purchases), 10), 1):
            page_purchases = all_purchases[i:i+10]
            
            embed = discord.Embed(
                title=f"📄 Page {page_num}",
                color=0x9b59b6
            )
            
            for j, purchase in enumerate(page_purchases, 1):
                date_str = purchase['date'].strftime('%Y-%m-%d %H:%M:%S UTC')
                embed.add_field(
                    name=f"Purchase {i+j}",
                    value=f"**Date:** {date_str}\n**Item:** {purchase['item']}\n**Robux:** {purchase['robux']:,}\n**ID:** `{purchase['purchase_id'][:16]}...`",
                    inline=False
                )
            
            embed.set_footer(text=f"Page {page_num}/{(len(all_purchases)-1)//10 + 1}")
            await dm_channel.send(embed=embed)
            
            if i + 10 < len(all_purchases):
                await asyncio.sleep(1)  # Rate limit
        
        # Check if we have delivered accounts for any of these purchases
        delivered_accounts = []
        if interaction.user.id in purchase_history:
            for tracked_purchase in purchase_history[interaction.user.id]:
                if tracked_purchase.get('roblox_username', '').lower() == roblox_username.lower():
                    delivered_accounts.extend(tracked_purchase['accounts'])
        
        if delivered_accounts:
            # Send delivered accounts
            accounts_embed = discord.Embed(
                title="Delivered Accounts",
                description=f"Accounts that were delivered to you for {roblox_username}:",
                color=0x00FF00
            )
            
            for i, acc in enumerate(delivered_accounts, 1):
                accounts_embed.add_field(
                    name=f"Account {i}",
                    value=f"```\n{acc['username']}:{acc['password']}\n```",
                    inline=False
                )
            
            # Send cookie files
            files = []
            for i, acc in enumerate(delivered_accounts, 1):
                cookie_file = discord.File(
                    fp=acc['cookie'].encode(),
                    filename=f"account_{i}_cookie.txt"
                )
                files.append(cookie_file)
            
            await dm_channel.send(embed=accounts_embed, files=files)
        
        log(f"📧 Sent purchase history to {interaction.user.name} for Roblox: {roblox_username}")
        
    except discord.Forbidden:
        await interaction.followup.send("<:emoji:1456014722343108729> Cannot send DMs! Enable DMs and try again.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"<:emoji:1456014722343108729> Error: {str(e)}", ephemeral=True)
        log(f"<:emoji:1456014722343108729> Error fetching history: {e}")

# ============ RUN BOT ============
if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print("<:emoji:1456014722343108729> ERROR: Set DISCORD_BOT_TOKEN!")
    else:
        log('🚀 Starting bot...')
        bot.run(DISCORD_BOT_TOKEN)
