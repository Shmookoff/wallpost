from __future__ import annotations
from typing import Union, Optional

from discord.ext import commands, tasks
from discord import errors as discord_errors

import asyncio
import aiopg
from aiovk.pools import AsyncVkExecuteRequestPool, AsyncResult

from psycopg2.extras import DictCursor

from rsc.config import sets, vk_sets
from rsc.classes import SafeDict, VKRespWrapper
from rsc.exceptions import MsgTooLong


class Repost(commands.Cog):
    __name__ = 'Repost'

    def __init__(self, client: commands.Bot):
        Repost.client = client
        Repost.logger = client.logger

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


    def Wall_init(self, id_: int, public: bool, last_id: int) -> tuple[Repost.Wall, str]:
        return Repost.Wall.init(self.client, id_, public, last_id)
        
    async def Wall_add(self, id_: int, last_id: int) -> tuple[Repost.Wall, str]:
        return await Repost.Wall.add(self.client, id_, last_id)

    def User_init(self, id_: int, token: str) -> tuple[Repost.User, str]:
        return Repost.User.init(self.client, id_, token)

    async def User_add(self, id_: int) -> Repost.User:
        return await Repost.User.add(self.client, id_)

    def Server_init(self, id_: int, lang: str) -> Repost.Server:
        return Repost.Server.init(self.client, id_, lang)

    async def Server_add(self, id_: int) -> Repost.Server:
        return await Repost.Server.add(self.client, id_)

    class Wall:
        all_: set[Repost.Wall] = set()

        def __init__(self, id_: int, public: bool, last_id: int):
            self.id = id_
            self.public = public
            self.last_id = last_id

            self.subscriptions: set[Repost.Server.Channel.Subscription] = set()
            Repost.Wall.all_.add(self)

        def __str__(self):
            return f'WALL {self.id} PUB {self.public} LAST {self.last_id}'

        @classmethod
        async def add(cls, id_: int, last_id: int) -> Repost.Wall:
            self = cls(id_, True, last_id)
            msg = f'Add {self}'
            async with aiopg.connect(sets["psqlUri"]) as conn:
                async with conn.cursor(cursor_factory=DictCursor) as cur:
                    await cur.execute("INSERT INTO wall (id, public, last_id) VALUES(%s, %s, %s)", (
                        self.id, self.public, self.last_id))
            Repost.logger.info('Add {aa}WALL{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=msg)))
            return self

        async def delete(self):
            msg = f'Del {self}'
            async with aiopg.connect(sets["psqlUri"]) as conn:
                async with conn.cursor(cursor_factory=DictCursor) as cur:
                    await cur.execute("DELETE FROM wall WHERE id = %s", (self.id,))
            Repost.Wall.all_.remove(self)
            Repost.logger.info('Del {aa}WALL{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=msg)))

        def eq_by_args(self, other_id):
            return self.id == other_id

        @classmethod
        def find_by_args(cls, id_: int) -> Repost.Wall:
            wall = None
            for _wall in cls.all_:
                if _wall.eq_by_args(id_):
                    wall = _wall
                    break
            return wall

    class User:
        all_: set[Repost.User] = set()
        auth_data: list[dict] = list()

        def __init__(self, id_: int, token: str):
            self.id = id_
            self.token = token
            self.subscriptions: set[Repost.Server.Channel.Subscription] = set()

            Repost.User.all_.add(self)
            self.sleep_on_error = 30
            self.repost_task.start()

        def __str__(self):
            return f'USR {self.id}'

        @classmethod
        async def add(cls, id_: int) -> Repost.User:
            self = cls(id_, None)
            msg = f'Add {self}'
            async with aiopg.connect(sets["psqlUri"]) as conn:
                async with conn.cursor(cursor_factory=DictCursor) as cur:
                    await cur.execute("INSERT INTO users (id) VALUES(%s)", (self.id,))
            Repost.logger.info('Add {aa}USR{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=msg)))
            return self

        async def set_token(self, token: str):
            self.token = token
            msg = f'Set token {self}'
            async with aiopg.connect(sets["psqlUri"]) as conn:
                async with conn.cursor(cursor_factory=DictCursor) as cur:
                    await cur.execute("UPDATE users SET token = %s WHERE id = %s", (self.token, self.id))
            Repost.logger.info('Set token {aa}USR{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=msg)))

        def eq_by_args(self, other_id: int):
            return self.id == other_id
        
        @classmethod
        def find_by_args(cls, id_: int) -> Repost.User:
            usr = None
            for _usr in cls.all_:
                if _usr.eq_by_args(id_):
                    usr = _usr
                    break
            return usr
        
        @tasks.loop(seconds=60)
        async def repost_task(self):
            new_post = False
            # Check if subs changed
            if self.task_subs != self.subscriptions:
                self.task_subs = self.subscriptions.copy()
                self.task_walls = dict()
                for sub in self.task_subs:
                    if sub.wall.id not in self.task_walls:
                        self.task_walls[sub.wall.id] = {'wall_obj': sub.wall, 'subs': set(), 'post_REQ': None, 'post_RESP': None, 'ERR': None}
                    self.task_walls[sub.wall.id]['subs'].add(sub)
            # Req for posts
            for wall_id in self.task_walls:
                self.task_walls[wall_id]['post_REQ'] = self.vk_pool.add_call('wall.get', self.token, {
                    'owner_id': wall_id, 'extended': 1, 'count': 1, 'fields': 'photo_max', 'v': '5.84'})
            await self.vk_pool.execute()
            # Offset req for pinned posts
            for wall_id in self.task_walls:
                wall = self.task_walls[wall_id]
                if wall['post_REQ'].ok:
                    wall['post_RESP'] = wall['post_REQ'].result
                    if (len(wall['post_RESP']['items']) > 0) and (wall['post_RESP']['items'][0].get('is_pinned', False)):
                        wall['post_REQ'] = self.vk_pool.add_call('wall.get', self.token, {
                            'owner_id': wall_id, 'extended': 1, 'offset': 1, 'count': 1, 'fields': 'photo_max', 'v': '5.84'})
                else:
                    wall['ERR'] = wall['post_REQ'].error
            await self.vk_pool.execute()
            # Repost
            msg = f'{self}\n'
            for wall_id in self.task_walls:
                wall = self.task_walls[wall_id]
                if not wall['ERR']:
                    if wall['post_REQ'].ok:
                        resp = wall['post_REQ'].result
                        #Check if wall is not empty and post is new
                        if len(resp['items']) > 0 and resp['items'][0]['id'] > wall['wall_obj'].last_id:
                            new_post = True
                            wrapped = VKRespWrapper(post=resp, vk_info=self.client.vk_info)
                            #Send messages
                            msg += f'\t{wall["wall_obj"]}\n'
                            for sub in wall['subs']:
                                if not sub.channel.disabled:
                                    dc_chn = self.client.get_channel(sub.channel.id)
                                    try:
                                        await dc_chn.send(content=sub.msg, embed=wrapped.post_embed)
                                    except Exception as exc:
                                        if isinstance(exc, AttributeError):
                                            submsg = await sub.channel.delete(intents=2)
                                            msg += submsg
                                        elif isinstance(exc, discord_errors.Forbidden):
                                            bot_perms = dc_chn.permissions_for(dc_chn.guild.me)
                                            required_perms = {'send_messages': True, 'embed_links': True}
                                            missing_perms = [perm for perm, value in required_perms.items() if getattr(bot_perms, perm) != value]
                                            if missing_perms:
                                                missing = [perm.replace('_', ' ').replace('guild', 'server').title() for perm in missing_perms]
                                                if len(missing) > 2:
                                                    fmt = '{}, and {}'.format(", ".join(missing[:-1]), missing[-1])
                                                else:
                                                    fmt = ' and '.join(missing)

                                                users_id = set()
                                                for sub_ in sub.channel.subscriptions:
                                                    users_id.add(sub_.user.id)
                                                for user_id in users_id:
                                                    dc_user = self.client.get_user(user_id)
                                                    await dc_user.send(content=f"Couldn\'t repost to {dc_chn.mention} due to lack of permissions.\n" \
                                                        "Channel Subscriptions are temporarily disabled.\n" \
                                                        f"In order to enable them, give the Bot following permissions: `{fmt}`, and use `/subs manage` on the Channel.")
                                                sub.channel.disabled = True
                                            else:
                                                raise
                                        else:
                                            raise
                                    else:
                                        msg += f'\t\t{sub}\n'
                            wall['wall_obj'].last_id = wrapped.post['items'][0]['id']
                            async with aiopg.connect(sets["psqlUri"]) as conn:
                                async with conn.cursor(cursor_factory=DictCursor) as cur:
                                    await cur.execute("UPDATE wall SET last_id = %s WHERE id = %s", (
                                        wall['wall_obj'].last_id, wall['wall_obj'].id))
                    else:
                        wall['ERR'] = wall['post_REQ'].error

            if new_post:
                self.client.logger.info('Task {aa}USR{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=msg)))
            self.sleep_on_error = 30

        @repost_task.before_loop
        async def before_repost_task(self):
            await self.client.wait_until_ready()
            self.task_walls: dict[int, dict[str, Union[Repost.Wall, set, Optional[AsyncResult], Optional[dict], Optional[dict]]]] = dict()
            self.task_subs = set()
            self.vk_pool = AsyncVkExecuteRequestPool()

        @repost_task.error
        async def error_repost_task(self, exc):
            await self.client.error_handler('repost_task', usr=self, exc=exc)
            await asyncio.sleep(self.sleep_on_error)
            self.sleep_on_error += 30
            self.repost_task.restart()

    class Server: 
        all_: set[Repost.Server] = set()

        def __init__(self, id_: int, lang: str):
            self.id = id_
            self.lang = lang

            self.channels: set[Repost.Server.Channel] = set()
            Repost.Server.all_.add(self)
        
        def __str__(self):
            return f'SRV {self.id}'

        @classmethod
        async def add(cls, client: commands.Bot, id_: int) -> Repost.Server:
            self = cls(client, id_, "en")
            msg = f'Add {self}'
            async with aiopg.connect(sets["psqlUri"]) as conn:
                async with conn.cursor(cursor_factory=DictCursor) as cur:
                    await cur.execute("INSERT INTO server (id) VALUES(%s)", (self.id,))
            Repost.logger.info('Add {aa}SRV{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=msg)))
            return self

        async def Channel_add(self, id_: int) -> tuple[Repost.Server.Channel, str]:
            return await Repost.Server.Channel.add(self, id_, False)

        async def delete(self):
            msg = f'Del {self}'
            for chn in self.channels.copy():
                msg += f'\n\tDel {chn}'
                for sub in chn.subscriptions.copy():
                    msg += f'\n\tDel {sub}'
                    sub.channel.subscriptions.remove(sub)
                    sub.wall.subscriptions.remove(sub)
                    sub.user.subscriptions.remove(sub)
                    Repost.Server.Channel.Subscription.all_.remove(sub)
                self.channels.remove(chn)
                Repost.Server.Channel.all_.remove(chn)
            Repost.Server.all_.remove(self)
            async with aiopg.connect(sets["psqlUri"]) as conn:
                async with conn.cursor(cursor_factory=DictCursor) as cur:
                    await cur.execute("DELETE FROM server WHERE id = %s", (self.id,))
            Repost.logger.info('Del {aa}SRV{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=msg)))

        async def set_lang(self, lang: str):
            pass

        def eq_by_args(self, other_id: int):
            return self.id == other_id

        def find_channel(self, id_: int) -> Repost.Server.Channel:
            chn = None
            for _chn in self.channels:
                if _chn.eq_by_args(id_):
                    chn = _chn
            return chn
        
        @classmethod
        def find_by_args(cls, id_: int) -> Repost.Server:
            srv = None
            for _srv in cls.all_:
                if _srv.eq_by_args(id_):
                    srv = _srv
                    break
            return srv

        class Channel:
            all_: set[Repost.Server.Channel] = set()

            def __init__(self, server: Repost.Server, id_: int, disabled: bool):
                self.server = server
                self.id = id_
                self.disabled = disabled
                self.subscriptions: set[Repost.Server.Channel.Subscription] = set()
                server.channels.add(self)

                Repost.Server.Channel.all_.add(self)
            
            def __str__(self):
                return f'CHN {self.id}'

            @classmethod
            async def add(cls, server: Repost.Server, id_: int, disabled: bool) -> Repost.Server.Channel:
                self = cls(server, id_, disabled)
                msg = f'Add {self}'
                async with aiopg.connect(sets["psqlUri"]) as conn:
                    async with conn.cursor(cursor_factory=DictCursor) as cur:
                        await cur.execute("INSERT INTO channel (id, server_id) VALUES(%s, %s)", (
                            self.id, self.server.id))
                Repost.logger.info('Add {aa}CHN{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=msg)))
                return self

            async def Subscription_add(self, wall: Repost.Wall, user: Repost.User, msg: str) -> tuple[Repost.Server.Channel.Subscription, str]:
                return await Repost.Server.Channel.Subscription.add(self, wall, user, msg)

            async def delete(self):
                msg = f'{self.server}\n\tDel {self}'
                for sub in self.subscriptions.copy():
                    msg += f'\n\t\tDel {sub}'
                    sub.channel.subscriptions.remove(sub)
                    sub.wall.subscriptions.remove(sub)
                    sub.user.subscriptions.remove(sub)
                    Repost.Server.Channel.Subscription.all_.remove(sub)
                self.server.channels.remove(self)
                Repost.Server.Channel.all_.remove(self)
                async with aiopg.connect(sets["psqlUri"]) as conn:
                    async with conn.cursor(cursor_factory=DictCursor) as cur:
                        await cur.execute("DELETE FROM channel WHERE id = %s", (self.id,))
                Repost.logger.info('Del {aa}CHN{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=msg)))

            def eq_by_args(self, other_id: int):
                return self.id == other_id

            def find_subs(self, id_: int, wall_type: bool=False) -> tuple[list[Repost.Server.Channel.Subscription], str]:
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
            def find_by_args(cls, id_: int) -> tuple[Repost.Server.Channel, str]:
                chn, msg = None, str()
                for _chn in cls.all_:
                    if _chn.eq_by_args(id_):
                        chn = _chn
                        msg += f'{chn}'
                        break
                return chn, msg

            class Subscription:
                all_: set[Repost.Server.Channel.Subscription] = set()

                def __init__(self, channel: Repost.Server.Channel, wall: Repost.Wall, user: Repost.User, msg: str, id_: int=None):
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

                @classmethod
                def init(cls, channel: Repost.Server.Channel, wall: Repost.User, user: Repost.User, msg: str, id_: int) -> tuple[Repost.Server.Channel.Subscription, str]:
                    self = cls(channel, wall, user, msg, id_)
                    msg = f'Init {self}'
                    return self, msg

                @classmethod
                async def add(cls, channel: Repost.Server.Channel, wall: Repost.Wall, user: Repost.User, msg: str) -> tuple[Repost.Server.Channel.Subscription, str]:
                    if msg:
                        if len(msg) > 255:
                            raise MsgTooLong(msg)
                    sub = cls(channel, wall, user, msg)
                    async with aiopg.connect(sets["psqlUri"]) as conn:
                        async with conn.cursor(cursor_factory=DictCursor) as cur:
                            await cur.execute("INSERT INTO subscription (wall_id, users_id, channel_id, msg) VALUES(%s, %s, %s, %s) RETURNING id", (
                                sub.wall.id, sub.user.id, sub.channel.id, sub.msg))
                            sub.id = (await cur.fetchone())['id']
                    msg = f'Add {sub}'

                    return sub, msg

                async def delete(self):
                    msg = f'{self.channel.server}\n\t{self.channel}\n\t\tDel {self}'
                    self.channel.subscriptions.remove(self)
                    self.wall.subscriptions.remove(self)
                    self.user.subscriptions.remove(self)
                    Repost.Server.Channel.Subscription.all_.remove(self)
                    async with aiopg.connect(sets["psqlUri"]) as conn:
                        async with conn.cursor(cursor_factory=DictCursor) as cur:
                            await cur.execute("DELETE FROM subscription WHERE channel_id = %s AND wall_id = %s", (
                                self.channel.id, self.wall.id))
                    Repost.logger.info('Del {aa}SUB{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=msg)))
                
                async def change_msg(self, new_msg: str) -> str:
                    if len(new_msg) > 255:
                        raise MsgTooLong(new_msg)
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
    cog = Repost(client)
    client.add_cog(cog)