import discord
from discord.ext import commands

import os

from rsc.functions import chn_service_or_owner


class Cogs(commands.Cog):
    def __init__(self, client):
        self.client = client
        

    @commands.group(invoke_without_command=True, aliases=['c'])
    @chn_service_or_owner()
    async def cogs(self, ctx):
        cogs = self.client.extensions
        msg = '__Loaded cogs:__\n'
        n = 0
        for cog in cogs:
            n += 1
            msg += f'**{n}.** `{cogs[cog]}`\n'
        if n == 0:
            msg += '`None`'
        await ctx.send(msg)

    @cogs.command(aliases=['l'])
    @chn_service_or_owner()
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

    @cogs.command(aliases=['r'])
    @chn_service_or_owner()
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

    @cogs.command(aliases=['u'])
    @chn_service_or_owner()
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