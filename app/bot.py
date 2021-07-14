import discord
from discord.ext import commands, tasks, ipc
from discord_slash import SlashCommand

import aiopg
from psycopg2.extras import DictCursor
import aiohttp

import os
import traceback
import sys
import logging
import re

from rsc.config import sets
from rsc.classes import Server, WPLoggerAdapter, WPLogger, SafeDict


class WallPost(commands.Bot):
    __name__ = 'WallPost'

    def __init__(self, *args, **kwargs):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(*args, intents=intents, command_prefix='.', activity=discord.Activity(name='/subs add', type=0), **kwargs)

        self.logger = WPLoggerAdapter(WPLogger(self.loop), {'tb': ''})
        self.ipc = ipc.Server(self, secret_key=sets['ipcSecretKey'])
        self.slash = SlashCommand(self, sync_commands=True, sync_on_cog_reload=True)
        Server.client = self

        self.cogs_msg = '\nLoad COGs'
        try: self.load_extension('app.cogs.handler')
        except commands.ExtensionAlreadyLoaded:
            self.reload_extension('app.cogs.handler')
        for filename in os.listdir('app/cogs'):
            if filename.endswith('.py') and filename != 'handler.py':
                try: self.load_extension(f'app.cogs.{filename[:-3]}')
                except commands.ExtensionAlreadyLoaded:
                    self.reload_extension(f'app.cogs.{filename[:-3]}')

        self.ipc.start()
        self.remove_command('help')

    async def on_ready(self):
        self.logger.logger.add_discord_handler(logging.INFO, self.get_channel(sets['logChnId']))
        self.ping_server.start()

        self.init_msg = "INIT {aa}{name}{aa} {tttpy}\nLogged on as {user}"
        
        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("SELECT id FROM server")
                guilds_in_db = await cur.fetchall()
            guilds_connected = self.guilds
            
            guilds_connected_array, guilds_in_db_array = set(), set()
            for guild in guilds_in_db:
                guilds_in_db_array.add(guild['id'])
            for guild in guilds_connected:
                guilds_connected_array.add(guild.id)

            if guilds_connected_array != guilds_in_db_array:
                self.init_msg += '\nUpdate DB'
                for guild in guilds_connected_array:
                    if not guild in guilds_in_db_array:
                        async with conn.cursor(cursor_factory=DictCursor) as cur:
                            await cur.execute("INSERT INTO server (id) VALUES(%s)", (guild,))
                        self.init_msg += f'\n\tRegister SERVER {guild} in DB'
                for guild in guilds_in_db_array:
                    if not guild in guilds_connected_array:
                        async with conn.cursor(cursor_factory=DictCursor) as cur:
                            await cur.execute("DELETE FROM server WHERE id = %s", (guild,))
                        self.init_msg += f'\n\tDelete SERVER {guild} from DB'

        self.init_msg += self.cogs_msg
        del self.cogs_msg

        self.init_msg += '\n/CMNDS: {commands} {ttt}'
        self.logger.info(self.init_msg.format_map(SafeDict(name=self.__name__, user=self.user, commands=list(self.slash.commands.keys()))))
        del self.init_msg

    async def on_ipc_ready(self):
        self.logger.info("IPC is ready!")

    async def on_guild_join(self, guild):
        await Server.add((guild.id))

    async def on_guild_remove(self, guild):
        await Server.find_by_args(guild.id).delete()

    async def on_error(self, event, *args, **kwargs):
        await self.error_handler('general', event=event)

    async def error_handler(self, raised, **kwargs):
        if raised == 'general':
            tb = traceback.format_exc()
            msg = 'Ignoring exception in {t}{event}{t}:'.format_map(SafeDict(event=kwargs['event']))
        else:
            tb = "".join(traceback.format_exception(type(kwargs["exc"]), kwargs["exc"], kwargs["exc"].__traceback__))
            if raised in ['slash_command', 'command']:
                if raised == 'slash_command':
                    cmnd_name = f'/{kwargs["ctx"].name}{" "+kwargs["ctx"].subcommand_name if kwargs["ctx"].subcommand_name is not None else ""}'
                elif raised == 'command':
                    cmnd_name = f'.{kwargs["ctx"].command}'
                print(kwargs["ctx"].kwargs)
                msg = 'Ignoring exception in {t}{cmnd_name}{t} {aa}COMMAND{aa}:\nParams: {t}{kwargs}{t}'.format_map(SafeDict(cmnd_name=cmnd_name, kwargs=str(kwargs["ctx"].kwargs).replace('{', '(').replace('}', ')')))
            elif raised == 'endpoint':
                msg = 'Ignoring exception in {t}{endpoint}{t} {aa}IPC ENDPOINT{aa}:'.format_map(SafeDict(endpoint=kwargs["endpoint"]))
        self.logger.error(msg, tb=tb)

    @tasks.loop(minutes=15.0)
    async def ping_server(self):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(sets['url']) as resp:
                    pass
            except:
                pass


if __name__ == '__main__':
    client = WallPost()
    client.run(sets["dcToken"])