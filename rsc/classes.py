import discord
from discord.errors import NotFound

import asyncio
import aiopg
import aiovk
from aiovk.longpoll import BotsLongPoll
from aiohttp import ClientSession

from psycopg2.extras import DictCursor

from rsc.config import sets
from rsc.functions import compile_post_embed


loop = asyncio.get_event_loop()

class Server: 
    all = []
    temp_data = []

    def __init__(self, id, prefix, lang, token):
        self.id = id
        self.token = token

        self.prefix = prefix if (prefix is not None) else "."
        self.lang = lang if (lang is not None) else "en"

        self.channels = []

        Server.all.append(self)

    @classmethod
    def init(cls, id, prefix, lang, token):
        self = cls(id, prefix, lang, token)
        print(f'Init {self}')
        return self

    @classmethod
    def uninit_all(cls):
        for server in cls.all:
            for channel in server.channels:
                for sub in channel.subscriptions:
                    sub.task.cancel()
                    del sub
                del channel
            del server

    @classmethod
    async def add(cls, id):
        self = cls(id, None, None, None)
        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("INSERT INTO server (id) VALUES(%s)", (self.id,))

        print(f'\nAdd {self}\n')
        return self

    async def delete(self):
        print(f'\nDel {self}')

        for channel in self.channels:
            await channel.delete()
        print("")

        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("DELETE FROM server WHERE id = %s", (self.id,))

        Server.all.remove(self)
        del self

    async def set_token(self, token):
        self.token = token
        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("UPDATE server SET token = %s WHERE id = %s", (self.token, self.id))

    async def set_lang(self, lang):
        pass

    async def set_prefix(self, prefix):
        if prefix == '.': prefix = None
        
        self.prefix = prefix if prefix is not None else '.'

        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("UPDATE server SET prefix = %s WHERE id = %s", (prefix, self.id))

        return self.prefix

    def find_channel(self, id):
        for channel in self.channels:
            if channel.eq_by_args(id):
                return channel
        return None

    def eq_by_args(self, other_id):
        return self.id == other_id
    
    @classmethod
    def find_by_args(cls, id):
        for server in cls.all:
            if server.eq_by_args(id):
                return server
        return None

    def __str__(self):
        return f'SRV {self.id}'

class Channel:
    all = []

    def __init__(self, server, id, webhook_url):
        self.server = server

        self.id = id
        self.webhook_url = webhook_url
        self.webhook_id = webhook_url.split('/')[5]

        self.subscriptions = []
        server.channels.append(self)

        Channel.all.append(self)

    @classmethod
    def init(cls, server, id, webhook_url):
        self = cls(server, id, webhook_url)
        print(f'\tInit {self}')
        return self

    @classmethod
    async def add(cls, server, discord_channel, info=None):
        webhook = await discord_channel.create_webhook(name=f"WallPost {sets['version'] if sets['version'] == 'DEV' else 'VK'}")
        self = cls(server, discord_channel.id, webhook.url)

        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("INSERT INTO channel (id, webhook_url, server_id) VALUES(%s, %s, %s)", (self.id, self.webhook_url, self.server.id))

        print(f'\n{self.server}')
        print(f'\tAdd {self}')
        if not (info is None):
            try:
                sub = await Subscription.add(self, info, True)
            except Exception as exc: print(exc)
        else: print("")

        return self

    async def delete(self, is_called=False):
        if is_called is False:
            print(f'\n{self.server}')
        print(f'\tDel {self}')

        for sub in self.subscriptions:
            await sub.delete(is_called=True)

        if is_called is False:
            async with ClientSession() as session:
                try: await discord.Webhook.from_url(url=self.webhook_url, adapter=discord.AsyncWebhookAdapter(session)).delete()
                except NotFound as exc:
                    if exc.code == 10015: pass
                    else: print(exc)

            async with aiopg.connect(sets["psqlUri"]) as conn:
                async with conn.cursor(cursor_factory=DictCursor) as cur:
                    await cur.execute("DELETE FROM channel WHERE id = %s", (self.id,))

        Channel.all.remove(self)
        self.server.channels.remove(self)

        if is_called is False: print("")

        del self

    def find_subs(self, id, wall = None):
        if wall is None:
            subs = []
            i = 0
            for sub in self.subscriptions:
                if sub.id == abs(id):
                    subs.append(sub)
                    i += 1
                if i == 2:
                    break
            return subs
        else:
            for sub in self.subscriptions:
                if (sub.id, sub.type) == (abs(id), wall):
                    return sub
        return None

    def eq_by_args(self, other_id):
        return self.id == other_id

    @classmethod
    def find_by_args(cls, id):
        for chn in cls.all:
            if eq_by_args(chn, id):
                return chn
        return None

    def __str__(self):
        return f'CHN {self.id} WH {self.webhook_id}'


class Subscription:
    all = []

    def __init__(self, channel, info):
        self.server = channel.server
        self.channel = channel

        self.id = info['vk_id']
        self.type = info['vk_type']
        self.longpoll = info['long_poll']
        self.last_post_id = info['last_post_id']
        self.token = info['token']

        self.task = loop.create_task(self.repost_task())

        channel.subscriptions.append(self)

        Subscription.all.append(self)

    @classmethod
    def init(cls, channel, info):
        self = cls(channel, info)
        print(f'\t\tInit {self}')
        return self

    @classmethod
    async def add(cls, channel, info, is_called=False):
        self = cls(channel, info)

        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("INSERT INTO subscription (vk_id, vk_type, long_poll, last_post_id, channel_id) VALUES(%s, %s, %s, %s, %s)", (self.id, self.type, self.longpoll, self.last_post_id, self.channel.id))

        if is_called is False:
            print(f'\n{self.server}')
            print(f'\t{self.channel}')
        print(f'\t\tAdd {self}\n')

        return self

    async def delete(self, is_called=False):
        if is_called is False:
            if len(self.channel.subscriptions) == 1:
                await self.channel.delete()
                return
            else:
                print(f'\n{self.server}')
                print(f'\t{self.channel}')
                print(f'\t\tDel {self}\n')

                async with aiopg.connect(sets["psqlUri"]) as conn:
                    async with conn.cursor(cursor_factory=DictCursor) as cur:
                        await cur.execute("DELETE FROM subscription WHERE channel_id = %s AND vk_id = %s AND vk_type = %s", (self.channel.id, self.id, self.type))
        else:
            print(f'\t\tDel {self}')

        Subscription.all.remove(self)
        self.channel.subscriptions.remove(self)

        loop.create_task(self.delete_task())

    async def delete_task(self):
        self.task.cancel()
        del self

    def __str__(self):
        return f'SUB {self.type.upper()}{self.id} LP {self.longpoll}'

    async def repost_task(self):
        if self.longpoll is False:
            vk_id = self.id if (self.type == 'u') else -self.id
            while True:
                async with aiovk.TokenSession(self.server.token) as ses:
                    vkapi = aiovk.API(ses)
                    wall = await vkapi.wall.get(owner_id=vk_id, extended=1, count=1, fields='photo_max', v='5.130')
                if len(wall['items']) > 0:
                    if 'is_pinned' in wall['items'][0]:
                        if wall['items'][0]['is_pinned'] == 1:
                            async with aiovk.TokenSession(self.server.token) as ses:
                                vkapi = aiovk.API(ses)
                                wall = await vkapi.wall.get(owner_id=vk_id, extended=1, offset=1, count=1, fields='photo_max', v='5.130')
                    if len(wall['items']) > 0:
                        if self.last_post_id != wall['items'][0]['id']:
                            post_embed = compile_post_embed(wall)
                            async with ClientSession() as session:
                                try: await discord.Webhook.from_url(url=self.channel.webhook_url, adapter=discord.AsyncWebhookAdapter(session)).send(embed=post_embed)
                                except NotFound as exc:
                                    if exc.code == 10015:
                                        loop.create_task(self.channel.delete())
                                    else: print(exc)
                                else:
                                    async with aiopg.connect(sets["psqlUri"]) as conn:
                                        async with conn.cursor(cursor_factory=DictCursor) as cur:
                                            await cur.execute("UPDATE subscription SET last_post_id = %s WHERE channel_id = %s AND vk_id = @ %s AND vk_type = %s", (wall["items"][0]["id"], self.channel.id, self.id, self.type))

                                    self.last_post_id = wall['items'][0]['id']

                                    print(f'Repost POST {wall["items"][0]["id"]} from {self} to {self.channel} on {self.server}')
                await asyncio.sleep(60)

        if self.longpoll is True:
            async with aiovk.TokenSession(self.token) as ses:
                long_poll = BotsLongPoll(ses, group_id=self.id)
                async for event in long_poll.iter():
                    if event['type'] == 'wall_post_new':
                        async with aiovk.TokenSession(self.token) as ses:
                            vkapi = aiovk.API(ses)
                            post_embed = compile_post_embed(event['object'], await vkapi.groups.getById(group_id=self.id, fields='photo_max'))

                        async with ClientSession() as session:
                            try: await discord.Webhook.from_url(url=self.channel.webhook_url, adapter=discord.AsyncWebhookAdapter(session)).send(embed=post_embed)
                            except NotFound as exc:
                                if exc.status == 10015:
                                    self.loop.create_task(self.channel.delete())
                                else: print(exc)
                            else:
                                print(f'Repost POST {wall["items"][0]["id"]} from {self} to {self.channel} on {self.server}')