import discord
from discord.ext import commands, tasks
from discord import errors as discord_errors

import asyncio
import aiopg
import aiovk
from aiovk.longpoll import BotsLongPoll
from aiovk.pools import AsyncVkExecuteRequestPool
from aiohttp import ClientSession

from psycopg2.extras import DictCursor

from rsc.config import sets, vk_sets
from rsc.classes import SafeDict
from rsc.functions import compile_post_embed
from rsc.exceptions import MsgTooLong


class Repost(commands.Cog):
    __name__ = 'Repost'

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


    def Wall_init(self, id_, public, last_id):
        wall = Repost.Wall(self, id_, public, last_id)
        msg = f'Init {wall}'
        return wall, msg
        
    async def Wall_add(self, id_, last_id):
        wall = Repost.Wall(self, id_, True, last_id)
        msg = f'Add {wall}'
        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("INSERT INTO wall (id, public, last_id) VALUES(%s, %s, %s)", (
                    wall.id, wall.public, wall.last_id))
        return wall, msg

    def User_init(self, id_, token):
        usr = Repost.User(self, id_, token)
        msg = f'Init {usr}'
        return usr, msg

    async def User_add(self, id_):
        usr = Repost.User(self, id_, None)
        msg = f'Add {usr}'
        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("INSERT INTO users (id) VALUES(%s)", (usr.id,))
        return usr, msg

    def Server_init(self, id_, lang):
        srv = Repost.Server(self, id_, lang)
        msg = f'Init {srv}'
        return srv, msg

    async def Server_add(self, id_):
        srv = Repost.Server(self, id_, "en")
        msg = f'Add {srv}'
        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("INSERT INTO server (id) VALUES(%s)", (srv.id,))
        return srv, msg

    class Wall:
        all_ = set()

        def __init__(self, cog, id_, public, last_id):
            self.cog = cog
            self.id = id_
            self.public = public
            self.last_id = last_id

            self.subscriptions = set()
            Repost.Wall.all_.add(self)

        def __str__(self):
            return f'WALL {self.id} PUB {self.public} LAST {self.last_id}'

        async def delete(self):
            msg = f'Del {self}'
            async with aiopg.connect(sets["psqlUri"]) as conn:
                async with conn.cursor(cursor_factory=DictCursor) as cur:
                    await cur.execute("DELETE FROM wall WHERE id = %s", (self.id,))
            Repost.Wall.all_.remove(self)
            return msg

        def eq_by_args(self, other_id):
            return self.id == other_id

        @classmethod
        def find_by_args(cls, id_):
            wall, msg = None, str()
            for _wall in cls.all_:
                if _wall.eq_by_args(id_):
                    wall = _wall
                    msg += f'{wall}'
                    break
            return wall, msg

    class User:
        all_ = set()
        auth_data = list()

        def __init__(self, cog, id_, token):
            self.cog = cog
            self.id = id_
            self.token = token
            self.subscriptions = set()

            Repost.User.all_.add(self)
            self.sleep_on_error = 30
            self.repost_task.start()

        def __str__(self):
            return f'USR {self.id}'

        async def set_token(self, token):
            self.token = token
            async with aiopg.connect(sets["psqlUri"]) as conn:
                async with conn.cursor(cursor_factory=DictCursor) as cur:
                    await cur.execute("UPDATE users SET token = %s WHERE id = %s", (self.token, self.id))

        def eq_by_args(self, other_id):
            return self.id == other_id
        
        @classmethod
        def find_by_args(cls, id_):
            usr, msg = None, str()
            for _usr in cls.all_:
                if _usr.eq_by_args(id_):
                    usr = _usr
                    msg += f'{usr}'
                    break
            return usr, msg
        
        @tasks.loop(seconds=60)
        async def repost_task(self):
            new_post = False
            # Check if subs changed
            if self.task_subs != self.subscriptions:
                self.task_subs = self.subscriptions.copy()
                self.task_walls = dict()
                for sub in self.task_subs:
                    if sub.wall.id not in self.task_walls:
                        self.task_walls[sub.wall.id] = {'wall': sub.wall, 'subs': set(), 'req': None, 'empty': False}
                    self.task_walls[sub.wall.id]['subs'].add(sub)
            # Req for posts
            for wall_id in self.task_walls:
                self.task_walls[wall_id]['req'] = self.vk_pool.add_call('wall.get', self.token, {
                    'owner_id': wall_id, 'extended': 1, 'count': 1, 'fields': 'photo_max', 'v': '5.84'})
            await self.vk_pool.execute()
            # Offset req for pinned posts
            for wall_id in self.task_walls:
                resp = self.task_walls[wall_id]['req'].result
                if len(resp['items']) > 0:
                    if resp['items'][0].get('is_pinned', False):
                        self.task_walls[wall_id]['req'] = self.vk_pool.add_call('wall.get', self.token, {
                            'owner_id': wall_id, 'extended': 1, 'offset': 1, 'count': 1, 'fields': 'photo_max', 'v': '5.84'})
            await self.vk_pool.execute()
            # Disable empty walls
            for wall_id in self.task_walls:
                resp = self.task_walls[wall_id]['req'].result
                if len(resp['items']) == 0:
                    self.task_walls[wall_id]['empty'] = True
            msg = f'{self}\n'
            for wall_id in self.task_walls:
                if not self.task_walls[wall_id]['empty']:
                    resp = self.task_walls[wall_id]['req'].result
                    # If post is new
                    if resp['items'][0]['id'] > self.task_walls[wall_id]['wall'].last_id:
                        new_post = True
                        post_embed = compile_post_embed(resp)
                        for sub in self.task_walls[wall_id]['subs']:
                                dc_chn = self.cog.client.get_channel(sub.channel.id)
                                try:
                                    await dc_chn.send(content=sub.msg, embed=post_embed)
                                except Exception as exc:
                                    if isinstance(exc, AttributeError):
                                        sub.channel.delete()
                                    elif isinstance(exc, discord_errors.Forbidden):
                                        pass
                                    else:
                                        raise
                                else:
                                    msg += f'\t\t{sub}\n'
                        self.task_walls[wall_id]['wall'].last_id = resp['items'][0]['id']
                        msg += f'\t{self.task_walls[wall_id]["wall"]}\n'
                        async with aiopg.connect(sets["psqlUri"]) as conn:
                            async with conn.cursor(cursor_factory=DictCursor) as cur:
                                await cur.execute("UPDATE wall SET last_id = %s WHERE id = %s", (self.task_walls[wall_id]['wall'].last_id, self.task_walls[wall_id]['wall'].id))
            
            if new_post:
                self.cog.client.logger.info('Task {aa}USR{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=msg)))
            self.sleep_on_error = 30

        @repost_task.before_loop
        async def before_repost_task(self):
            await self.cog.client.wait_until_ready()
            self.task_walls = dict()
            self.task_subs = set()
            self.vk_pool = AsyncVkExecuteRequestPool()

        @repost_task.error
        async def error_repost_task(self, exc):
            await self.cog.client.error_handler('repost_task', usr=self, exc=exc)
            await asyncio.sleep(self.sleep_on_error)
            self.sleep_on_error += 30
            self.repost_task.restart()

        async def private_task(self):
            async with aiovk.TokenSession(self.token) as ses:
                long_poll = BotsLongPoll(ses, group_id=self.wall_id)
                async for event in long_poll.iter():
                    if event['type'] == 'wall_post_new':
                        async with aiovk.TokenSession(self.token) as ses:
                            vkapi = aiovk.API(ses)
                            post_embed = compile_post_embed(event['object'], await vkapi.groups.getById(group_id=self.wall_id, fields='photo_max'))

                        async with ClientSession() as session:
                            try: await discord.Webhook.from_url(url=self.channel.webhook_url, adapter=discord.AsyncWebhookAdapter(session)).send(embed=post_embed)
                            except discord_errors.NotFound as exc:
                                self.loop.create_task(self.channel.delete())
                            else:
                                msg = f'{self.channel.server}\n\t{self.channel}\n\t\t{self}\n\t\t\tRepost POST {wall["items"][0]["id"]}'
                                Server.client.logger.info('Repost {aa}POST{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=msg)))

    class Server: 
        all_ = set()
        temp_data = set()

        def __init__(self, cog, id_, lang):
            self.cog = cog
            self.id = id_
            self.lang = lang

            self.channels = set()
            Repost.Server.all_.add(self)
        
        def __str__(self):
            return f'SRV {self.id}'

        def Channel_init(self, id_):
            chn = Repost.Server.Channel(self, id_)
            msg = f'Init {chn}'
            return chn, msg

        async def Channel_add(self, id_):
            chn = Repost.Server.Channel(self, id_)
            msg = f'Add {chn}'
            async with aiopg.connect(sets["psqlUri"]) as conn:
                async with conn.cursor(cursor_factory=DictCursor) as cur:
                    await cur.execute("INSERT INTO channel (id, server_id) VALUES(%s, %s)", (
                        chn.id, chn.server.id))
            return chn, msg

        async def delete(self):
            msg = f'Del {self}'
            async with aiopg.connect(sets["psqlUri"]) as conn:
                async with conn.cursor(cursor_factory=DictCursor) as cur:
                    await cur.execute("DELETE FROM server WHERE id = %s", (self.id,))
            for chn in self.channels.copy():
                _msg = await chn.delete(is_called=True)
                msg += f'\n{_msg}'
            Repost.Server.all_.remove(self)
            return msg

        async def set_lang(self, lang):
            pass

        def eq_by_args(self, other_id):
            return self.id == other_id

        def find_channel(self, id_):
            chn, msg = None, str()
            for _chn in self.channels:
                if _chn.eq_by_args(id_):
                    chn = _chn
                    msg += f'{_chn}'
            return chn, msg
        
        @classmethod
        def find_by_args(cls, id_):
            srv, msg = None, str()
            for _srv in cls.all_:
                if _srv.eq_by_args(id_):
                    srv = _srv
                    msg += f'{_srv}'
                    break
            return srv, msg

        class Channel:
            all_ = set()

            def __init__(self, server, id_):
                self.server = server
                self.id = id_
                self.subscriptions = set()
                server.channels.add(self)

                Repost.Server.Channel.all_.add(self)
            
            def __str__(self):
                return f'CHN {self.id}'
            
            def Subscription_init(self, wall, user, msg, id_):
                """Initiates a subscription

                Args:
                    chn (Channel): Subscription's channel
                    wall (Wall): Subscription's wall_id
                    user (User): Subscription added by

                Returns:
                    Subscription: Subscription initiated
                    String: Message for logger
                """
                sub = Repost.Server.Channel.Subscription(self, wall, user, msg, id_)
                msg = f'Init {sub}'
                return sub, msg

            async def Subscription_add(self, wall, user, msg):
                """Creates a new Subscription

                Args:
                    chn (Channel): Channel which to subscribe
                    wall (Wall): Wall to subscribe
                    User (User): DiscordUser object

                Returns:
                    Subscription: Subscription added
                    String: Message for logger
                """
                if msg:
                    if len(msg) > 255:
                        raise MsgTooLong
                sub = Repost.Server.Channel.Subscription(self, wall, user, msg)
                async with aiopg.connect(sets["psqlUri"]) as conn:
                    async with conn.cursor(cursor_factory=DictCursor) as cur:
                        await cur.execute("INSERT INTO subscription (wall_id, users_id, channel_id, msg) VALUES(%s, %s, %s, %s) RETURNING id", (
                            sub.wall.id, sub.user.id, sub.channel.id, sub.msg))
                        sub.id = (await cur.fetchone())['id']
                msg = f'Add {sub}'
                return sub, msg

            async def delete(self, is_called=False):
                msg = f'Del {self}'
                for sub in self.subscriptions.copy():
                    _msg = await sub.delete(is_called=True)
                    msg += f'\n{_msg}'
                if is_called:
                    pass
                else:
                    async with ClientSession() as session:
                        try: await discord.Webhook.from_url(url=self.webhook_url, adapter=discord.AsyncWebhookAdapter(session)).delete()
                        except discord_errors.Forbidden as exc:
                            if exc.code == 50013:
                                raise commands.BotMissingPermissions(['manage_webhooks'])
                            raise
                        except discord_errors.NotFound as exc:
                            pass
                    async with aiopg.connect(sets["psqlUri"]) as conn:
                        async with conn.cursor(cursor_factory=DictCursor) as cur:
                            await cur.execute("DELETE FROM channel WHERE id = %s", (self.id,))
                self.server.channels.remove(self)
                Repost.Server.Channel.all_.remove(self)
                return msg

            def eq_by_args(self, other_id):
                return self.id == other_id

            def find_subs(self, id_, wall_type=False):
                subs, msg = list(), str()
                if not wall_type:
                    i = 0
                    for sub in self.subscriptions:
                        if abs(sub.wall.id) == abs(id_):
                            subs.append(sub)
                            msg += f'{sub}'
                            i += 1
                        if i == 2:
                            break
                else:
                    for sub in self.subscriptions:
                        if sub.wall.id == id_:
                            subs.append(sub)
                            msg += f'{sub}'
                            break
                return subs, msg

            @classmethod
            def find_by_args(cls, id_):
                chn, msg = None, str()
                for _chn in cls.all_:
                    if _chn.eq_by_args(id_):
                        chn = _chn
                        msg += f'{chn}'
                        break
                return chn, msg

            class Subscription:
                all_ = set()

                def __init__(self, channel, wall, user, msg, id_=None):
                    self.channel = channel
                    self.wall = wall
                    self.user = user
                    self.msg = msg
                    self.id = id_

                    channel.subscriptions.add(self)
                    wall.subscriptions.add(self)
                    user.subscriptions.add(self)
                    Repost.Server.Channel.Subscription.all_.add(self)
                
                def __str__(self):
                    return f'SUB {self.id}'

                async def delete(self, is_called=False):
                    msg = f'Del {self}'
                    if is_called:
                        pass
                    else:
                        async with aiopg.connect(sets["psqlUri"]) as conn:
                            async with conn.cursor(cursor_factory=DictCursor) as cur:
                                await cur.execute("DELETE FROM subscription WHERE channel_id = %s AND wall_id = %s", (
                                    self.channel.id, self.wall.id))
                    self.channel.subscriptions.remove(self)
                    self.wall.subscriptions.remove(self)
                    self.user.subscriptions.remove(self)
                    Repost.Server.Channel.Subscription.all_.remove(self)
                    return msg
                
                async def change_msg(self, new_msg):
                    if len(new_msg) > 255:
                        raise MsgTooLong
                    msg = f'Change msg {self}'
                    if new_msg == 'None':
                        new_msg = None
                    self.msg = new_msg
                    async with aiopg.connect(sets["psqlUri"]) as conn:
                        async with conn.cursor(cursor_factory=DictCursor) as cur:
                            await cur.execute("UPDATE subscription SET msg = %s WHERE id = %s", (
                                self.msg, self.id))
                    return msg


def setup(client):
    client.add_cog(Repost(client))