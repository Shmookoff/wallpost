import discord
from discord.ext import commands
from discord_slash import cog_ext
from discord_slash.utils.manage_commands import create_option, create_choice

import os

from rsc.functions import chn_service_or_owner


class Cogs(commands.Cog):
    def __init__(self, client):
        self.client = client

    guild_ids = [817700627605749781]
    choices = [create_choice(
                    value='subs',
                    name='Subsciptions Command'
                ),
                create_choice(
                    value='cogs',
                    name='Cogs Command'
                ),
                create_choice(
                    value='help',
                    name='Help Command'
                ),
                create_choice(
                    value='executor',
                    name='Code Executor'
                ),
                create_choice(
                    value='handler',
                    name='Exception Handler'
                )]

    @cog_ext.cog_subcommand(base='cogs',
                            name='list',
                            description='List loaded cogs',
                            guild_ids=guild_ids,
                            )
    async def _list(self, ctx):
        cogs = self.client.extensions
        msg = '__Loaded cogs:__\n'
        n = 0
        for cog in cogs:
            n += 1
            msg += f'**{n}.** `{cogs[cog]}`\n'
        if n == 0:
            msg += '`None`'
        await ctx.send(msg)

    @cog_ext.cog_subcommand(base='cogs',
                            name='load',
                            description='Load all cogs or a specific one',
                            guild_ids=guild_ids,
                            options=[create_option(
                                name='cog',
                                description='Cog to load',
                                option_type=3,
                                required=False,
                                choices=choices
                            )])
    async def load(self, ctx, cog=None):
        if cog == None: 
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
            await ctx.send(msg)
        else:
            try: self.client.load_extension(f'app.cogs.{cog}')
            except commands.ExtensionNotFound:
                msg = f'❌ `{cog}` not found!'
            except commands.ExtensionAlreadyLoaded:
                msg = f'❌ `{cog}` is already loaded!'
            else: msg = f'✅ `{cog}` loaded!'
            await ctx.send(msg)

    @cog_ext.cog_subcommand(base='cogs',
                            name='reload',
                            description='Reload all cogs or a specific one',
                            guild_ids=guild_ids,
                            options=[create_option(
                                name='cog',
                                description='Cog to reload',
                                option_type=3,
                                required=False,
                                choices=choices
                            )])
    async def reload(self, ctx, cog=None):
        if cog == None: 
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

    @cog_ext.cog_subcommand(base='cogs',
                            name='unload',
                            description='Unload all cogs or a specific one',
                            guild_ids=guild_ids,
                            options=[create_option(
                                name='cog',
                                description='Cog to unload',
                                option_type=3,
                                required=False,
                                choices=choices
                            )])
    async def unload(self, ctx, cog=None):
        if cog == None: 
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


name = 'Cogs'

def setup(client):
    print(f'Load COG {name}')
    cog = Cogs(client)
    client.add_cog(cog)

def teardown(client):
    print(f'Unload COG {name}')
    client.remove_cog(name)