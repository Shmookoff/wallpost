import discord
from discord.ext import commands

import psycopg2

import traceback
import sys

from rsc.config import psql_sets
from rsc.functions import set_error_embed, add_command_and_example
from rsc.errors import prefixGreaterThan3

class Prefix(commands.Cog):
    def __init__(self, client):
        self.client = client


    @commands.group(aliases=['p'], invoke_without_command=True)
    @commands.bot_has_permissions(send_messages=True)
    async def prefix(self, ctx):
        with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(f"SELECT prefix FROM server WHERE id = {ctx.guild.id}")
                prefix = cur.fetchone()['prefix']
        dbcon.close
        if prefix == None:
            await ctx.send(f'Prefix is "."')
        else:
            await ctx.send(f'Prefix is "{prefix}"')

    @prefix.error
    async def prefix_error(self, ctx, error):
        error_embed = None
        dm = False

        if isinstance(error, commands.BotMissingPermissions):
            if 'Send Messages' in str(error):
                dm = True
                error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')
                await ctx.message.author.send(embed=error_embed)
            else:
                error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')

        else:
            print(str(error))
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

        if error_embed != None and dm == False:
            await ctx.send(embed=error_embed)

    @prefix.command(aliases=['set', 's'])
    @commands.bot_has_permissions(send_messages=True)
    @commands.has_permissions(administrator=True)
    async def prefix_set(self, ctx, prefix: str=None):
        if prefix == None or len(prefix) <= 3:
            with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
                with dbcon.cursor() as cur:
                    if prefix in [None, '.']:
                        cur.execute(f"UPDATE server SET prefix = NULL WHERE id = {ctx.guild.id};")
                        await ctx.send(f'Prefix is set to "." (default)')
                    else:
                        cur.execute(f"UPDATE server SET prefix = '{prefix}' WHERE id = {ctx.guild.id};")
                        await ctx.send(f'Prefix is set to "{prefix}"')
        else: raise prefixGreaterThan3
        dbcon.close()

    @prefix_set.error
    async def prefix_set_error(self, ctx, error):
        error_embed = None
        dm = False

        if isinstance(error, commands.BotMissingPermissions):
            if 'Send Messages' in str(error):
                dm = True
                error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')
                await ctx.message.author.send(embed=error_embed)
            else:
                error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')

        elif isinstance(error, commands.MissingPermissions):
            error_embed = set_error_embed(f'You are missing permission(s).\n\n> {error}')

        elif isinstance(error, commands.CommandInvokeError):
            error = error.original

            if isinstance(error, prefixGreaterThan3):
                error_embed = set_error_embed(f'The length of prefix must be `<` or `=` `3`',)
                add_command_and_example(ctx, error_embed, f'`prefix set [Prefix]`', f'.p s !!!')

            else:
                print(str(error), str(error.original))
                traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

        else: 
            print(str(error), str(error.original))
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        
        if error_embed != None and dm == False:
            await ctx.send(embed=error_embed)

def setup(client):
    client.add_cog(Prefix(client))