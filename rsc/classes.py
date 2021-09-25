import discord

import logging
import sys
from datetime import datetime
from io import StringIO

from rsc.config import sets


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

class VKRespWrapper:
    def __init__(self, type_: str, wall: dict=None, post: dict=None, vk_info: dict=None, error: dict=None):
        self.type = type_
        if not error:
            self.wall = wall
            if wall:
                if type_ == 'grp':
                    self.id = -wall['id']
                    self.wall_url = f"https://vk.com/club{wall['id']}"
                    self.name = wall['name']
                else:
                    self.id = wall['id']
                    self.wall_url = f"https://vk.com/id{wall['id']}"
                    self.name = f"{wall['first_name']} {wall['last_name']}"
                self.wall_embed = self.compile_wall_embed(vk_info)
            self.post = post
            if post:
                if post['items'][0]['id'] > 0:
                    self.post_embed = self.compile_post_embed(vk_info)
        else:
            self.error = error

    def compile_wall_embed(self, vk_info) -> discord.Embed:
        embed = discord.Embed(
            title=self.name,
            url=self.wall_url,
            color=sets["embedColor"])

        if self.wall['status'] != '':
            embed.add_field(
                name = 'Status',
                value = f'> {self.wall["status"]}',
                inline = False)
        embed.add_field(
            name = 'Short address',
            value = f'`{self.wall["screen_name"]}`',
            inline = True)
        if self.type == 'grp':
            embed.add_field(
                name = 'Members',
                value = f'`{self.wall["members_count"]}`',
                inline = True)
            embed.set_thumbnail(url=self.wall['photo_200'])
        else:
            embed.add_field(
                name = 'Followers',
                value = f'`{self.wall["followers_count"] if "followers_count" in self.wall else 0}`',
                inline = True)
            embed.set_thumbnail(url=self.wall['photo_max'])
        embed.add_field(
            name = 'Verified',
            value = '✅' if self.wall['verified'] else '❎',
            inline = True)
        embed.set_footer(text=vk_info['name'], icon_url=vk_info['photo'])
        return embed

    def compile_post_embed(self, vk_info) -> discord.Embed:
        post = self.post['items'][0]
        embed = discord.Embed(
            title = 'Open post',
            url = f'https://vk.com/wall{post["owner_id"]}_{post["id"]}',
            description = post['text'] if len(post['text']) <= 4096 else f"{post['text'][:4095]}…",
            timestamp = datetime.utcfromtimestamp(post['date']),
            color = sets["embedColor"])
        
        if self.wall is None: 
            if self.type == 'grp':
                for group in self.post['groups']:
                    if group['id'] == -post['owner_id']:
                        author = group
                        break
                embed.set_author(
                name = author['name'],
                url = f'https://vk.com/club{author["id"]}',
                icon_url = author['photo_max'])
            else:
                for profile in self.post['profiles']:
                    if profile['id'] == post['owner_id']:
                        author = profile
                        break
                embed.set_author(
                name = f'{author["first_name"]} {author["last_name"]}',
                url = f'https://vk.com/id{author["id"]}',
                icon_url = author['photo_200'])
        else:
            if self.type == 'grp':
                icon_url = self.wall['photo_max']
            else:
                icon_url = self.wall['photo_200']
            embed.set_author(
                name = self.name,
                url = self.wall_url,
                icon_url = icon_url)

        has_photo = False
        if post.get('attachments', False):
            for attachment in post['attachments']:
                if attachment['type'] == 'photo':
                    has_photo = True
                    hw = 0
                    image_url = ''
                    for size in attachment['photo']['sizes']:
                        if size['width']*size['height'] > hw:
                            hw = size['width']*size['height']
                            image_url = size['url']
                    embed.set_image(url = image_url)
                    break

        if 'copy_history' in post: 
            repost = post['copy_history'][0]
            if len(repost['text']) > 0:
                repost['text'] = repost['text'] if len(repost['text']) <= 900 else f"{repost['text'][:900]}…"
                embed.add_field(
                    name = '↪️ Repost',
                    value = f'[**Open repost**](https://vk.com/wall{repost["owner_id"]}_{repost["id"]})\n>>> {repost["text"]}')
            else:
                embed.add_field(
                    name = '↪️ Repost',
                    value = f'[**Open repost**](https://vk.com/wall{repost["owner_id"]}_{repost["id"]})')
            
            if not has_photo:
                if repost.get('attachments', False):
                    for attachment in repost['attachments']:
                        if attachment['type'] == 'photo':
                            hw = 0
                            image_url = ''
                            for size in attachment['photo']['sizes']:
                                if size['width']*size['height'] > hw:
                                    hw = size['width']*size['height']
                                    image_url = size['url']
                            embed.set_image(url = image_url)
                            break

        embed.set_footer(text=vk_info['name'], icon_url=vk_info['photo'])
        return embed