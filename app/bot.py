import discord
from discord.ext import commands, tasks, ipc
from discord_slash import SlashCommand

import aiopg
import aiohttp
import aiovk
from psycopg2.extras import DictCursor
from aiovk.pools import AsyncVkExecuteRequestPool

import os
import traceback
import logging

from rsc.config import sets, vk_sets
from rsc.classes import WPLoggerAdapter, WPLogger, SafeDict


class WallPost(commands.Bot):
    __name__ = 'WallPost'

    def __init__(self, *args, **kwargs):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(*args, intents=intents, command_prefix='.', activity=discord.Activity(name='/subs add', type=0), **kwargs)

        self.loop.create_task(self.ainit())
        self.logger = WPLoggerAdapter(WPLogger(self.loop), {'tb': ''})
        self.ipc = ipc.Server(self, secret_key=sets['ipcSecretKey'])
        self.slash = SlashCommand(self, sync_commands=True, sync_on_cog_reload=True)

        self.ipc.start()
        self.remove_command('help')

    async def ainit(self):
        async with aiovk.TokenSession(vk_sets["serviceKey"]) as ses:
            vkapi = aiovk.API(ses)
            vk_info = await vkapi.groups.getById(group_id=22822305, v='5.84')
        self.vk_info = {'name': vk_info[0]['name'], 'photo': vk_info[0]['photo_200']}
        
        self.cogs_msg = '\nLoad COGs'
        try: self.load_extension('app.cogs.handler')
        except commands.ExtensionAlreadyLoaded:
            self.reload_extension('app.cogs.handler')
        try: self.load_extension('app.cogs.repost')
        except commands.ExtensionAlreadyLoaded:
            self.reload_extension('app.cogs.repost')
        for filename in os.listdir('app/cogs'):
            if filename.endswith('.py') and filename not in ['handler.py', 'repost.py']:
                try: self.load_extension(f'app.cogs.{filename[:-3]}')
                except commands.ExtensionAlreadyLoaded:
                    self.reload_extension(f'app.cogs.{filename[:-3]}')

    async def on_ready(self):
        self.logger.logger.add_discord_handler(logging.INFO, self.get_channel(sets['logChnId']))
        self.logger.logger.add_discord_handler(logging.ERROR, self.get_channel(sets['errorChnId']))
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
        repost_cog = self.get_cog('Repost')
        srv, logmsg = await repost_cog.Server_add((guild.id))
        self.logger.info('Add {aa}SRV{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=logmsg)))

    async def on_guild_remove(self, guild):
        repost_cog = self.get_cog('Repost')
        srv, _ = repost_cog.Server.find_by_args(guild.id)
        logmsg = await srv.delete()
        self.logger.info('Del {aa}SRV{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=logmsg)))

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
                msg = 'Ignoring exception in {t}{cmnd_name}{t} {aa}COMMAND{aa}:\nParams: {t}{kwargs}{t}'.format_map(SafeDict(cmnd_name=cmnd_name, kwargs=str(kwargs["ctx"].kwargs).replace('{', '(').replace('}', ')')))
            elif raised == 'endpoint':
                msg = 'Ignoring exception in {t}{endpoint}{t} {aa}IPC ENDPOINT{aa}:'.format_map(SafeDict(endpoint=kwargs["endpoint"]))
            elif raised == 'repost_task':
                msg = 'Ignoring exception in {aa}USER{aa} {t}"repost_task"{t}:\n{t}{usr}{t}'.format_map(SafeDict(usr=kwargs["usr"]))
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