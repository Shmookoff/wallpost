import discord

import psycopg2
import psycopg2.extras
import os
from cryptography.fernet import Fernet
from discord.ext import commands

import traceback
import sys

from rsc.config import dc_sets, psql_sets
from rsc.functions import get_prefix


client = commands.Bot(command_prefix=get_prefix, activity=discord.Activity(name='.help', type='1'))

client.remove_command('help')


@client.event
async def on_ready():
    with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
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
                    cur.execute("DELETE FROM server WHERE id = %s", (guild,))
    dbcon.close()

    print('Ready!')

@client.event
async def on_guild_join(guild):
    with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
        with dbcon.cursor() as cur:
            cur.execute("INSERT INTO server (id, key, key_uuid) VALUES(%s, %s, uuid_generate_v4())", (guild.id, Fernet.generate_key()))
    dbcon.close()

@client.event
async def on_guild_remove(guild):
    with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
        with dbcon.cursor() as cur:
            cur.execute(f"DELETE FROM server WHERE id = {guild.id}")
    dbcon.close()


@client.group(invoke_without_command=True)
async def cogs(ctx):
    if ctx.channel.id == 823545137082531861:
        cogs = client.extensions
        msg = '__Loaded cogs:__\n'
        n = 0
        for cog in cogs:
            n += 1
            msg += f'**{n}.** `{cogs[cog]}`\n'
        if n == 0:
            msg += '`None`'
        await ctx.send(msg)

@cogs.error
async def load_error(ctx, error):
    await ctx.send(f'❌ **ERROR:**\n```py\n{str(error)}\n\n{traceback.format_exc()}\n```')

@cogs.command()
async def load(ctx, cog=None):
    if ctx.channel.id == 823545137082531861:
        if cog == None: 
            msg, n = '✅ __Successfully loaded cogs:__\n', 0
            for filename in os.listdir('app/cogs'):
                if filename.endswith('.py'):
                    try: client.load_extension(f'app.cogs.{filename[:-3]}')
                    except Exception as error: 
                        if isinstance(error, commands.ExtensionAlreadyLoaded): pass
                    else:
                        n += 1
                        msg += f'**{n}.** `{filename[:-3]}`\n'
            if n == 0:
                msg += '`None`'
            await ctx.send(msg)
        else:
            try: client.load_extension(f'app.cogs.{cog}')
            except Exception as error:
                if isinstance(error, commands.ExtensionNotFound):
                    msg = f'❌ `{cog}` not found!'
                elif isinstance(error, commands.ExtensionAlreadyLoaded):
                    msg = f'❌ `{cog}` is already loaded!'
            else: msg = f'✅ `{cog}` loaded!'
            await ctx.send(msg)
                
@load.error
async def load_error(ctx, error):
    await ctx.send(f'❌ **ERROR:**\n```py\n{str(error)}\n\n{traceback.format_exc()}\n```')

@cogs.command()
async def reload(ctx, cog=None):
    if ctx.channel.id == 823545137082531861:
        if cog == None: 
            msg, n = '✅ __Successfully reloaded cogs:__\n', 0
            for filename in os.listdir('app/cogs'):
                if filename.endswith('.py'):
                    try: client.reload_extension(f'app.cogs.{filename[:-3]}')
                    except Exception as error:
                        if isinstance(error, commands.ExtensionNotLoaded): pass
                    else:
                        n += 1
                        msg += f'**{n}.** `{filename[:-3]}`\n'
            if n == 0:
                msg += '`None`'
            await ctx.send(msg)
        else: 
            try: client.reload_extension(f'app.cogs.{cog}')
            except Exception as error:
                if isinstance(error, commands.ExtensionNotFound):
                    msg = f'❌ `{cog}` not found!'
                elif isinstance(error, commands.ExtensionNotLoaded):
                    msg = f'❌ `{cog}` hasn\'t been loaded for it to reload!'
            else: msg = f'✅ `{cog}` reloaded!'
            await ctx.send(msg)

@reload.error
async def load_error(ctx, error):
    await ctx.send(f'❌ **ERROR:\n```py\n{str(error)}\n\n{traceback.format_exc()}\n```')

@cogs.command()
async def unload(ctx, cog=None):
    if ctx.channel.id == 823545137082531861:
        if cog == None: 
            msg, n = '✅ __Successfully unloaded cogs:__\n', 0
            for filename in os.listdir('app/cogs'):
                if filename.endswith('.py'):
                    try: client.unload_extension(f'app.cogs.{filename[:-3]}')
                    except Exception as error:
                        if isinstance(error, commands.ExtensionNotLoaded): pass
                    else:
                        n += 1
                        msg += f'**{n}.** `{filename[:-3]}`\n'
            if n == 0:
                msg += '`None`'
            await ctx.send(msg)
        else:
            try: client.unload_extension(f'app.cogs.{cog}')
            except Exception as error:
                if isinstance(error, commands.ExtensionNotFound):
                    msg = f'❌ `{cog}` not found!'
                if isinstance(error, commands.ExtensionNotLoaded):
                    msg = f'❌ `{cog}` hasn\'t been loaded for it to unload!'
            else: msg = f'✅ `{cog}` unloaded!'
            await ctx.send(msg)

@unload.error
async def load_error(ctx, error):
    await ctx.send(f'❌ **ERROR:**\n```py\n{str(error)}\n\n{traceback.format_exc()}\n```')

for filename in os.listdir('app/cogs'):
    if filename.endswith('.py'):
        client.load_extension(f'app.cogs.{filename[:-3]}')


client.run(dc_sets["token"])