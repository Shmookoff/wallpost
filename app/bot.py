import discord
from discord.ext import commands, ipc
from discord_slash import SlashCommand

import aiopg
from psycopg2.extras import DictCursor

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
        tb = traceback.format_exc()
        print(f'Ignoring exception in {event}:\n{tb}', file=sys.stderr)
        try:
            msg = f'Ignoring exception in `{event}`:\n```py\n{tb}\n```'
            if len(msg) <= 2000:
                await self.log_chn.send(msg)
            else:
                await self.log_chn.send(f'Ignoring exception in `{event}`:', file=discord.File(StringIO(tb), filename='traceback.txt'))
        except Exception as e:
            pass


if __name__ == '__main__':
    client = WallPost(command_prefix='.', activity=discord.Activity(name='/subs add', type=0))
    client.ipc.start()
    client.run(sets["dcToken"])