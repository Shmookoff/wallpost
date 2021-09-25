import discord
from discord.ext import commands

from rsc.config import sets


def check_service_chn():
    def predicate(ctx):
        if hasattr(ctx, 'channel_id'):
            return ctx.channel_id == sets["srvcChnId"]
        return ctx.channel.id == sets["srvcChnId"]
    return commands.check(predicate)

#Errors

def set_error_embed(d) -> discord.Embed:
    return discord.Embed(color=sets["errorColor"], description=d)

def add_command_and_example(ctx, error_embed):
    if ctx.name == 'subs':
        if ctx.subcommand_name == 'add':
            command, example = '`/subs add [wall_id] (channel)`', f'/subs add apiclub {ctx.channel.mention}\n/subs add 1'
        elif ctx.subcommand_name == 'info':
            command, example = '`/subs info (channel)`', f'/subs info {ctx.channel.mention}\n/subs info'
        elif ctx.subcommand_name == 'del':
            command, example = '`/subs del [wall_id] (channel)`', f'/subs del apiclub {ctx.channel.mention}\n/subs del 1'

    error_embed.add_field(
        name = 'Command',
        value = command,
        inline = False
    )
    error_embed.add_field(
        name = 'Example',
        value = example,
        inline = False
    )
