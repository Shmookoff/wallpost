import discord
from discord.ext import commands

import traceback
import sys
from io import StringIO

import discord_slash.error as slash_errors
import aiovk.exceptions as aiovk_errors

from rsc.config import sets
from rsc.functions import set_error_embed, add_command_and_example
from rsc.exceptions import *


class ExceptionHandler(commands.Cog):
    __name__ = 'Exception Handler'

    def __init__(self, client):
        print(f'Load COG {self.__name__}')

        self.client = client

        print(f'\tSet LOG_CHN {self.client.log_chn.name} at {self.client.log_chn.guild.name}')

    def cog_unload(self):
        print(f'Unload COG {self.__name__}')


    @commands.Cog.listener()
    async def on_command_error(self, ctx, exc):
        if not (isinstance(exc, commands.CommandNotFound)):
            if not hasattr(exc, 'embed'):
                if isinstance(exc, commands.CheckFailure):
                    exc._pass = True
            
            if not (hasattr(exc, '_pass')):
                if hasattr(exc, 'embed'):
                    await ctx.send(embed=exc.embed)
                else:
                    tb = traceback.format_exc()
                    print(f'Ignoring exception in COMMAND .{ctx.command}.\nParams: {ctx.kwargs}\n{tb}', file=sys.stderr)
                    msg = f'Ignoring exception in *COMMAND* `.{ctx.command}`.\nParams: `{ctx.kwargs}`\n```py\n{tb}\n```'
                    if len(msg) <= 2000:
                        await self.client.log_chn.send(msg)
                    else:
                        await self.client.log_chn.send(f'Ignoring exception in *COMMAND* `.{ctx.command}`.\nParams: `{ctx.kwargs}`', file=discord.File(StringIO(tb), filename='traceback.txt'))

    @commands.Cog.listener()
    async def on_slash_command_error(self, ctx, exc):
        if ctx.name == 'subs':
            if ctx.subcommand_name == 'account':
                pass
            elif ctx.subcommand_name == 'link':
                pass
            elif ctx.subcommand_name == 'add':
                if isinstance(exc, ChannelForbiddenWebhooks):
                    exc.embed = set_error_embed(f'WallPost VK is missing **Manage Webhooks** permission in Channel.\n\n> Try giving WallPost VK **Manage Webhooks** permission in {ctx.webhook_channel.mention}.')
                if isinstance(exc, MaximumWebhooksReached):
                    exc.embed = set_error_embed(f'Maximum number of webhooks reached (10).\n> Try removing a webhook from {ctx.webhook_channel.mention}.')
                elif isinstance(exc, WallClosed):
                    exc.embed = set_error_embed(f'Wall is closed\n\n> Your VK account doesn\'t have access to wall **{ctx.kwargs["wall_id"]}**.')
                elif isinstance(exc, SubExists):
                    exc.embed = set_error_embed(f'{ctx.webhook_channel.mention} is already subscribed to wall **{ctx.kwargs["wall_id"]}**.')
            elif ctx.subcommand_name == 'info':
                if isinstance(exc, NoSubs):
                    exc.embed = set_error_embed(f'{ctx.webhook_channel.mention} doesn\'t have any subscriptions.')
            elif ctx.subcommand_name == 'del':
                if isinstance(exc, NotSub):
                    exc.embed = set_error_embed(f'{ctx.webhook_channel.mention} isn\'t subscribed to wall **{ctx.kwargs["wall_id"]}**.')

        if not hasattr(exc, 'embed'):
            if isinstance(exc, slash_errors.CheckFailure):
                exc.embed = set_error_embed(f'No 🙂')
            elif isinstance(exc, NotAuthenticated):
                exc.embed = set_error_embed(f'You aren\'t authenticated.\n\n> Use `/subs link` to link your VK profile.')
            elif isinstance(exc, aiovk_errors.VkAuthError):
                exc.embed = set_error_embed('Can\'t gain access to your VK account.\n\n> Use `/subs link` to relink your VK profile.')
            elif isinstance(exc, WallIdBadArgument):
                exc.embed = set_error_embed(f'VK Wall ID is invalid.\n\n>>> **{ctx.kwargs["wall_id"]}** isn\'t a valid VK Wall ID.\nPlease, specify `[wall_id]` as **String**')
                exc.command_and_example = True
            elif isinstance(exc, VkWallBlocked):
                exc.embed = set_error_embed(f'Can\'t gain access to this Wall.\n\n> Wall **{ctx.kwargs["wall_id"]}** may be blocked, deactivated, deleted or it may not exist.')
            elif isinstance(exc, commands.BotMissingPermissions):
                exc.embed = set_error_embed(f'Bot is missing permission(s).\n\n> {exc}')
            elif isinstance(exc, commands.MissingPermissions):
                exc.embed = set_error_embed(f'You are missing permission(s).\n\n> {exc}')

        if hasattr(exc, 'embed'):
            if hasattr(exc, 'command_and_example'):
                add_command_and_example(ctx, exc.embed)

            if hasattr(ctx, 'msg'):
                await ctx.msg.edit(content=None, embed=exc.embed)
            else:
                await ctx.send(embed=exc.embed)
        else:
            tb = traceback.format_exc()
            print(f'Ignoring exception in COMMAND `/{ctx.name}{" "+ctx.subcommand_name if ctx.subcommand_name is not None else ""}`:\nParams: {ctx.kwargs}\n{tb}', file=sys.stderr)
            msg = f'Ignoring exception in *COMMAND* `/{ctx.name}{" "+ctx.subcommand_name if ctx.subcommand_name is not None else ""}`:\nParams: `{ctx.kwargs}`\n```py\n{tb}\n```'
            if len(msg) <= 2000:
                await self.client.log_chn.send(msg)
            else:
                await self.client.log_chn.send(f'Ignoring exception in *COMMAND* `/{ctx.name}{" "+ctx.subcommand_name if ctx.subcommand_name is not None else ""}`:\nParams: `{ctx.kwargs}`', file=discord.File(StringIO(tb), filename='traceback.txt'))

    @commands.Cog.listener()
    async def on_ipc_error(self, endpoint, exc):
        tb = traceback.format_exc()
        print(f'Ignoring exception in {endpoint} IPC ENDPOINT.\n{tb}', file=sys.stderr)
        msg = f'Ignoring exception in `{endpoint}` *IPC ENDPOINT*:\n```py\n{tb}\n```'
        if len(msg) <= 2000:
            await self.client.log_chn.send(msg)
        else:
            await self.client.log_chn.send(f'Ignoring exception in `{endpoint}` *IPC ENDPOINT*:', file=discord.File(StringIO(tb), filename='traceback.txt'))


def setup(client):
    client.add_cog(ExceptionHandler(client))