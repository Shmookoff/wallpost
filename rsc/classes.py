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

    def __init__(self, id, lang, token):
        self.id = id
        self.token = token
        self.lang = lang if (lang is not None) else "en"

        self.channels = []

        Server.all.append(self)

    @classmethod
    def init(cls, id, lang, token):
        self = cls(id, lang, token)
        print(f'Init {self}')
        return self

    @classmethod
    def uninit_all(cls):
        for server in cls.all:
            for channel in server.channels:
                for sub in channel.subscriptions:
                    channel.subscriptions.remove(sub)
                    Subscription.all.remove(sub)
                    sub.task.cancel()
                server.channels.remove(channel)
                Channel.all.remove(channel)
            cls.all.remove(server)

    @classmethod
    async def add(cls, id):
        self = cls(id, None, None)
        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("INSERT INTO server (id) VALUES(%s)", (self.id,))

        print(f'Add {self}', end='\n\n')
        return self

    async def delete(self):
        print(f'Del {self}')

        for channel in self.channels:
            await channel.delete()
        print("")

        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("DELETE FROM server WHERE id = %s", (self.id,))

        Server.all.remove(self)

    async def set_token(self, token):
        self.token = token
        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("UPDATE server SET token = %s WHERE id = %s", (self.token, self.id))

    async def set_lang(self, lang):
        pass

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

        self.subscriptions = []
        server.channels.append(self)

        Channel.all.append(self)

    @property
    def webhook_id(self):
        return webhook_url.split('/')[5]

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

        print(f'{self.server}')
        print(f'\tAdd {self}')
        if not (info is None):
            sub = await Subscription.add(self, info, True)
        else: print("")

        return self

    async def delete(self, is_called=False):
        if is_called is False:
            print(f'{self.server}')
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

        if is_called is False: print()

    def find_subs(self, wall_id, wall_type=None):
        if wall_type is None:
            subs = []
            i = 0
            for sub in self.subscriptions:
                if sub.wall_id == abs(wall_id):
                    subs.append(sub)
                    i += 1
                if i == 2:
                    break
            return subs
        else:
            for sub in self.subscriptions:
                if (sub.wall_id, sub.wall_type) == (abs(wall_id), wall_type):
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
        self.channel = channel

        self.wall_id = info['wall_id']
        self.wall_type = info['wall_type']
        self.added_by = info['added_by']
        if info['last_id'] is not None:
            self.last_id = info['last_id']
        else:
            self.token = info['token']

        self.task = loop.create_task(self.repost_task())

        channel.subscriptions.append(self)
        Subscription.all.append(self)

    @property
    def longpoll(self):
        return False if hasattr(self, "last_id") else True

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
                await cur.execute("INSERT INTO subscription (wall_id, wall_type, last_id, added_by, channel_id) VALUES(%s, %s, %s, %s, %s)", (self.wall_id, self.wall_type, self.last_id, self.added_by, self.channel.id))

        if is_called is False:
            print(f'{self.channel.server}')
            print(f'\t{self.channel}')
        print(f'\t\tAdd {self}', end ='\n\n')

        return self

    async def delete(self, is_called=False):
        if is_called is False:
            if len(self.channel.subscriptions) == 1:
                await self.channel.delete()
                return
            else:
                print(f'{self.channel.server}')
                print(f'\t{self.channel}')
                print(f'\t\tDel {self}', end='\n\n')

                async with aiopg.connect(sets["psqlUri"]) as conn:
                    async with conn.cursor(cursor_factory=DictCursor) as cur:
                        await cur.execute("DELETE FROM subscription WHERE channel_id = %s AND wall_id = %s AND wall_type = %s", (self.channel.id, self.wall_id, self.wall_type))
        else:
            print(f'\t\tDel {self}')

        Subscription.all.remove(self)
        self.channel.subscriptions.remove(self)

        self.task.cancel()

    def __str__(self):
        return f'SUB {self.wall_type.upper()}{self.wall_id} LP {self.longpoll}'

    async def repost_task(self):
        if hasattr(self, 'last_id'):
            wall_id = self.wall_id if (self.wall_type == 'u') else -self.wall_id
            while True:
                async with aiovk.TokenSession(self.channel.server.token) as ses:
                    vkapi = aiovk.API(ses)
                    wall = await vkapi.wall.get(owner_id=wall_id, extended=1, count=1, fields='photo_max', v='5.130')
                if len(wall['items']) > 0:
                    if 'is_pinned' in wall['items'][0]:
                        if wall['items'][0]['is_pinned'] == 1:
                            async with aiovk.TokenSession(self.channel.server.token) as ses:
                                vkapi = aiovk.API(ses)
                                wall = await vkapi.wall.get(owner_id=wall_id, extended=1, offset=1, count=1, fields='photo_max', v='5.130')
                    if len(wall['items']) > 0:
                        if self.last_id != wall['items'][0]['id']:
                            post_embed = compile_post_embed(wall)
                            async with ClientSession() as session:
                                try: await discord.Webhook.from_url(url=self.channel.webhook_url, adapter=discord.AsyncWebhookAdapter(session)).send(embed=post_embed)
                                except NotFound as exc:
                                    if exc.code == 10015:
                                        loop.create_task(self.channel.delete())
                                    else: print(exc)
                                else:
                                    self.last_id = wall['items'][0]['id']
                                    async with aiopg.connect(sets["psqlUri"]) as conn:
                                        async with conn.cursor(cursor_factory=DictCursor) as cur:
                                            await cur.execute("UPDATE subscription SET last_id = %s WHERE channel_id = %s AND wall_id = %s AND wall_type = %s",
                                                (self.last_id, self.channel.id, self.wall_id, self.wall_type))

                                    print(f'Repost POST {self.last_id} from {self} to {self.channel} on {self.channel.server}')
                await asyncio.sleep(60)
        else:
            async with aiovk.TokenSession(self.token) as ses:
                long_poll = BotsLongPoll(ses, group_id=self.wall_id)
                async for event in long_poll.iter():
                    if event['type'] == 'wall_post_new':
                        async with aiovk.TokenSession(self.token) as ses:
                            vkapi = aiovk.API(ses)
                            post_embed = compile_post_embed(event['object'], await vkapi.groups.getById(group_id=self.wall_id, fields='photo_max'))

                        async with ClientSession() as session:
                            try: await discord.Webhook.from_url(url=self.channel.webhook_url, adapter=discord.AsyncWebhookAdapter(session)).send(embed=post_embed)
                            except NotFound as exc:
                                if exc.status == 10015:
                                    self.loop.create_task(self.channel.delete())
                                else: print(exc)
                            else:
                                print(f'Repost POST {wall["items"][0]["id"]} from {self} to {self.channel} on {self.channel.server}')