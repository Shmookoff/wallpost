import discord
import vk
import psycopg2
import asyncio
import psycopg2.extras
import traceback
import sys
import texttable
import aiohttp
import time
from cryptography.fernet import Fernet
from vk import exceptions
from datetime import datetime
from discord.ext import commands, tasks
from discord.ext.commands import bot_has_permissions, has_permissions
from discord.errors import HTTPException
from config import settings


title, color = 'Открыть запись', 2590709
ERROR_title, ERROR_color = 'ERROR', 16711680


#ERRORS
class prefixGreaterThan3(Exception): pass
class channelNotSpecifiedError(Exception): pass
class MaximumWebhooksReached(Exception): pass
class vkIdNotSpecifiedError(Exception): pass
class vkWallBlockedError(Exception): pass
class subExists(Exception): pass
class noSubs(Exception): pass
class notSub(Exception): pass
class NotAuthenticated(Exception): pass


#FUNCTIONS
def get_prefix(client, message):
    with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
        with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(f"SELECT prefix FROM server WHERE id = {message.guild.id}")
            prefix = cur.fetchone()['prefix']
        dbcon.close

    if prefix == None: 
        return '.'
    else: 
        return prefix

def authenticate(token):
    session = vk.AuthSession(access_token=token)
    vkapi = vk.API(session)
    return vkapi

def group_compile_embed(group):
    group_embed = discord.Embed(
        title = group['name'],
        url = f'https://vk.com/public{group["id"]}',
        colour = color
    )
    group_embed.set_thumbnail(url = group['photo_200'])
    group_embed.add_field(
        name = 'Members',
        value = f'`{group["members_count"]}`',
        inline = True,
    )
    group_embed.add_field(
        name = 'Short address',
        value = f'`{group["screen_name"]}`',
        inline = True
    )
    if group['status'] != '':
        group_embed.add_field(
            name = 'Status',
            value = f'```{group["status"]}```',
            inline = False
        )
    if group['description'] != '':
        if len(group['description']) > 512:
            group_embed.add_field(
                name = 'Description',
                value = f'{group["description"][:512]}...',
                inline = False
            )
        else:
            group_embed.add_field(
                name = 'Description',
                value = f'{group["description"]}',
                inline = False
            )
    return group_embed
def user_compile_embed(user):
    user_embed = discord.Embed(
        title = f'{user["first_name"]} {user["last_name"]}',
        url = f'https://vk.com/id{user["id"]}',
        colour = color
    )
    user_embed.set_thumbnail(url = user['photo_max'])
    user_embed.add_field(
        name = 'Friends',
        value = f'`{user["counters"]["friends"]}`',
        inline = True
    )
    user_embed.add_field(
        name = "Short address",
        value = f'`{user["screen_name"]}`',
        inline = True
    )
    if 'followers_count' in user:
        user_embed.add_field(
            name = 'Followers',
            value = f'`{user["followers_count"]}`',
            inline = True
        )
    if user['status'] != '':
        user_embed.add_field(
            name = 'Status',
            value = f'```{user["status"]}```',
            inline = False
        )
    return user_embed

async def setup(ctx, action, messages, channel, wall, walli, embed):
    messages.append(await ctx.send(f'Is this the wall you requested?\nReact with ✅ or ❌', embed=embed))

    for emoji in ['✅', '❌']:
        await messages[0].add_reaction(emoji)

    try:
        r, u = await client.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message == messages[0] and r.emoji in ['✅', '❌'], timeout=120.0)
    except asyncio.TimeoutError:
        await ctx.channel.delete_messages(messages)
        messages = []
        await ctx.send('❌ Cancelled (timeout)')
    else:
        if r.emoji == '✅':
            await ctx.channel.delete_messages(messages)
            messages = []

            if wall == "g":
                name = walli['name']
            elif wall == "u":
                name = f'{walli["first_name"]} {walli["last_name"]}'
            
            if action == 'add':
                with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
                    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        cur.execute(f"SELECT EXISTS(SELECT 1 FROM subscription WHERE vk_id = {walli['id']} AND vk_type = \'{wall}\' AND channel_id = {channel.id})")
                        if cur.fetchone()['exists'] == False:
                            webhook = await channel.create_webhook(name=name)
                            cur.execute(f"INSERT INTO channel (id, server_id) VALUES({channel.id}, {ctx.guild.id}) ON CONFLICT DO NOTHING")
                            cur.execute(f"INSERT INTO subscription (vk_id, vk_type, webhook_url, channel_id) VALUES({walli['id']}, \'{wall}\', \'{webhook.url}\', {channel.id})")
                        else: raise subExists
                dbcon.close()
                
                await ctx.send(f'✅ Successfully subscribed {channel.mention} to **{name}** wall!')

            if action == 'del':
                with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
                    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        cur.execute(f"SELECT webhook_url FROM subscription WHERE channel_id = {channel.id} AND vk_id = {walli['id']} AND vk_type = \'{wall}\'")
                        async with aiohttp.ClientSession() as session:
                            await discord.Webhook.from_url(url=cur.fetchone()['webhook_url'], adapter=discord.AsyncWebhookAdapter(session)).delete()
                        cur.execute(f"DELETE FROM subscription WHERE channel_id = {channel.id} AND vk_id = {walli['id']} AND vk_type = \'{wall}\'")
                dbcon.close()

                await ctx.send(f'✅ Successfully unsubscrubed {channel.mention} from **{name}** wall!')

        else:
            await ctx.channel.delete_messages(messages)
            messages = []
            await ctx.send('❌ Cancelled')

def set_error_embed(d):
    error_embed = discord.Embed(title=ERROR_title, colour=ERROR_color, description=d)
    return error_embed

def add_command_and_example(ctx, error_embed, command, example):
    error_embed.add_field(
        name = 'Command',
        value = command,
        inline = False
    )
    error_embed.add_field(
        name = 'Example',
        value = example,
        inline = False
    )

def get_vk_info():
    vkapi = authenticate(settings['vkServiceKey'])
    vk_info = vkapi.groups.getById(group_id=22822305, v='5.130')
    vk = {'name': vk_info[0]['name'], 'photo': vk_info[0]['photo_200']}
    return vk


client = commands.Bot(command_prefix=get_prefix, activity=discord.Activity(name='.help', type='1'))
client.remove_command('help')


@client.event
async def on_ready():
    with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
        with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT id FROM server")
            guilds_in_db = cur.fetchall()
        guilds_connected = client.guilds

        guilds_connected_array = []
        guilds_in_db_array = []

        for guild in guilds_in_db:
            guilds_in_db_array.append(guild['id'])
        for guild in guilds_connected:
            guilds_connected_array.append(guild.id)

        for guild in guilds_connected_array:
            if not guild in guilds_in_db_array:
                with dbcon.cursor() as cur:
                    cur.execute("INSERT INTO server (id, key, key_uuid) VALUES(%s, %s, uuid_generate_v4())", (guild, Fernet.generate_key()))
        for guild in guilds_in_db_array:
            if not guild in guilds_connected_array:
                with dbcon.cursor() as cur:
                    cur.execute("DELETE FROM server WHERE id = %s", (guild))
    dbcon.close()

    print('Ready!')

@client.event
async def on_guild_join(guild):
    with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
        with dbcon.cursor() as cur:
            cur.execute("INSERT INTO server (id, key, key_uuid) VALUES(%s, %s, uuid_generate_v4())", (guild.id, Fernet.generate_key()))
    dbcon.close()

@client.event
async def on_guild_remove(guild):
    with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
        with dbcon.cursor() as cur:
            cur.execute(f"DELETE FROM server WHERE id = {guild.id}")
    dbcon.close()


@client.group(aliases=['h', '?'], invoke_without_command=True)
@bot_has_permissions(send_messages=True)
async def help(ctx):
    help_embed = discord.Embed(
        title = 'Help',
        description = f'Use `help (Command)` to show help for a command.',
        colour = color
    )

    help_embed.add_field(
        name = 'sub (s, subscriptions)',
        value = '`Work in progress.`\n\nSubcommands:\n```sub add [Channel Mention] [VK Wall]\n    Subscribes channel to updates on the wall.\n    Aliases: a\n\nsub info [Channel Mention]\n    Displays list of subscriptions for channel.\n    Aliases: i, information\n\nsub del [Channel Mention] [VK Wall]\n    Unsubscribes channel from updates on the wall.\n    Aliases: d, delete```',
        inline = False
    )

    help_embed.add_field(
        name = 'prefix (p)',
        value = '`Shows current prefix for the server.`\n\nSubcommands:\n```prefix set (Prefix)\n    Sets prefix for the server. If no Prefix passed, sets to default prefix — "."\n    Aliases: s```',
        inline = False
    )


    help_embed.add_field(
        name = 'help (h, ?)',
        value = '`Shows this message.`'
    )

    await ctx.send(embed=help_embed)


@client.group(aliases=['p'], invoke_without_command=True)
@bot_has_permissions(send_messages=True)
async def prefix(ctx):
    with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
        with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(f"SELECT prefix FROM server WHERE id = {ctx.guild.id}")
            prefix = cur.fetchone()['prefix']
    dbcon.close
    if prefix == None:
        await ctx.send(f'Prefix is "."')
    else:
        await ctx.send(f'Prefix is "{prefix}"')

@prefix.error
async def prefix_error(ctx, error):
    error_embed = None
    dm = False

    if isinstance(error, commands.BotMissingPermissions):
        if 'Send Messages' in str(error):
            dm = True
            error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')
            await ctx.message.author.send(embed=error_embed)
        else:
            error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')

    else:
        print(str(error))
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    if error_embed != None and dm == False:
        await ctx.send(embed=error_embed)

@prefix.command(aliases=['s'])
@bot_has_permissions(send_messages=True)
@has_permissions(administrator=True)
async def set(ctx, prefix: str=None):
    if prefix == None or len(prefix) <= 3:
        with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
            with dbcon.cursor() as cur:
                if prefix in [None, '.']:
                    cur.execute(f"UPDATE server SET prefix = NULL WHERE id = {ctx.guild.id};")
                    await ctx.send(f'Prefix is set to "." (default)')
                else:
                    cur.execute(f"UPDATE server SET prefix = '{prefix}' WHERE id = {ctx.guild.id};")
                    await ctx.send(f'Prefix is set to "{prefix}"')
    else: raise prefixGreaterThan3
    dbcon.close()

@set.error
async def prefix_set_error(ctx, error):
    error_embed = None
    dm = False

    if isinstance(error, commands.BotMissingPermissions):
        if 'Send Messages' in str(error):
            dm = True
            error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')
            await ctx.message.author.send(embed=error_embed)
        else:
            error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')

    elif isinstance(error, commands.MissingPermissions):
        error_embed = set_error_embed(f'You are missing permission(s).\n\n> {error}')

    elif isinstance(error, commands.CommandInvokeError):
        error = error.original

        if isinstance(error, prefixGreaterThan3):
            error_embed = set_error_embed(f'The length of prefix must be `<` or `=` `3`',)
            add_command_and_example(ctx, error_embed, f'`prefix set [Prefix]`', f'.p s !!!')

        else:
            print(str(error), str(error.original))
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    else: 
        print(str(error), str(error.original))
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
    
    if error_embed != None and dm == False:
        await ctx.send(embed=error_embed)


@has_permissions(administrator=True)
@client.group(aliases=['s', 'sub'], invoke_without_command=True)
async def subscriptions(ctx):
    with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
        with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(f"SELECT vk_id, token FROM server WHERE id = {ctx.guild.id}")
            vk_profile = cur.fetchone()
            vk_id, vk_token = vk_profile['vk_id'], vk_profile['token']
    dbcon.close

    if vk_id == None or vk_token == None: 
        await sub_set(ctx)

    else:
        vkapi = authenticate(vk_token)
        user_embed = user_compile_embed(vkapi.users.get(user_ids=vk_id, fields='photo_max,status,screen_name,followers_count,counters', v='5.130')[0])
        await ctx.send(f'This is the account that is linked to **{ctx.guild.name}**.\nYou can change it with `sub set` command.', embed=user_embed)
      

@subscriptions.error
async def subscriptions_error(ctx, error):
    error_embed = None
    dm = False

    if isinstance(error, commands.BotMissingPermissions):
        if 'Send Messages' in str(error):
            dm = True
            error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')
            await ctx.message.author.send(embed=error_embed)
        else:
            error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')

    elif isinstance(error, commands.MissingPermissions):
        error_embed = set_error_embed(f'You are missing permission(s).\n\n> {error}')   

    else: 
        print(str(error), str(error.original))
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    if error_embed != None and dm == False:
        await ctx.send(embed=error_embed)

@subscriptions.command(aliases=['s', 'set'])
@has_permissions(administrator=True)
async def sub_set(ctx):
    with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
        with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(f"SELECT key, key_uuid FROM server WHERE id = {ctx.guild.id}")
            res = cur.fetchone()
            key, key_uuid = res['key'], res['key_uuid']
    dbcon.close

    vk = get_vk_info()

    embed = discord.Embed(
        title = 'Authentication',
        url = f'https://posthound.herokuapp.com/oauth2/login?server_id={Fernet(key).encrypt(str(ctx.guild.id).encode()).decode()}&key_uuid={key_uuid}',
        description = 'Authenticate with your VK profile to be able to interact with VK walls.\n\n**Please, do not pass any arguments from link or link itself to 3rd parties. __It may result in security flaws.__**',
        colour = color
    )
    embed.set_thumbnail(url=vk['photo'])
    embed.set_footer(text=vk['name'], icon_url=vk['photo'])

    await ctx.send('Check your DM for an authentication link!')
    await ctx.author.send(embed=embed)

@sub_set.error
async def sub_set_error(ctx, error):
    error_embed = None
    dm = False

    if isinstance(error, commands.BotMissingPermissions):
        if 'Send Messages' in str(error):
            dm = True
            error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')
            await ctx.message.author.send(embed=error_embed)
        else:
            error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')

    elif isinstance(error, commands.MissingPermissions):
        error_embed = set_error_embed(f'You are missing permission(s).\n\n> {error}')   

    else: 
        print(str(error), str(error.original))
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    if error_embed != None and dm == False:
        await ctx.send(embed=error_embed)

@subscriptions.command(aliases=['a'])
@bot_has_permissions(manage_webhooks=True, add_reactions=True, manage_messages=True, read_message_history=True, send_messages=True)
@has_permissions(manage_webhooks=True)
async def add(ctx, vk_id: str=None, webhook_channel: discord.TextChannel=None):
    if webhook_channel == None: webhook_channel = ctx.channel
    ctx.webhook_channel = webhook_channel
    if webhook_channel == None: raise channelNotSpecifiedError
    elif vk_id == None: raise vkIdNotSpecifiedError
    elif len(await webhook_channel.webhooks()) == 10: raise MaximumWebhooksReached
    else:
        with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT token FROM server WHERE id = %s", (ctx.guild.id,))
                token = cur.fetchone()['token']
        dbcon.close

        if token == None: raise NotAuthenticated
        else: 
            vkapi = authenticate(token)

            try: groupi = vkapi.groups.getById(group_id=vk_id, fields="status,description,members_count", v='5.130')
            except Exception as error:
                if isinstance(error, exceptions.VkAPIError) and '100' in str(error):
                    groupi = [{'deactivated': True}]
            try: useri = vkapi.users.get(user_ids=vk_id, fields='photo_max,status,screen_name,followers_count,counters', v='5.130')
            except Exception as error:
                if isinstance(error, exceptions.VkAPIError) and '113' in str(error):
                    useri = [{'deactivated': True}]

            add.webhook_channel = webhook_channel
            if not 'deactivated' in groupi[0] and not 'deactivated' in useri[0]:
                group_embed = group_compile_embed(groupi[0])
                user_embed = user_compile_embed(useri[0])

                messages = []
                messages.append(await ctx.send(embed=group_embed))
                messages.append(await ctx.send('React with ⬆️ for **group** wall\nReact with ❌ for cancel\nReact with ⬇️ for **user** wall'))
                messages.append(await ctx.send(embed=user_embed))

                for emoji in ['⬆️', '❌', '⬇️']:
                    await messages[1].add_reaction(emoji)
                
                try:
                    r, u = await client.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message == messages[1] and r.emoji in ['⬆️', '❌', '⬇️'], timeout=120.0)
                except asyncio.TimeoutError:
                    await ctx.channel.delete_messages(messages)
                    messages = []
                    await ctx.send('❌ Cancelled (timeout)')
                else:
                    await ctx.channel.delete_messages(messages)
                    messages = []

                    if r.emoji == '⬆️':
                        await setup(ctx, 'add', messages, webhook_channel, 'g', groupi[0], group_embed)

                    elif r.emoji == '⬇️':
                        await setup(ctx, 'add', messages, webhook_channel, 'u', useri[0], user_embed)

                    else:
                        await ctx.send('❌ Cancelled')

            elif not 'deactivated' in groupi[0]:
                group_embed = group_compile_embed(groupi[0])
                
                messages = []
                
                await setup(ctx, 'add', messages, webhook_channel, 'g', groupi[0], group_embed)

            elif not 'deactivated' in useri[0]:
                user_embed = user_compile_embed(useri[0])

                messages = []

                await setup(ctx, 'add', messages, webhook_channel, 'u', useri[0], user_embed)

            else: raise vkWallBlockedError

@add.error
async def subscriptions_add_error(ctx, error):
    error_embed = None
    dm = False

    if isinstance(error, commands.BotMissingPermissions):
        if 'Send Messages' in str(error):
            dm = True
            error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')
            await ctx.message.author.send(embed=error_embed)
        else:
            error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')

    elif isinstance(error, commands.MissingPermissions):
        error_embed = set_error_embed(f'You are missing permission(s).\n\n> {error}')

    elif isinstance(error, commands.ChannelNotFound):
        error_embed = set_error_embed(f'Channel is not found.\n\n> Please, pass in `[Channel Mention]` as **Channel Mention** from current server.')
        add_command_and_example(ctx, error_embed, f'`subscriptions add [Channel Mention] [VK Wall]`', f'.s a {ctx.message.channel.mention} 1')

    elif isinstance(error, commands.BadArgument):
        error_embed = set_error_embed(f'One or more arguments are invalid.\n\n> Please, pass in `[Channel Mention]` as **Channel Mention** and `[VK Wall]` as **String**.')
        add_command_and_example(ctx, error_embed, f'`subscriptions add [Channel Mention] [VK Wall]`', f'.s a {ctx.message.channel.mention} 1')

    elif isinstance(error, commands.CommandInvokeError):
        error = error.original

        if isinstance(error, NotAuthenticated):
            error_embed = set_error_embed(f'You aren\'t authenticated.\n\n> Run `sub` command to link your VK profile.')

        elif isinstance(error, channelNotSpecifiedError):
            error_embed = set_error_embed(f'`[Channel Mention]` is not specified.\n\n> Please, specify `[Channel Mention]` as **Channel Mention**.')
            add_command_and_example(ctx, error_embed, f'`subscriptions add [Channel Mention] [VK Wall]`', f'.s a {ctx.message.channel.mention} 1')

        elif isinstance(error, vkIdNotSpecifiedError):
            error_embed = set_error_embed(f'`[VK Wall]` is not specified.\n\n> Please, specify `[VK Wall]` as **String**.')
            add_command_and_example(ctx, error_embed, f'`subscriptions add [Channel Mention] [VK Wall]`', f'.s a {ctx.message.channel.mention} 1')

        elif isinstance(error, vkWallBlockedError):
            error_embed = set_error_embed(f'`[VK Wall]` is invalid.\n\n> Wall **{ctx.args[1]}** may be blocked, deactivated, deleted or it may not exist.')

        elif isinstance(error, MaximumWebhooksReached):
            error_embed = set_error_embed(f'Maximum number of webhooks reached (10).\n> Try removing a webhook from {ctx.webhook_channel.mention}.')

        elif isinstance(error, subExists):
            error_embed = set_error_embed(f'{ctx.webhook_channel.mention} already subscribed to this wall.')

        else:
            print(error)
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    else: 
        print(str(error), str(error.original))
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    if error_embed != None and dm == False:
        await ctx.send(embed=error_embed)

@subscriptions.command(aliases=['i', 'info'])
@bot_has_permissions(send_messages=True)
@has_permissions(manage_webhooks=True)
async def information(ctx, channel: discord.TextChannel=None):
    if channel == None: channel = ctx.channel
    if channel == None: raise channelNotSpecifiedError
    else:
        with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT token FROM server WHERE id = %s", (ctx.guild.id,))
                token = cur.fetchone()['token']
        dbcon.close

        if token == None: raise NotAuthenticated
        else: 
            vkapi = authenticate(token)

            with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
                with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                    cur.execute(f"SELECT vk_id, vk_type FROM subscription WHERE channel_id = {channel.id}")
                    subs = cur.fetchall()
            dbcon.close

            embed = discord.Embed(
                title = f'Wall subscriptions',
                description = f'**for **{channel.mention}** channel:**',
                colour = color
            )

            table = texttable.Texttable(max_width=0)
            table.set_cols_align(['c','c','c','c'])
            table.header(['Name', 'Short address', 'Type', 'ID'])
            table.set_cols_dtype(['t','t','t','i'])
            table.set_chars(['─','│','┼','─'])

            if len(subs) > 0:
                groups, users = '', ''
                for sub in subs:
                    if sub['vk_type'] == 'g': groups += f"{sub['vk_id']},"
                    else: users += f"{sub['vk_id']},"
                        
                r_groups = vkapi.groups.getById(group_ids=groups, v='5.130')
                r_users = vkapi.users.get(user_ids=users, fields='screen_name', v='5.130')

                for wall in r_groups:
                    name = f"{wall['name']}"
                    type = 'Group'

                    table.add_row([name, wall['screen_name'], type, wall['id']])
                    embed.add_field(
                        name = name,
                        value = f"Short address: `{wall['screen_name']}`\nType: `{type}`\nID: `{wall['id']}`",
                        inline = True
                    )

                for wall in r_users:
                    name = f"{wall['first_name']} {wall['last_name']}"
                    type = 'User'

                    table.add_row([name, wall['screen_name'], type, wall['id']])
                    embed.add_field(
                        name = name,
                        value = f"Short address: `{wall['screen_name']}`\nType: `{type}`\nID: `{wall['id']}`",
                        inline = True
                    )

                await ctx.send(f"**Wall subscriptions for **{channel.mention}** channel:**\n```{table.draw()}```", embed=embed)
            else: raise noSubs

@information.error
async def susbcriptions_information_error(ctx, error):
    error_embed = None
    dm = False

    if isinstance(error, commands.BotMissingPermissions):
        if 'Send Messages' in str(error):
            dm = True
            error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')
            await ctx.message.author.send(embed=error_embed)
        else:
            error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')

    elif isinstance(error, commands.MissingPermissions):
        error_embed = set_error_embed(f'You are missing permission(s).\n\n> {error}')

    elif isinstance(error, commands.ChannelNotFound) or isinstance(error, commands.BadArgument):
        error_embed = set_error_embed(f'Channel is not found.\n\n> Please, pass in `[Channel Mention]` as **Channel Mention** from current server.')
        add_command_and_example(ctx, error_embed, f'`subscriptions information [Channel Mention]`', f'.s i {ctx.message.channel.mention}')

    elif isinstance(error, commands.CommandInvokeError):
        error = error.original
        if isinstance(error, NotAuthenticated):
            error_embed = set_error_embed(f'You aren\'t authenticated.\n\n> Run `sub` command to link your VK profile.')

        elif isinstance(error, noSubs):
            error_embed = set_error_embed(f'No subscriptions for this channel.')

        elif isinstance(error, channelNotSpecifiedError):
            error_embed = set_error_embed(f'`[Channel Mention]` is not specified.\n\n> Please, specify `[Channel Mention]` as **Channel Mention**.')
            add_command_and_example(ctx, error_embed, f'`subscriptions information [Channel Mention]`', f'.s i {ctx.message.channel.mention}')
        
        else:
            print(str(error), str(error.original))
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    else:
        print(error)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    if error_embed != None and dm == False:
        await ctx.send(embed=error_embed)

@subscriptions.command(aliases=['d','del'])
@bot_has_permissions(manage_webhooks=True, add_reactions=True, manage_messages=True, read_message_history=True, send_messages=True)
@has_permissions(manage_webhooks=True)
async def delete(ctx, vk_id: str=None, webhook_channel: discord.TextChannel=None):
    if webhook_channel == None: webhook_channel = ctx.channel
    ctx.webhook_channel = webhook_channel
    if webhook_channel == None: raise channelNotSpecifiedError
    elif vk_id == None: raise vkIdNotSpecifiedError
    else:
        with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT token FROM server WHERE id = %s", (ctx.guild.id,))
                token = cur.fetchone()['token']
        dbcon.close

        if token == None: raise NotAuthenticated
        else: 
            vkapi = authenticate(token)

            try: groupi = vkapi.groups.getById(group_id=vk_id, fields="status,description,members_count", v='5.130')
            except Exception as error:
                if isinstance(error, exceptions.VkAPIError) and '100' in str(error):
                    groupi = [{'deactivated': True}]
            try: useri = vkapi.users.get(user_ids=vk_id, fields='photo_max,status,screen_name,followers_count,counters', v='5.130')
            except Exception as error:
                if isinstance(error, exceptions.VkAPIError) and '113' in str(error):
                    useri = [{'deactivated': True}]
            
            if not 'deactivated' in groupi[0] and not 'deactivated' in useri[0]:
                with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
                    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        cur.execute(f"SELECT vk_id, vk_type FROM subscription WHERE channel_id = {webhook_channel.id} AND (vk_id = {groupi[0]['id']} OR vk_id = {useri[0]['id']})")
                        subs = cur.fetchall()
                dbcon.close

                if len(subs) == 2:
                    group_embed = group_compile_embed(groupi[0])
                    user_embed = user_compile_embed(useri[0])

                    messages = []
                    messages.append(await ctx.send(embed=group_embed))
                    messages.append(await ctx.send('React with ⬆️ for **group** wall\nReact with ❌ for cancel\nReact with ⬇️ for **user** wall'))
                    messages.append(await ctx.send(embed=user_embed))

                    for emoji in ['⬆️', '❌', '⬇️']:
                        await messages[1].add_reaction(emoji)
                    
                    try:
                        r, u = await client.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message == messages[1] and r.emoji in ['⬆️', '❌', '⬇️'], timeout=120.0)
                    except asyncio.TimeoutError:
                        await ctx.channel.delete_messages(messages)
                        messages = []
                        await ctx.send('❌ Cancelled (timeout)')
                    else:
                        await ctx.channel.delete_messages(messages)
                        messages = []

                        if r.emoji == '⬆️':
                            await setup(ctx, 'del', messages, webhook_channel, 'g', groupi[0], group_embed)

                        elif r.emoji == '⬇️':
                            await setup(ctx, 'del', messages, webhook_channel, 'u', useri[0], user_embed)

                        else:
                            await ctx.send('❌ Cancelled')
                
                elif len(subs) == 1:
                    if subs[0]['vk_type'] == 'g':
                        group_embed = group_compile_embed(groupi[0])

                        messages = []

                        await setup(ctx, 'del', messages, webhook_channel, 'g', groupi[0], group_embed)
                    elif subs[0]['vk_type'] == 'u': 
                        user_embed = user_compile_embed(useri[0])

                        messages = []

                        await setup(ctx, 'del', messages, webhook_channel, 'u', useri[0], user_embed)

                else: raise notSub

            elif not 'deactivated' in groupi[0]:
                with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
                    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        cur.execute(f"SELECT vk_id, vk_type FROM subscription WHERE channel_id = {webhook_channel.id} AND vk_id = {groupi[0]['id']}")
                        subs = cur.fetchall()
                dbcon.close

                if len(subs) == 1:
                    group_embed = group_compile_embed(groupi[0])

                    messages = []

                    await setup(ctx, 'del', messages, webhook_channel, 'g', groupi[0], group_embed)

                else: raise notSub

            elif not 'deactivated' in useri[0]:
                with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
                    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        cur.execute(f"SELECT vk_id, vk_type FROM subscription WHERE channel_id = {webhook_channel.id} AND vk_id = {useri[0]['id']}")
                        subs = cur.fetchall()
                dbcon.close

                if len(subs) == 1:
                    user_embed = user_compile_embed(useri[0])

                    messages = []

                    await setup(ctx, 'del', messages, webhook_channel, 'u', useri[0], user_embed)

                else: raise notSub

            else: raise vkWallBlockedError

@delete.error
async def subscriptions_delete_error(ctx, error):
    error_embed = None
    dm = False

    if isinstance(error, commands.BotMissingPermissions):
        if 'Send Messages' in str(error):
            dm = True
            error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')
            await ctx.message.author.send(embed=error_embed)
        else:
            error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')

    elif isinstance(error, commands.MissingPermissions):
        error_embed = set_error_embed(f'You are missing permission(s).\n\n> {error}')

    elif isinstance(error, commands.ChannelNotFound):
        error_embed = set_error_embed(f'Channel is not found.\n\n> Please, pass in `[Channel Mention]` as **Channel Mention** from current server.')
        add_command_and_example(ctx, error_embed, f'`subscriptions delete [Channel Mention] [VK Wall]`', f'.s d {ctx.message.channel.mention} 1')

    elif isinstance(error, commands.BadArgument):
        error_embed = set_error_embed(f'One or more arguments are invalid.\n\n> Please, pass in `[Channel Mention]` as **Channel Mention** and `[VK Wall]` as **String**.')
        add_command_and_example(ctx, error_embed, f'`subscriptions delete [Channel Mention] [VK Wall]`', f'.s d {ctx.message.channel.mention} 1')

    elif isinstance(error, commands.CommandInvokeError):
        error = error.original

        if isinstance(error, NotAuthenticated):
            error_embed = set_error_embed(f'You aren\'t authenticated.\n\n> Run `sub` command to link your VK profile.')

        elif isinstance(error, channelNotSpecifiedError):
            error_embed = set_error_embed(f'`[Channel Mention]` is not specified.\n\n> Please, specify `[Channel Mention]` as **Channel Mention**.')
            add_command_and_example(ctx, error_embed, f'`subscriptions delete [Channel Mention] [VK Wall]`', f'.s d {ctx.message.channel.mention} 1')

        elif isinstance(error, vkIdNotSpecifiedError):
            error_embed = set_error_embed(f'`[VK Wall]` is not specified.\n\n> Please, specify `[VK Wall]` as **String**.')
            add_command_and_example(ctx, error_embed, f'`subscriptions delete [Channel Mention] [VK Wall]`', f'.s d {ctx.message.channel.mention} 1')

        elif isinstance(error, vkWallBlockedError):
            error_embed = set_error_embed(f'`[VK Wall]` is invalid.\n\n> Wall **{ctx.args[1]}** may be blocked, deactivated, deleted or it may not exist.')

        elif isinstance(error, notSub):
            error_embed = set_error_embed(f'{ctx.webhook_channel.mention} isn\'t subscribed to wall **{ctx.args[1]}**.')

        else: 
            print(error)
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    else: 
        print(error)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    if error_embed != None and dm == False:
        await ctx.send(embed=error_embed)

@tasks.loop(seconds=60)
async def repost(channel, ctx):
    post = vkapi.wall.get(owner_id=-(settings['wallId']), extended=False, count=1, v='5.130')
    dbcon = psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword'])

    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(f"SELECT last_post_id FROM data WHERE server_id = {ctx.guild.id};")
        last_post = cur.fetchone()['value']
    
    if post['items'][0]['is_pinned'] == 1:
        post = vkapi.wall.get(owner_id=-(settings['wallId']), extended=False, count=2, v='5.130')
        post_count = 1
    else: post_count = 0

    if last_post != post['items'][post_count]['id']:
        items = post['items'][post_count]
        group = post['groups'][0]
        from_id = -(items['from_id'])
        post_id = items['id']

        #Запись
        post_url = f'https://vk.com/wall-{from_id}_{post_id}'
        post_text = items['text']
        post_date = items['date']

        #Автор
        author_name = group['name']
        author_url = f'https://vk.com/public{from_id}'
        author_photo = group['photo_200']

        #ВК
        vk_group = vkapi.groups.getById(group_id=22822305, v='5.130')
        vk_name = vk_group[0]['name']
        vk_photo = vk_group[0]['photo_200']

        #Изображение
        is_there_a_photo = False
        if 'attachments' in items:                              #Если есть вложения
            for attachment in items['attachments']:             #Для каждого вложения
                if 'photo' in attachment:                       #Если вложение является изображением
                    is_there_a_photo = True                     #Вложения имеют изображение
                    hw = 0                                      #Размер изображения
                    image_url = ''                              #И так понятно
                    for size in attachment['photo']['sizes']:   #Для каждого размера изображения 
                        if size['width']*size['height'] > hw:   #Если размер изображения больше предыдущего
                            hw = size['width']*size['height']   #Присвоить размер текущему размеру
                            image_url = size['url']             #Присвоить ссылку на текущее изображение
                    break
        
        embed = discord.Embed(
            title = title,
            url = post_url,
            description = post_text,
            timestamp = datetime.fromtimestamp(post_date),
            colour = color
        )
        embed.set_author(
            name = author_name,
            url = author_url,
            icon_url = author_photo
        )
        embed.set_footer(
            text = vk_name,
            icon_url = vk_photo
        )
        
        if is_there_a_photo:
            embed.set_image(url = image_url)
        
        if 'copy_history' in items:
            copy = items['copy_history'][0]
            rfrom_id = -(copy['from_id'])
            rpost_id = copy['id']
            # rpost = vkapi.groups.getById(group_id=rfrom_id, v='5.130')

            rpost_url = f'https://vk.com/wall-{rfrom_id}_{rpost_id}'
            rpost_text = copy['text']
            # rpost_date = copy['date']
        
            # rauthor_name = rpost[0]['name']
            # rauthor_photo = rpost[0]['photo_200']
            # rauthor_url = f'https://vk.com/public{rfrom_id}'

            embed.add_field(
                name = '↪️ Репост',
                value = f'[**Открыть запись**]({rpost_url})\n>>> {rpost_text}'
            )

        await channel.send(embed=embed)

        with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(f"UPDATE data SET last_post_id = {post_id} WHERE server_id = {ctx.guild.id};")
        dbcon.commit()
        dbcon.close()
        
        print(f'Post {post_url} reposted!')
    else:
        dbcon.commit() 
        dbcon.close()

client.run(settings['discordToken'])