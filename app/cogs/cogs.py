import discord
from discord.ext import commands
from discord_slash import cog_ext
from discord_slash.utils.manage_commands import create_option, create_choice

import os

from rsc.config import sets
from rsc.functions import check_service_chn


class Cogs(commands.Cog):
    __name__ = 'Cogs Command'
    choices = [create_choice(
                    value='subs',
                    name='Subsciptions Command'
                ), create_choice(
                    value='cogs',
                    name='Cogs Command'
                ), create_choice(
                    value='executor',
                    name='Code Executor'
                ), create_choice(
                    value='handler',
                    name='Exception Handler'
                ), create_choice(
                    value='repost',
                    name='Repost Handler'
                )]

    def __init__(self, client):
        self.client = client

        msg = f'Load COG {self.__name__}'
        if hasattr(self.client, 'cogs_msg'):
            self.client.cogs_msg += f'\n\t{msg}'
        else:
            self.client.logger.info(msg)

    def cog_unload(self):
        msg = f'Unload COG {self.__name__}'
        if hasattr(self.client, 'cogs_msg'):
            self.client.cogs_msg += f'\n\t{msg}'
        else:
            self.client.logger.info(msg)


    @cog_ext.cog_subcommand(name='list',
                            base='cogs',
                            description='List loaded cogs',
                            guild_ids=[sets['srvcSrv']],
                            )
    @check_service_chn()
    async def cogs_list(self, ctx):
        cogs = self.client.extensions
        msg = '__Loaded cogs:__\n'
        n = 0
        for cog in cogs:
            n += 1
            msg += f'**{n}.** `{cogs[cog]}`\n'
        if n == 0:
            msg += '`None`'
        await ctx.send(msg)

    @cog_ext.cog_subcommand(name='load',
                            base='cogs',
                            description='Load all cogs or a specific one',
                            guild_ids=[sets['srvcSrv']],
                            options=[create_option(
                                name='cog',
                                description='Cog to load',
                                option_type=3,
                                required=False,
                                choices=choices
                            )])
    @check_service_chn()
    async def cogs_load(self, ctx, cog=None):
        if cog == None:
            self.client.cogs_msg = 'Load COGs {{tttpy}}'
            msg, n = '✅ __Successfully loaded cogs:__\n', 0
            for filename in os.listdir('app/cogs'):
                if filename.endswith('.py'):
                    try: self.client.load_extension(f'app.cogs.{filename[:-3]}')
                    except commands.ExtensionAlreadyLoaded: 
                        pass
                    else:
                        n += 1
                        msg += f'**{n}.** `{filename[:-3]}`\n'
            if n == 0:
                msg += '`None`'
            else:
                self.client.cogs_msg += ' {{ttt}}'
                self.client.logger.info(self.client.cogs_msg.format())
            del self.client.cogs_msg
            await ctx.send(msg)
        else:
            try: self.client.load_extension(f'app.cogs.{cog}')
            except commands.ExtensionNotFound:
                msg = f'❌ `{cog}` not found!'
            except commands.ExtensionAlreadyLoaded:
                msg = f'❌ `{cog}` is already loaded!'
            else: msg = f'✅ `{cog}` loaded!'
            await ctx.send(msg)

    @cog_ext.cog_subcommand(name='reload',
                            base='cogs',
                            description='Reload all cogs or a specific one',
                            guild_ids=[sets['srvcSrv']],
                            options=[create_option(
                                name='cog',
                                description='Cog to reload',
                                option_type=3,
                                required=False,
                                choices=choices
                            )])
    @check_service_chn()
    async def cogs_reload(self, ctx, cog=None):
        if cog == None:
            self.client.cogs_msg = 'Reload COGs {{tttpy}}'
            msg, n = '✅ __Successfully reloaded cogs:__\n', 0
            for filename in os.listdir('app/cogs'):
                if filename.endswith('.py'):
                    try: self.client.reload_extension(f'app.cogs.{filename[:-3]}')
                    except commands.ExtensionNotLoaded:
                        pass
                    else:
                        n += 1
                        msg += f'**{n}.** `{filename[:-3]}`\n'
            if n == 0:
                msg += '`None`'
            else:
                self.client.cogs_msg += ' {{ttt}}'
                self.client.logger.info(self.client.cogs_msg.format())
            del self.client.cogs_msg
            await ctx.send(msg)
        else: 
            try: self.client.reload_extension(f'app.cogs.{cog}')
            except commands.ExtensionNotFound:
                msg = f'❌ `{cog}` not found!'
            except commands.ExtensionNotLoaded:
                msg = f'❌ `{cog}` hasn\'t been loaded for it to reload!'
            else:
                msg = f'✅ `{cog}` reloaded!'
            await ctx.send(msg)

    @cog_ext.cog_subcommand(name='unload',
                            base='cogs',
                            description='Unload all cogs or a specific one',
                            guild_ids=[sets['srvcSrv']],
                            options=[create_option(
                                name='cog',
                                description='Cog to unload',
                                option_type=3,
                                required=False,
                                choices=choices
                            )])
    @check_service_chn()
    async def cogs_unload(self, ctx, cog=None):
        if cog == None:
            self.client.cogs_msg = 'Unload COGs {{tttpy}}'
            msg, n = '✅ __Successfully unloaded cogs:__\n', 0
            for filename in os.listdir('app/cogs'):
                if filename.endswith('.py'):
                    try: self.client.unload_extension(f'app.cogs.{filename[:-3]}')
                    except commands.ExtensionNotLoaded:
                        pass
                    else:
                        n += 1
                        msg += f'**{n}.** `{filename[:-3]}`\n'
            if n == 0:
                msg += '`None`'
            else:
                self.client.cogs_msg += ' {{ttt}}'
                self.client.logger.info(self.client.cogs_msg.format())
            del self.client.cogs_msg
            await ctx.send(msg)
        else:
            try: self.client.unload_extension(f'app.cogs.{cog}')
            except commands.ExtensionNotFound:
                msg = f'❌ `{cog}` not found!'
            except commands.ExtensionNotLoaded:
                msg = f'❌ `{cog}` hasn\'t been loaded for it to unload!'
            else:
                msg = f'✅ `{cog}` unloaded!'
            await ctx.send(msg)


def setup(client):
    client.add_cog(Cogs(client))