import discord
from discord.ext import commands

import asyncio.exceptions as asycnio_exceptions
import discord_slash.error as slash_errors
import aiovk.exceptions as aiovk_errors

from rsc.config import sets
from rsc.functions import set_error_embed, add_command_and_example
from rsc.exceptions import *


class ExceptionHandler(commands.Cog):
    __name__ = 'Exception Handler'

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
                    await self.client.error_handler('command', ctx=ctx, exc=exc)

    @commands.Cog.listener()
    async def on_slash_command_error(self, ctx, exc):
        if ctx.name == 'subs':
            if isinstance(exc, asycnio_exceptions.TimeoutError):
                await ctx.msg.clear_reactions()
                await ctx.msg.edit(content='❌ Cancelled (timeout)', components=[], embed=None)
                return

            if ctx.subcommand_name == 'account':
                pass
            elif ctx.subcommand_name == 'link':
                pass
            elif ctx.subcommand_name == 'add':
                if isinstance(exc, MaximumWebhooksReached):
                    exc.embed = set_error_embed(f'Maximum number of webhooks reached (10).\n> Try removing a webhook from {ctx.webhook_channel.mention}.')
                elif isinstance(exc, WallClosed):
                    exc.embed = set_error_embed(f'Wall is closed\n\n> Your VK account doesn\'t have access to wall **{ctx.kwargs["wall_id"]}**.')
                elif isinstance(exc, SubExists):
                    exc.embed = set_error_embed(f'{ctx.webhook_channel.mention} is already subscribed to wall **{ctx.kwargs["wall_id"]}**.')
                elif isinstance(exc, MsgTooLong):
                    exc.embed = set_error_embed(f'Message is too long.')
            elif ctx.subcommand_name == 'info':
                if isinstance(exc, NoSubs):
                    exc.embed = set_error_embed(f'{ctx.webhook_channel.mention} doesn\'t have any subscriptions.')
            elif ctx.subcommand_name == 'del':
                if isinstance(exc, NotSub):
                    exc.embed = set_error_embed(f'{ctx.webhook_channel.mention} isn\'t subscribed to wall **{ctx.kwargs["wall_id"]}**.')
        elif ctx.name == 'cogs':
            if isinstance(exc, slash_errors.CheckFailure):
                exc.embed = set_error_embed(f'No 🙂')
            
        if not hasattr(exc, 'embed'):
            if isinstance(exc, NotAuthenticated):
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
            await self.client.error_handler('slash_command', ctx=ctx, exc=exc)

    @commands.Cog.listener()
    async def on_ipc_error(self, endpoint, exc):
        await self.client.error_handler('endpoint', endpoint=endpoint, exc=exc)

def setup(client):
    client.add_cog(ExceptionHandler(client))