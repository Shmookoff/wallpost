import discord
from discord.ext import commands, ipc

import psycopg2
import psycopg2.extras
import os
from cryptography.fernet import Fernet
import asyncio

import traceback
import sys

from colorama import Fore, Style

from rsc.config import dc_sets, psql_sets
from rsc.functions import get_prefix, Server


class WallPost(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.ipc = ipc.Server(self, secret_key = dc_sets['ipcSecretKey'], host='0.0.0.0')

        self.remove_command('help')

    async def on_ready(self):
        with psycopg2.connect(psql_sets["uri"]) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT id FROM server")
                guilds_in_db = cur.fetchall()
            guilds_connected = self.guilds
            
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
                    print(f'Registered {Fore.GREEN}SERVER {Fore.BLUE}{guild} {Style.RESET_ALL}in DB')
            for guild in guilds_in_db_array:
                if not guild in guilds_connected_array:
                    with dbcon.cursor() as cur:
                        cur.execute("DELETE FROM server WHERE id = %s", (guild,))
                    print(f'Deleted {Fore.GREEN}SERVER {Fore.BLUE}{guild} {Style.RESET_ALL}from DB')
        dbcon.close()


        msg, n = '✅ Successfully loaded cogs:\n', 0
        for filename in os.listdir('app/cogs'):
            if filename.endswith('.py'):
                client.load_extension(f'app.cogs.{filename[:-3]}')
                n += 1
                msg += f'{n}. {filename[:-3]}\n'
        if n == 0:
            msg += '`None`' 
        print(msg)


        self.log_chn = self.get_channel(836705410630287451)


        print('WallPost bot is ready!\n')

    async def on_ipc_ready(self):
        print("IPC is ready!")

    async def on_guild_join(self, guild):
        Server.add((guild.id))

    async def on_guild_remove(self, guild):
        Server.find_by_args(guild.id).delete()

    async def on_command_error(self, ctx, exc, force=False):
        if (ctx.command.has_error_handler() and force) or ctx.command.has_error_handler() is False:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            print(f'Ignoring exception in command {ctx.command}:\n{tb}', file=sys.stderr)
            await self.log_chn.send(f'Ignoring exception in command `{ctx.command}`:\n```py\n{tb}\n```')

    async def on_ipc_error(self, endpoint, exc):
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        print(f'Ignoring exception in {endpoint} endpoint:\n{tb}', file=sys.stderr)
        await self.log_chn.send(f'Ignoring exception in `{endpoint}` endpoint:\n```py\n{tb}\n```')

client = WallPost(command_prefix=get_prefix, activity=discord.Activity(name='.help', type=0))


@client.group(invoke_without_command=True, aliases=['c'])
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

@cogs.command(aliases=['l'])
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

@cogs.command(aliases=['r'])
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

@cogs.command(aliases=['u'])
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


client.ipc.start()
client.run(dc_sets["token"])