import discord
from discord.ext import commands

from rsc.config import sets
from rsc.functions import set_error_embed, add_command_and_example
from rsc.classes import Server
from rsc.exceptions import PrefixGreaterThan3


class Prefix(commands.Cog):
    def __init__(self, client):
        self.client = client


    @commands.group(aliases=['p'], invoke_without_command=True)
    @commands.bot_has_permissions(send_messages=True)
    async def prefix(self, ctx, prefix: str = None):
        if prefix is None:
            server = Server.find_by_args(ctx.guild.id)
            prefix = server.prefix if server.prefix is not None else '.'
            await ctx.send(f'Prefix is `{prefix}`')
        else:
            if len(prefix) <= 3:
                server = Server.find_by_args(ctx.guild.id)
                await ctx.send(f'Prefix is set to `{await server.set_prefix(prefix)}`')
            else: raise PrefixGreaterThan3

    @prefix.error
    async def prefix_error(self, ctx, exc):
        if isinstance(exc, commands.CommandInvokeError):
            _exc = exc.original

            if isinstance(_exc, PrefixGreaterThan3):
                exc.embed = set_error_embed('The length of prefix must be `<` or `=` `3`')
                exc.command_and_example = True


name = 'Prefix'

def setup(client):
    print(f'Load COG {name}')
    cog = Prefix(client)
    client.add_cog(cog)

def teardown(client):
    print(f'Unload COG {name}')
    client.remove_cog(name)