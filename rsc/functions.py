import discord
from discord.ext import commands

from dhooks import Webhook, Embed

import psycopg2
import asyncio
import aiohttp
from aiohttp.client_exceptions import ClientResponseError
from datetime import datetime

from aiovk.sessions import TokenSession
from aiovk.api import API as VKAPI
from aiovk.pools import AsyncVkExecuteRequestPool #!!!
from aiovk.longpoll import BotsLongPoll

from colorama import Fore, Style

from rsc.config import sets, vk_sets
from rsc.exceptions import subExists, WallClosed


#Subscription

def group_compile_embed(group):
    group_embed = discord.Embed(
        title = group['name'],
        url = f'https://vk.com/public{group["id"]}',
        color = sets["embedColor"]
    )
    group_embed.set_thumbnail(url = group['photo_200'])
    group_embed.add_field(
        name = 'Members',
        value = f'`{group["members_count"]}`',
        inline = True,
    )
    group_embed.add_field(
        name = 'Short address',
        value = f'`{group["screen_name"]}`',
        inline = True
    )
    if group['status'] != '':
        group_embed.add_field(
            name = 'Status',
            value = f'```{group["status"]}```',
            inline = False
        )
    if group['description'] != '':
        if len(group['description']) > 512:
            group_embed.add_field(
                name = 'Description',
                value = f'{group["description"][:512]}...',
                inline = False
            )
        else:
            group_embed.add_field(
                name = 'Description',
                value = f'{group["description"]}',
                inline = False
            )
    return group_embed
def user_compile_embed(user):
    user_embed = discord.Embed(
        title = f'{user["first_name"]} {user["last_name"]}',
        url = f'https://vk.com/id{user["id"]}',
        color = sets["embedColor"]
    )
    user_embed.set_thumbnail(url = user['photo_max'])
    user_embed.add_field(
        name = 'Friends',
        value = f'`{user["counters"]["friends"]}`',
        inline = True
    )
    user_embed.add_field(
        name = "Short address",
        value = f'`{user["screen_name"]}`',
        inline = True
    )
    if 'followers_count' in user:
        user_embed.add_field(
            name = 'Followers',
            value = f'`{user["followers_count"]}`',
            inline = True
        )
    if user['status'] != '':
        user_embed.add_field(
            name = 'Status',
            value = f'```{user["status"]}```',
            inline = False
        )
    return user_embed


#Repost

def compile_post_embed(post, vk, wall1=None):
    if wall1 is None:
        items = post['items'][0]
        embed = Embed(
            title = sets["embedTitle"],
            url = f'https://vk.com/wall{items["from_id"]}_{items["id"]}',
            description = items['text'],
            timestamp = datetime.utcfromtimestamp(items['date']).isoformat(),
            color = sets["embedColor"]
        )
        if items['owner_id'] > 0:
            author = post['profiles'][0]
            embed.set_author(
            name = f'{author["first_name"]} {author["last_name"]}',
            url = f'https://vk.com/id{author["id"]}',
            icon_url = author['photo_max']
            )
        else:
            author = post['groups'][0] 
            embed.set_author(
            name = author['name'],
            url = f'https://vk.com/club{author["id"]}',
            icon_url = author['photo_max']
            )
    else:
        items = post
        embed = Embed(
            title = sets["embedTitle"],
            url = f'https://vk.com/wall{items["from_id"]}_{items["id"]}',
            description = items['text'],
            timestamp = datetime.utcfromtimestamp(items['date']).isoformat(),
            color = sets["embedColor"]
        )
        embed.set_author(
            name = wall1[0]['name'],
            url = f'https://vk.com/club{wall1[0]["id"]}',
            icon_url = wall1[0]['photo_max']
        )
    
    has_photo = False
    if 'attachments' in items:                              
        for attachment in items['attachments']:             
            if 'photo' in attachment:                       
                has_photo = True                     
                hw = 0                                      
                image_url = ''                              
                for size in attachment['photo']['sizes']:   
                    if size['width']*size['height'] > hw:   
                        hw = size['width']*size['height']   
                        image_url = size['url']             
                embed.set_image(url = image_url)
                break

    if 'copy_history' in items: 
        copy = items['copy_history'][0]

        if copy['text'] != '':
            embed.add_field(
                name = '↪️ Repost',
                value = f'[**Open repost**](https://vk.com/wall{copy["from_id"]}_{copy["id"]})\n>>> {copy["text"]}'
            )
        else:
            embed.add_field(
                name = '↪️ Repost',
                value = f'[**Open repost**](https://vk.com/wall{copy["from_id"]}_{copy["id"]})'
            )
        
        if not has_photo:
            if 'attachments' in copy:                              
                for attachment in copy['attachments']:             
                    if 'photo' in attachment:                                        
                        hw = 0                                      
                        image_url = ''                              
                        for size in attachment['photo']['sizes']:   
                            if size['width']*size['height'] > hw:   
                                hw = size['width']*size['height']   
                                image_url = size['url']             
                        embed.set_image(url = image_url)
                        break

    embed.set_footer(text=vk['name'], icon_url=vk['photo'])

    return embed

async def repost(sub, vk):
    while True:
        async with TokenSession(sub.server.token) as ses:
            vkapi = VKAPI(ses)
            wall = await vkapi.wall.get(owner_id=sub.id, extended=1, count=1, fields='photo_max', v='5.130')
        if len(wall['items']) > 0:
            if 'is_pinned' in wall['items'][0]:
                if wall['items'][0]['is_pinned'] == 1:
                    async with TokenSession(sub.server.token) as ses:
                        vkapi = VKAPI(ses)
                        wall = await vkapi.wall.get(owner_id=sub.id, extended=1, offset=1, count=1, fields='photo_max', v='5.130')
            if len(wall['items']) > 0:
                if sub.last_post_id != wall['items'][0]['id']:
                    post_embed = compile_post_embed(wall, vk)

                    async with Webhook.Async(sub.channel.webhook_url) as webhook:
                        try: await webhook.send(embed=post_embed)
                        except ClientResponseError as e:
                            if e.status == 404:
                                with psycopg2.connect(sets["psqlUri"]) as dbcon:
                                    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                                        cur.execute("DELETE FROM channel WHERE id = %s", (sub.channel.id,))
                                
                                for subscription in sub.channel.subscriptions:
                                    if not subscription is sub:
                                        subscription.task.cancel()
                                        del subscription
                                    else: _task = subscription.task

                                print(f'Deleted {Fore.GREEN}CHANNEL {Fore.BLUE}{sub.channel.id} {Style.RESET_ALL}with {Fore.GREEN}WEBHOOK {Fore.BLUE}{sub.channel.webhook_url[33:51]}    {Fore.GREEN}SERVER {Fore.BLUE}{sub.server.id}{Style.RESET_ALL}')

                                del sub.channel, sub

                                _task.cancel()
                            else: 
                                print(e)
                        except Exception as e:
                            print(e)
                        else:
                            with psycopg2.connect(sets["psqlUri"]) as dbcon:
                                with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                                    cur.execute("UPDATE subscription SET last_post_id = %s WHERE channel_id = %s AND vk_id = @ %s AND vk_type = %s", (wall["items"][0]["id"], sub.channel.id, abs(sub.id), sub.type))
                            dbcon.close()
                            sub.last_post_id = wall['items'][0]['id']

                            print(f'Reposted {Fore.GREEN}POST {Fore.BLUE}{wall["items"][0]["id"]}    {Fore.GREEN}SERVER {Fore.BLUE}{sub.server.id} {Fore.GREEN}CHANNEL {Fore.BLUE}{sub.channel.id} {Fore.GREEN}WEBHOOK {Fore.BLUE}{sub.channel.webhook_url[33:51]}    {Fore.GREEN}WALL {Fore.BLUE}{sub.type}{abs(sub.id)} {Fore.GREEN}LONGPOLL {Fore.BLUE}{sub.longpoll}{Style.RESET_ALL}')
        await asyncio.sleep(60)

async def longpoll(sub, vk):
    async with TokenSession(sub.token) as ses:
        long_poll = BotsLongPoll(ses, group_id=sub.id)
        async for event in long_poll.iter():
            if event['type'] == 'wall_post_new':
                async with TokenSession(sub.token) as ses:
                    vkapi = VKAPI(ses)
                    post_embed = compile_post_embed(event['object'], vk, await vkapi.groups.getById(group_id=sub.id, fields='photo_max'))

                
                async with Webhook.Async(sub.channel.webhook_url) as webhook:
                    try: await webhook.send(embed=post_embed)
                    except ClientResponseError as e:
                        if e.status == 404:
                            with psycopg2.connect(sets["psqlUri"]) as dbcon:
                                with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                                    cur.execute("DELETE FROM channel WHERE id = %s", (sub.channel.id,))

                            for subscription in sub.channel.subscriptions:
                                if not subscription is sub:
                                    subscription.task.cancel()
                                    del subscription
                                else: _task = subscription.task

                            print(f'Deleted {Fore.GREEN}CHANNEL {Fore.BLUE}{sub.channel.id} {Style.RESET_ALL}with {Fore.GREEN}WEBHOOK {Fore.BLUE}{sub.channel.webhook_url[33:51]}    {Fore.GREEN}SERVER {Fore.BLUE}{sub.server.id}{Style.RESET_ALL}')

                            del sub.channel, sub

                            _task.cancel()
                        else: 
                            print(e)
                    except Exception as e:
                        print(e)
                    else:
                        print(f'Reposted {Fore.GREEN}POST {Fore.BLUE}{event["object"]["id"]}    {Fore.GREEN}SERVER {Fore.BLUE}{sub.server.id} {Fore.GREEN}CHANNEL {Fore.BLUE}{sub.channel.id} {Fore.GREEN}WEBHOOK {Fore.BLUE}{sub.channel.webhook_url[33:51]}    {Fore.GREEN}WALL {Fore.BLUE}{sub.type}{sub.id} {Fore.GREEN}LONGPOLL {Fore.BLUE}{sub.longpoll}{Style.RESET_ALL}')

class Server: 
    all = []
    temp_data = []

    def __init__(self, id, token):
        self.id = id
        self.token = token

        self.channels = []

        Server.all.append(self)

    @classmethod
    def init(cls, id, token):
        self = cls(id, token)
        print(f'Init {Fore.GREEN}SERVER {Fore.BLUE}{self.id}{Style.RESET_ALL}')
        return self

    @classmethod
    def add(cls, id):
        self = cls(id, None)
        with psycopg2.connect(sets["psqlUri"]) as dbcon:
            with dbcon.cursor() as cur:
                try:
                    cur.execute("INSERT INTO server (id) VALUES(%s)", (self.id,))
                except psycopg2.errors.UniqueViolation as e:
                    pass
        dbcon.close()
        print(f'\nAdd {Fore.GREEN}SERVER {Fore.BLUE}{self.id}{Style.RESET_ALL}\n')
        return self

    def delete(self):
        print(f'\nDel {Fore.GREEN}SERVER {Fore.BLUE}{self.id}{Style.RESET_ALL}')

        for channel in self.channels:
            print(f'    {Fore.GREEN}CHANNEL {Fore.BLUE}{channel.id}{Style.RESET_ALL} with {Fore.GREEN}WEBHOOK {Fore.BLUE}{channel.webhook_url[33:51]}{Style.RESET_ALL}')

            for sub in channel.subscriptions:
                print(f'        {Fore.GREEN}SUBSCRIPTION {Fore.BLUE}{sub.type}{abs(sub.id)} {Fore.GREEN}LONGPOLL {Fore.BLUE}{sub.longpoll}{Style.RESET_ALL}')

                Subscription.all.remove(sub)
                channel.subscriptions.remove(sub)
                sub.task.cancel()

                del sub

            Channel.all.remove(channel)
            self.channels.remove(channel)

            del channel
        print("")

        with psycopg2.connect(sets["psqlUri"]) as dbcon:
            with dbcon.cursor() as cur:
                cur.execute("DELETE FROM server WHERE id = %s", (self.id,))
        dbcon.close()

        Server.all.remove(self)
        del self

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

class Channel:
    all = []

    def __init__(self, server, id, webhook_url):
        self.server = server

        self.id = id
        self.webhook_url = webhook_url

        self.subscriptions = []
        server.channels.append(self)

        Channel.all.append(self)

    @classmethod
    def init(cls, server, id, webhook_url):
        self = cls(server, id, webhook_url)
        print(f'    Init {Fore.GREEN}CHANNEL {Fore.BLUE}{self.id}{Style.RESET_ALL} with {Fore.GREEN}WEBHOOK {Fore.BLUE}{self.webhook_url[33:51]}{Style.RESET_ALL}')
        return self

    @classmethod
    async def add(cls, server, discord_channel):
        webhook = await discord_channel.create_webhook(name="WallPost VK")
        self = cls(server, discord_channel.id, webhook.url)

        with psycopg2.connect(sets["psqlUri"]) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("INSERT INTO channel (id, webhook_url, server_id) VALUES(%s, %s, %s)", (self.id, self.webhook_url, self.server.id))
        dbcon.close()

        print(f'\n{Fore.GREEN}SERVER {Fore.BLUE}{self.server.id}{Style.RESET_ALL}')
        print(f'    Add {Fore.GREEN}CHANNEL {Fore.BLUE}{self.id}{Style.RESET_ALL} with {Fore.GREEN}WEBHOOK {Fore.BLUE}{self.webhook_url[33:51]}{Style.RESET_ALL}\n')
        
        return self

    async def delete(self):
        print(f'\n{Fore.GREEN}SERVER {Fore.BLUE}{self.server.id}{Style.RESET_ALL}')
        print(f'    Del {Fore.GREEN}CHANNEL {Fore.BLUE}{self.id}{Style.RESET_ALL} with {Fore.GREEN}WEBHOOK {Fore.BLUE}{self.webhook_url[33:51]}{Style.RESET_ALL}')

        with psycopg2.connect(sets["psqlUri"]) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                for sub in self.subscriptions:
                    print(f'        {Fore.GREEN}SUBSCRIPTION {Fore.BLUE}{sub.type}{abs(sub.id)} {Fore.GREEN}LONGPOLL {Fore.BLUE}{sub.longpoll}{Style.RESET_ALL}')
                    
                    cur.execute("DELETE FROM subscription WHERE channel_id = %s AND vk_id = %s AND vk_type = %s", (sub.channel.id, abs(sub.id), sub.type))

                    Subscription.all.remove(sub)
                    self.subscriptions.remove(sub)
                    sub.task.cancel()

                    del sub

                async with aiohttp.ClientSession() as session:
                    await discord.Webhook.from_url(url=self.webhook_url, adapter=discord.AsyncWebhookAdapter(session)).delete()

                cur.execute("DELETE FROM channel WHERE id = %s", (self.id,))
        dbcon.close()

        Channel.all.remove(self)
        self.server.channels.remove(self)
        print("")

        del self

    def find_subs(self, id, wall = None):
        if wall is None:
            subs = []
            i = 0
            for sub in self.subscriptions:
                if abs(sub.id) == abs(id):
                    subs.append(sub)
                    i += 1
                if i == 2:
                    break
            return subs
        else:
            for sub in self.subscriptions:
                if (abs(sub.id), sub.type) == (abs(id), wall):
                    return sub
        return None

    def eq_by_args(self, other_id):
        return self.id == other_id

    # @classmethod
    # def find_by_args(cls, id):
    #     for channel in cls.all:
    #         if channel.eq_by_args(id):
    #             return channel
    #     return None

class Subscription:
    all = []

    def __init__(self, channel, info, vk, loop):
        self.server = channel.server
        self.channel = channel

        self.id = info['vk_id']
        self.type = info['vk_type']
        self.longpoll = info['long_poll']
        self.last_post_id = info['last_post_id']
        self.token = info['token']

        if info['long_poll'] == False: 
            if self.type == 'g': self.id = -self.id
            self.task = loop.create_task(repost(self, vk))
        else:
            self.task = loop.create_task(longpoll(self, vk))

        channel.subscriptions.append(self)

        Subscription.all.append(self)

    @classmethod
    def init(cls, channel, info, vk, loop):
        self = cls(channel, info, vk, loop)
        print(f'        Init {Fore.GREEN}SUBSCRIPTION {Fore.BLUE}{self.type}{abs(self.id)} {Fore.GREEN}LONGPOLL {Fore.BLUE}{self.longpoll}{Style.RESET_ALL}')
        return self

    @classmethod
    def add(cls, channel, info, vk, loop):
        self = cls(channel, info, vk, loop)

        with psycopg2.connect(sets["psqlUri"]) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("INSERT INTO subscription (vk_id, vk_type, long_poll, last_post_id, channel_id) VALUES(%s, %s, %s, %s, %s)", (abs(self.id), self.type, self.longpoll, self.last_post_id, self.channel.id))
        dbcon.close()

        print(f'\n{Fore.GREEN}SERVER {Fore.BLUE}{self.server.id}{Style.RESET_ALL}')
        print(f'    {Fore.GREEN}CHANNEL {Fore.BLUE}{self.channel.id}{Style.RESET_ALL} with {Fore.GREEN}WEBHOOK {Fore.BLUE}{self.channel.webhook_url[33:51]}{Style.RESET_ALL}')
        print(f'        Add {Fore.GREEN}SUBSCRIPTION {Fore.BLUE}{self.type}{abs(self.id)} {Fore.GREEN}LONGPOLL {Fore.BLUE}{self.longpoll}{Style.RESET_ALL}\n')

        return self

    def delete(self):
        print(f'\n{Fore.GREEN}SERVER {Fore.BLUE}{self.server.id}{Style.RESET_ALL}')
        print(f'    {Fore.GREEN}CHANNEL {Fore.BLUE}{self.channel.id}{Style.RESET_ALL} with {Fore.GREEN}WEBHOOK {Fore.BLUE}{self.channel.webhook_url[33:51]}{Style.RESET_ALL}')
        print(f'        Del {Fore.GREEN}SUBSCRIPTION {Fore.BLUE}{self.type}{abs(self.id)} {Fore.GREEN}LONGPOLL {Fore.BLUE}{self.longpoll}{Style.RESET_ALL}\n')

        with psycopg2.connect(sets["psqlUri"]) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("DELETE FROM subscription WHERE channel_id = %s AND vk_id = %s AND vk_type = %s", (self.channel.id, abs(self.id), self.type))
        dbcon.close()

        Subscription.all.remove(self)
        self.channel.subscriptions.remove(self)
        self.task.cancel()

        del self

    # def eq_by_args(self, other_channel, other_id, other_wall):
    #     return self.channel.eq_by_args(other_channel.id) and (abs(self.id), self.type) == (abs(other_id), other_wall)

    # @classmethod
    # def find_by_args(cls, channel: Channel, id: int, wall: str = None):
    #     if wall is None:
    #         subs = []

    #         for subscription in cls.all:
    #             if subscription.eq_by_args(channel, id, type):
    #                 return subscription
    #     else:
    #         for subscription in cls.all:
    #             if subscription.eq_by_args(channel, id, type):
    #                 return subscription
    #         return None


#Staff

def get_prefix(client, message):
    with psycopg2.connect(sets["psqlUri"]) as dbcon:
        with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(f"SELECT prefix FROM server WHERE id = {message.guild.id}")
            prefix = cur.fetchone()['prefix']
        dbcon.close

    if prefix == None: 
        return '.'
    else: 
        return prefix

async def get_vk_info():
    async with TokenSession(vk_sets["serviceKey"]) as ses:
        vkapi = VKAPI(ses)
        vk_info = await vkapi.groups.getById(group_id=22822305, v='5.130')
    return {'name': vk_info[0]['name'], 'photo': vk_info[0]['photo_200']}


#Errors

def set_error_embed(d):
    return discord.Embed(title=sets["errorTitle"], color=sets["errorColor"], description=d)

def add_command_and_example(ctx, error_embed, command, example):
    error_embed.add_field(
        name = 'Command',
        value = command,
        inline = False
    )
    error_embed.add_field(
        name = 'Example',
        value = example,
        inline = False
    )
