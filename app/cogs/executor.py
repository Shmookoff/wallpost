import discord
from discord.ext import commands

import traceback
import sys

import contextlib
import io

from rsc.functions import check_service_chn


class Executor(commands.Cog):
    __name__ = 'Executor'
    
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


    @commands.command(aliases=['e'])
    @check_service_chn()
    async def execute(self, ctx, *, code):
        if code.startswith('```py') and code.endswith('```'):
            code = code[5:-3]
        elif code.startswith('```') and code.endswith('```'):
            code = code[3:-3]
        
        if code.startswith('\n'):
            code = code[1:]
        if code.endswith('\n'):
            code = code[:-1]

        stream = io.StringIO()
        try:
            with contextlib.redirect_stdout(stream):
                exec(code)
        except Exception as exc:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            return await ctx.send(f'```py\n{tb}\n```')
        await ctx.send(f'```py\n{stream.getvalue()}\n```')

    def send(self, chn, msg):
        async def f(chn, msg):
            chn = self.client.get_channel(chn)
            await chn.send(msg)
        self.client.loop.create_task(f(chn, msg))


def setup(client):
    client.add_cog(Executor(client))