import discord
from discord.ext import commands, ipc

import aiopg
from psycopg2.extras import DictCursor

import os
from cryptography.fernet import Fernet

from rsc.config import sets
from rsc.classes import Server


class WallPost(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__name__ = 'WallPost'
        print(f"Start INIT {self.__name__}\n")

        self.ipc = ipc.Server(self, secret_key = sets['ipcSecretKey'])

        self.remove_command('help')

    async def on_ready(self):
        try: client.load_extension('app.cogs.handler')
        except commands.ExtensionAlreadyLoaded:
            client.reload_extension('app.cogs.handler')

        print('Check SERVERs')
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

            for guild in guilds_connected_array:
                if not guild in guilds_in_db_array:
                    async with conn.cursor(cursor_factory=DictCursor) as cur:
                        await cur.execute("INSERT INTO server (id, key, key_uuid) VALUES(%s, %s, uuid_generate_v4())", (guild, Fernet.generate_key()))
                    print(f'Register SERVER {guild} in DB')
            for guild in guilds_in_db_array:
                if not guild in guilds_connected_array:
                    async with conn.cursor(cursor_factory=DictCursor) as cur:
                        await cur.execute("DELETE FROM server WHERE id = %s", (guild,))
                    print(f'Delete SERVER {guild} from DB')
        print('—')

        print('Load COGs')
        for filename in os.listdir('app/cogs'):
            if filename.endswith('.py') and filename != 'handler.py':
                try: client.load_extension(f'app.cogs.{filename[:-3]}')
                except commands.ExtensionAlreadyLoaded:
                    client.reload_extension(f'app.cogs.{filename[:-3]}')
        print('—')

        print(f'Done INIT {self.__name__}\n')

    async def on_ipc_ready(self):
        print("IPC is ready!\n")

    async def on_guild_join(self, guild):
        await Server.add((guild.id))

    async def on_guild_remove(self, guild):
        await Server.find_by_args(guild.id).delete()

if __name__ == '__main__':
    client = WallPost(command_prefix=lambda _, msg: Server.find_by_args(msg.guild.id).prefix, activity=discord.Activity(name='.help', type=0))
    client.ipc.start()
    client.run(sets["dcToken"])