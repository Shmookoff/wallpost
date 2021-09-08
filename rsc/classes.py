import discord
from discord.ext import commands

import logging
import sys
from io import StringIO


class SafeDict(dict):
    def __missing__(self, key):
        return '{'+key+'}'

class WPLogger(logging.Logger):
    def __init__(self, loop):
        super().__init__('WallPost', logging.DEBUG)
        self.loop = loop
        self.formatter = logging.Formatter('[%(levelname)s]: %(message)s')

        self.add_stream_handler(logging.DEBUG)

    def add_stream_handler(self, level):
        stream_handler = StreamHandler(level)
        stream_handler.setFormatter(self.formatter)
        self.addHandler(stream_handler)

    def add_discord_handler(self, level, channel):
        discord_handler = DiscordHandler(level, self.loop, channel)
        discord_handler.setFormatter(self.formatter)
        self.addHandler(discord_handler)

class WPLoggerAdapter(logging.LoggerAdapter):
    def __init__(self, logger, extra={}):
        super().__init__(logger, extra)

    def process(self, msg, kwargs):
        extra = kwargs.get("extra", {})
        extra.update({"tb": kwargs.pop("tb", '')})
        kwargs["extra"] = extra
        return msg, kwargs

class StreamHandler(logging.StreamHandler):
    def __init__(self, level):
        super().__init__(sys.stdout)
        self.setLevel(level)

    def emit(self, record):
        try:
            msg = self.format(record)
            msg = msg.format_map(SafeDict(t='', ttt='', tttpy='', aa=''))
            if record.tb != '':
                msg = f'{msg}\n{record.tb}'

            self.stream.write(msg + self.terminator)
            self.flush()
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)

class DiscordHandler(logging.StreamHandler):
    def __init__(self, level, loop, channel: discord.TextChannel):
        super().__init__()
        self.loop = loop
        self.channel = channel
        self.setLevel(level)

    def emit(self, record):
        try:
            msg = self.format(record)
            msg = msg.format_map(SafeDict(t='`', ttt='```', tttpy='```py', aa='**'))
            if record.tb != '':
                if len(f'{msg}\n```py\n{record.tb}\n```') <= 2000:
                    task = self.channel.send(f'{msg}\n```py\n{record.tb}\n```')
                else:
                    task = self.channel.send(msg, file=discord.File(StringIO(record.tb), filename='traceback.python'))
            else:
                task = self.channel.send(content=msg)

            self.loop.create_task(task)
            self.flush()
        except Exception as exc:
            self.handleError(record)