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
from io import StringIO

from rsc.config import sets
from rsc.classes import Server


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

        self.init_msg = "INIT {{aa}}{name}{{aa}} {{tttpy}}\nLogged on as {user}"
        
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
                self.logger.debug(f'{guilds_connected_array} {guilds_in_db_array}')
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

        self.init_msg += '\n/CMNDS: {commands} {{ttt}}'
        self.logger.info(self.init_msg.format(name=self.__name__, user=self.user, commands=list(self.slash.commands.keys())))
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
            msg = 'Ignoring exception in {{t}}{event}{{t}}:'.format(event=kwargs['event'])
        else:
            tb = "".join(traceback.format_exception(type(kwargs["exc"]), kwargs["exc"], kwargs["exc"].__traceback__))
            if raised in ['slash_command', 'command']:
                if raised == 'slash_command':
                    cmnd_name = f'/{kwargs["ctx"].name}{" "+kwargs["ctx"].subcommand_name if kwargs["ctx"].subcommand_name is not None else ""}'
                elif raised == 'command':
                    cmnd_name = f'.{kwargs["ctx"].command}'
                print(kwargs["ctx"].kwargs)
                msg = 'Ignoring exception in {{t}}{cmnd_name}{{t}} {{aa}}COMMAND{{aa}}:\nParams: {{t}}{kwargs}{{t}}'.format(cmnd_name=cmnd_name, kwargs=
                    str(kwargs["ctx"].kwargs).replace('{', '(').replace('}', ')') if kwargs["ctx"].kwargs != {} else 'None')
            elif raised == 'endpoint':
                msg = 'Ignoring exception in {{t}}{endpoint}{{t}} {{aa}}IPC ENDPOINT{{aa}}:'.format(endpoint=kwargs["endpoint"])
        self.logger.error(msg, tb=tb)

    @tasks.loop(minutes=15.0)
    async def ping_server(self):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(sets['url']) as resp:
                    pass
            except:
                pass


class WPLogger(logging.Logger):
    def __init__(self, loop):
        super().__init__('WallPost', logging.DEBUG)
        self.loop = loop
        self.formatter = logging.Formatter('[%(levelname)s]: %(message)s')

        self.add_stream_handler(logging.DEBUG)

    def add_stream_handler(self, level):
        stream_handler = StreamHandler(level)
        stream_handler.setFormatter(self.formatter)
        self.addHandler(stream_handler)

    def add_discord_handler(self, level, channel):
        discord_handler = DiscordHandler(level, self.loop, channel)
        discord_handler.setFormatter(self.formatter)
        self.addHandler(discord_handler)

class WPLoggerAdapter(logging.LoggerAdapter):
    def __init__(self, logger, extra={}):
        super().__init__(logger, extra)

    def process(self, msg, kwargs):
        extra = kwargs.get("extra", {})
        extra.update({"tb": kwargs.pop("tb", '')})
        kwargs["extra"] = extra
        return msg, kwargs

class StreamHandler(logging.StreamHandler):
    def __init__(self, level):
        super().__init__(sys.stdout)
        self.setLevel(level)

    def emit(self, record):
        try:
            msg = self.format(record)
            msg = msg.format(t='', ttt='', tttpy='', aa='')
            if record.tb != '':
                msg = f'{msg}\n{record.tb}'

            self.stream.write(msg + self.terminator)
            self.flush()
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)

class DiscordHandler(logging.StreamHandler):
    def __init__(self, level, loop, channel: discord.TextChannel):
        super().__init__()
        self.loop = loop
        self.channel = channel
        self.setLevel(level)

    def emit(self, record):
        try:
            msg = self.format(record)
            msg = msg.format(t='`', ttt='```', tttpy='```py', aa='**')
            if record.tb != '':
                if len(f'{msg}\n```py\n{record.tb}\n```') <= 2000:
                    task = self.channel.send(f'{msg}\n```py\n{record.tb}\n```')
                else:
                    task = self.channel.send(msg, file=discord.File(StringIO(record.tb), filename='traceback.python'))
            else:
                task = self.channel.send(content=msg)

            self.loop.create_task(task)
            self.flush()
        except Exception as exc:
            self.handleError(record)

if __name__ == '__main__':
    client = WallPost()
    client.run(sets["dcToken"])