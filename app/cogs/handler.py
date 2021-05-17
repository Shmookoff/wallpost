import discord
from discord.ext import commands

import traceback
import sys

from aiovk.exceptions import VkAuthError

from rsc.functions import set_error_embed, add_command_and_example
from rsc.exceptions import *

import time

class ExceptionHandler(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.log_chn = client.get_channel(836705410630287451)
        print(f'    Set LOG_CHN {self.log_chn.name} at {self.log_chn.guild.name}\n')

    @commands.Cog.listener()
    async def on_command_error(self, ctx, exc):
        if isinstance(exc, commands.CommandNotFound):
            pass
        else:
            if not hasattr(exc, 'embed'):
                if isinstance(exc, commands.CommandInvokeError):
                    exc = exc.original

                    if isinstance(exc, NotAuthenticated):
                        exc.embed = set_error_embed(f'You aren\'t authenticated.\n\n> Run `sub` command to link your VK profile.')
                    elif isinstance(exc, VkIdNotSpecified):
                        exc.embed = set_error_embed(f'`[VK Wall]` is not specified.\n\n> Please, specify `[VK Wall]` as **String**.')
                        exc.command_and_example = True
                    elif isinstance(exc, VkWallBlocked):
                        exc.embed = set_error_embed(f'`[VK Wall]` is invalid.\n\n> Wall **{ctx.args[2]}** may be blocked, deactivated, deleted or it may not exist.')

                elif isinstance(exc, commands.BotMissingPermissions):
                    if 'send_messages' in exc.missing_perms:
                        exc.embed = set_error_embed(f'Bot is missing permission(s).\n\n> {exc}')
                        exc.dm = True
                    else:
                        exc.embed = set_error_embed(f'Bot is missing permission(s).\n\n> {exc}')
                elif isinstance(exc, commands.MissingPermissions):
                    exc.embed = set_error_embed(f'You are missing permission(s).\n\n> {exc}')
                elif isinstance(exc, VkAuthError):
                    exc.embed = set_error_embed('Can\'t gain access to your VK account.\n\n> Your VK account got unlinked.')
                elif isinstance(exc, commands.ChannelNotFound):
                    exc.embed = set_error_embed(f'Channel is not found.\n\n> Please, pass in `[Channel Mention]` as **Channel Mention** from current server.')
                    exc.command_and_example = True
                elif isinstance(exc, commands.BadArgument):
                    exc.embed = set_error_embed(f'One or more arguments are invalid.\n\n> Please, pass in all arguments as in examples below.')
                    exc.command_and_example = True

            if hasattr(exc, 'embed'):
                if hasattr(exc, 'command_and_example'):
                    add_command_and_example(ctx, exc.embed)

                if hasattr(exc, 'dm'):
                    await ctx.message.author.send(embed=exc.embed)
                else: 
                    await ctx.send(embed=exc.embed)
            else:
                tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                print(f'Ignoring exception in command {ctx.command}:\n{tb}', file=sys.stderr)
                await self.log_chn.send(f'Ignoring exception in command `{ctx.command}`:\n```py\n{tb}\n```')   

    @commands.Cog.listener()
    async def on_ipc_error(self, endpoint, exc):
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        print(f'Ignoring exception in {endpoint} endpoint:\n{tb}', file=sys.stderr)
        await self.log_chn.send(f'Ignoring exception in `{endpoint}` endpoint:\n```py\n{tb}\n```')


name = 'ExceptionHandler'

def setup(client):
    print(f'Load {name}')
    cog = ExceptionHandler(client)
    client.add_cog(cog)

def teardown(client):
    print(f'Unload {name}')
    client.remove_cog(name)