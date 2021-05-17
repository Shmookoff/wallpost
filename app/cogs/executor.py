import discord
from discord.ext import commands

import traceback
import sys

import contextlib
import io

from rsc.functions import chn_service_or_owner


class Executor(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.command(aliases=['e'])
    @chn_service_or_owner()
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

    
name = 'Executor'

def setup(client):
    print(f'Load COG {name}')
    cog = Executor(client)
    client.add_cog(cog)

def teardown(client):
    print(f'Unload COG {name}')
    client.remove_cog(name)