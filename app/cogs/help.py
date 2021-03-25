import discord
from discord.ext import commands

import traceback
import sys

from rsc.config import vars

class Help(commands.Cog):
    def __init__(self, client):
        self.client = client


    @commands.group(aliases=['h', '?'], invoke_without_command=True)
    @commands.bot_has_permissions(send_messages=True)
    async def help(self, ctx):
        help_embed = discord.Embed(
            title = 'Help',
            description = f'Use `help (Command)` to show help for a command.',
            color = vars["embedColor"]
        )

        help_embed.add_field(
            name = 'sub (s, subscriptions)',
            value = '`Work in progress.`\n\nSubcommands:\n```sub add [Channel Mention] [VK Wall]\n    Subscribes channel to updates on the wall.\n    Aliases: a\n\nsub info [Channel Mention]\n    Displays list of subscriptions for channel.\n    Aliases: i, information\n\nsub del [Channel Mention] [VK Wall]\n    Unsubscribes channel from updates on the wall.\n    Aliases: d, delete```',
            inline = False
        )

        help_embed.add_field(
            name = 'prefix (p)',
            value = '`Shows current prefix for the server.`\n\nSubcommands:\n```prefix set (Prefix)\n    Sets prefix for the server. If no Prefix passed, sets to default prefix — "."\n    Aliases: s```',
            inline = False
        )

        help_embed.add_field(
            name = 'help (h, ?)',
            value = '`Shows this message.`',
            inline = False
        )

        await ctx.send(embed=help_embed)

    @help.error
    async def help_error(self, ctx, error):
        print(str(error))
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
def setup(client):
    client.add_cog(Help(client))