import discord
from discord.ext import commands, tasks, ipc
from discord_slash import SlashCommand

import aiopg
from psycopg2.extras import DictCursor
import aiohttp

import os
import traceback
import sys
from io import StringIO

from rsc.config import sets
from rsc.classes import Server


class WallPost(commands.Bot):
    __name__ = 'WallPost'

    def __init__(self, *args, **kwargs):
        print(f"Start INIT {self.__name__}", end='\n\n')

        super().__init__(*args, **kwargs)

        self.ipc = ipc.Server(self, secret_key = sets['ipcSecretKey'])
        self.remove_command('help')

    async def on_ready(self):
        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("SELECT id FROM server")
                guilds_in_db = await cur.fetchall()
            guilds_connected = self.guilds
            
            guilds_connected_array = []
            guilds_in_db_array = []

            for guild in guilds_in_db:
                guilds_in_db_array.append(guild['id'])
            for guild in guilds_connected:
                guilds_connected_array.append(guild.id)

            _check = False
            for guild in guilds_connected_array:
                if not guild in guilds_in_db_array:
                    async with conn.cursor(cursor_factory=DictCursor) as cur:
                        await cur.execute("INSERT INTO server (id) VALUES(%s)", (guild,))
                    print(f'Register SERVER {guild} in DB')
                    if _check is False: _check = True
            for guild in guilds_in_db_array:
                if not guild in guilds_connected_array:
                    async with conn.cursor(cursor_factory=DictCursor) as cur:
                        await cur.execute("DELETE FROM server WHERE id = %s", (guild,))
                    print(f'Delete SERVER {guild} from DB')
                    if _check is False: _check = True
        if _check:
            print()

        self.log_chn = client.get_channel(sets["logChnId"])
        self.slash = SlashCommand(self, sync_commands=True, sync_on_cog_reload=True)

        try: self.load_extension('app.cogs.handler')
        except commands.ExtensionAlreadyLoaded:
            self.reload_extension('app.cogs.handler')
        for filename in os.listdir('app/cogs'):
            if filename.endswith('.py') and filename != 'handler.py':
                try: self.load_extension(f'app.cogs.{filename[:-3]}')
                except commands.ExtensionAlreadyLoaded:
                    self.reload_extension(f'app.cogs.{filename[:-3]}')
        print()

        print(f'/CMNDS: {list(self.slash.commands.keys())}', end='\n\n')

        print(f'Done INIT {self.__name__}', end='\n\n')

    async def on_ipc_ready(self):
        print("IPC is ready!", end='\n\n')

    async def on_guild_join(self, guild):
        await Server.add((guild.id))

    async def on_guild_remove(self, guild):
        await Server.find_by_args(guild.id).delete()

    async def on_error(self, event, *args, **kwargs):
        await self.error_handler('general', event=event)

    async def error_handler(self, raised, **kwargs):
        if raised == 'general':
            tb = traceback.format_exc()
            msg = f'Ignoring exception in `{kwargs["event"]}`:'
            print_msg = f'Ignoring exception in {kwargs["event"]}:'
        else:
            tb = "".join(traceback.format_exception(type(kwargs["exc"]), kwargs["exc"], kwargs["exc"].__traceback__))
            if raised in ['slash_command', 'command']:
                if raised == 'slash_command':
                    cmnd_name = f'/{kwargs["ctx"].name}{" "+kwargs["ctx"].subcommand_name if kwargs["ctx"].subcommand_name is not None else ""}'
                elif raised == 'command':
                    cmnd_name = f'.{kwargs["ctx"].command}'
                msg = f'Ignoring exception in **COMMAND** `{cmnd_name}`:\nParams: `{kwargs["ctx"].kwargs}`'
                print_msg = f'Ignoring exception in COMMAND {cmnd_name}:\nParams: {kwargs["ctx"].kwargs}'
            elif raised == 'endpoint':
                msg = f'Ignoring exception in `{kwargs["endpoint"]}` **IPC ENDPOINT**:'
                print_msg = f'Ignoring exception in {kwargs["endpoint"]} IPC ENDPOINT:'
        print(f'{print_msg}\n{tb}')
        try:
            if len(f'{msg}\n```py\n{tb}\n```') <= 2000:
                await self.log_chn.send(f'{msg}\n```py\n{tb}\n```')
            else:
                await self.log_chn.send(msg, file=discord.File(StringIO(tb), filename='traceback.python'))
        except Exception as exc:
            print(f'An exception has occured while handilng {raised} error:\n{traceback.format_exc()}', end='\n\n')

    @tasks.loop(minutes=15)
    async def ping_server(self):
        async with aiohttp.ClientSession() as session:
            try: session.get(sets['url'])
            except Exception: pass


if __name__ == '__main__':
    intents = discord.Intents.default()
    intents.members = True
    client = WallPost(command_prefix='.', intents=intents, activity=discord.Activity(name='/subs add', type=0))
    client.ipc.start()
    client.run(sets["dcToken"])