import discord
from discord.ext import commands, ipc

import asyncio
import aiopg
import aiovk
from aiovk.exceptions import VkAPIError

from psycopg2.extras import DictCursor

import texttable
from cryptography.fernet import Fernet

from rsc.config import sets
from rsc.functions import user_compile_embed, add_command_and_example, group_compile_embed, set_error_embed, vk
from rsc.classes import Server, Channel, Subscription
from rsc.exceptions import *


class Subscriptions(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.loop = client.loop
        self.loop.create_task(self.ainit())

    async def ainit(self):
        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("SELECT id, prefix, lang, token FROM server")
                srvs = await cur.fetchall()
                await cur.execute("SELECT id, webhook_url, server_id FROM channel")
                chns = await cur.fetchall()
                await cur.execute("SELECT vk_id, vk_type, long_poll, last_post_id, token, channel_id FROM subscription")
                subs = await cur.fetchall()

                for srv in srvs:
                    _srv = Server.init(srv['id'], srv['prefix'], srv['lang'], srv['token'])

                    for chn in chns:
                        if chn['server_id'] == _srv.id:
                            _chn = Channel.init(_srv, chn['id'], chn['webhook_url'])

                            for sub in subs:
                                if sub['channel_id'] == _chn.id:
                                    _sub = Subscription.init(_chn, {
                                        'vk_id': sub['vk_id'], 'vk_type': sub['vk_type'], 'long_poll': sub['long_poll'], 'last_post_id': sub['last_post_id'], 'token': sub['token']
                                    })

                    print()

                del srvs, chns, subs


    @commands.group(aliases=['subscriptions', 's'], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def sub(self, ctx):
        vk_token = Server.find_by_args(ctx.guild.id).token
        if vk_token is None:
            await self.sub_set(ctx)
        else:
            async with aiovk.TokenSession(vk_token) as ses:
                vkapi = aiovk.API(ses)
                user_embed = user_compile_embed((await vkapi.users.get(fields='photo_max,status,screen_name,followers_count,counters', v='5.130'))[0])
            await ctx.send(f'**{ctx.guild.name}** is bound to this account.\nYou can change it with `sub set` command.', embed=user_embed)
        
    @sub.error
    async def sub_error(self, ctx, exc):
        pass

    @sub.command(aliases=['set', 's'])
    @commands.has_permissions(administrator=True)
    async def sub_set(self, ctx):
        key = Fernet.generate_key().decode("utf-8")
        Server.temp_data.append({"key": key, "server_id": ctx.guild.id, "channel_id": ctx.channel.id})
        embed = discord.Embed(
            title = 'Authentication',
            url = f'{sets["url"]}/oauth2/login?key={key}',
            description = 'Authenticate with your VK profile to be able to use **WallPost VK**.',
            color = sets["embedColor"]
        )
        embed.set_thumbnail(url=vk['photo'])
        embed.set_footer(text=vk['name'], icon_url=vk['photo'])

        await ctx.send('Check your DM for an authentication link!')
        await ctx.author.send(embed=embed)

    @sub_set.error
    async def sub_set_error(self, ctx, exc):
        pass

    @sub.command(aliases=['add', 'a'])
    @commands.bot_has_permissions(manage_webhooks=True, add_reactions=True, manage_messages=True, read_message_history=True, send_messages=True)
    @commands.has_permissions(manage_webhooks=True)
    async def sub_add(self, ctx, vk_id: str=None, channel: discord.TextChannel=None):
        vk_token = Server.find_by_args(ctx.guild.id).token
        if vk_token is None: raise NotAuthenticated
        if vk_id is None: raise VkIdNotSpecified
        if vk_id == '0': raise VkWallBlocked
        if channel is None: channel = ctx.channel
        if len(await channel.webhooks()) == 10: raise MaximumWebhooksReached
        ctx.webhook_channel = channel
        messages = []


        async with aiovk.TokenSession(vk_token) as ses:
            vkapi = aiovk.API(ses)

            try:
                groupi = await vkapi.groups.getById(group_id=vk_id, fields="status,description,members_count", v='5.130')
                if groupi[0]['is_closed'] == 1 and not 'is_member' in groupi[0]:
                    groupi = [{'deactivated': True}]
            except VkAPIError as exc:
                if exc.error_code == 100:
                    groupi = [{'deactivated': True}]
            
            try:
                useri = await vkapi.users.get(user_ids=vk_id, fields='photo_max,status,screen_name,followers_count,counters', v='5.130')
            except VkAPIError as exc:
                if exc.error_code == 113:
                    useri = [{'deactivated': True}]

        if not 'deactivated' in groupi[0] and not 'deactivated' in useri[0]:
            group_embed = group_compile_embed(groupi[0])
            user_embed = user_compile_embed(useri[0])

            messages.append(await ctx.send(embed=group_embed))
            messages.append(await ctx.send('React with ⬆️ for **group** wall\nReact with ❌ for cancel\nReact with ⬇️ for **user** wall'))
            messages.append(await ctx.send(embed=user_embed))

            for emoji in ['⬆️', '❌', '⬇️']:
                await messages[1].add_reaction(emoji)
            
            try:
                r, u = await self.client.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message == messages[1] and r.emoji in ['⬆️', '❌', '⬇️'], timeout=120.0)
            except asyncio.TimeoutError:
                await ctx.channel.delete_messages(messages)
                messages.clear()
                await ctx.send('❌ Cancelled (timeout)')
            else:
                await ctx.channel.delete_messages(messages)
                messages.clear()

                if r.emoji == '⬆️':
                    await self.setup_wall(ctx, 'add', messages, channel, 'g', groupi[0], group_embed)

                elif r.emoji == '⬇️':
                    await self.setup_wall(ctx, 'add', messages, channel, 'u', useri[0], user_embed)

                else:
                    await ctx.send('❌ Cancelled')

        elif not 'deactivated' in groupi[0]:
            await self.setup_wall(ctx, 'add', messages, channel, 'g', groupi[0], group_compile_embed(groupi[0]))

        elif not 'deactivated' in useri[0]:
            await self.setup_wall(ctx, 'add', messages, channel, 'u', useri[0], user_compile_embed(useri[0]))

        else: raise VkWallBlocked

    @sub_add.error
    async def sub_add_error(self, ctx, exc):
        if isinstance(exc, commands.CommandInvokeError):
            _exc = exc.original

            if isinstance(_exc, MaximumWebhooksReached):
                exc.embed = set_error_embed(f'Maximum number of webhooks reached (10).\n> Try removing a webhook from {ctx.webhook_channel.mention}.')
            elif isinstance(_exc, WallClosed):
                exc.embed = set_error_embed(f'Wall is closed\n\n> Your VK account doesn\'t have access to this closed wall.')
            elif isinstance(_exc, SubExists):
                exc.embed = set_error_embed(f'{ctx.webhook_channel.mention} is already subscribed to this wall.')

    @sub.command(aliases=['information', 'info', 'i'])
    @commands.bot_has_permissions(send_messages=True)
    @commands.has_permissions(manage_webhooks=True)
    async def sub_info(self, ctx, channel: discord.TextChannel=None):
        vk_token = Server.find_by_args(ctx.guild.id).token
        if vk_token == None: raise NotAuthenticated
        if channel == None: channel = ctx.channel
        ctx.webhook_channel = channel

        chn = Server.find_by_args(ctx.guild.id).find_channel(channel.id)
        if chn is None:
            raise NoSubs
        else:
            subs = chn.subscriptions
        if len(subs) == 0: raise NoSubs

        embed = discord.Embed(
            title = f'Wall subscriptions',
            description = f'**for **{channel.mention}** channel:**',
            color = sets["embedColor"]
        )
        table = texttable.Texttable(max_width=0)
        table.set_cols_align(['c','c','c','c'])
        table.header(['Name', 'Short address', 'Type', 'ID'])
        table.set_cols_dtype(['t','t','t','i'])
        table.set_chars(['─','│','┼','─'])

        groups, users = '', ''
        for sub in subs:
            if sub.type == 'g': groups += f"{sub.id},"
            else: users += f"{sub.id},"
        async with aiovk.TokenSession(vk_token) as ses:
            vkapi = aiovk.API(ses)
            if groups != '':
                r_groups = await vkapi.groups.getById(group_ids=groups, v='5.130')

                for wall in r_groups:
                    name = f"{wall['name']}"
                    type = 'Group'

                    table.add_row([name, wall['screen_name'], type, wall['id']])
                    embed.add_field(
                        name = name,
                        value = f"Short address: `{wall['screen_name']}`\nType: `{type}`\nID: `{wall['id']}`",
                        inline = True
                    )
            if users != '':
                r_users = await vkapi.users.get(user_ids=users, fields='screen_name', v='5.130')

                for wall in r_users:
                    name = f"{wall['first_name']} {wall['last_name']}"
                    type = 'User'

                    table.add_row([name, wall['screen_name'], type, wall['id']])
                    embed.add_field(
                        name = name,
                        value = f"Short address: `{wall['screen_name']}`\nType: `{type}`\nID: `{wall['id']}`",
                        inline = True
                    )

        await ctx.send(f"**Wall subscriptions for **{channel.mention}** channel:**\n```{table.draw()}```", embed=embed)

    @sub_info.error
    async def sub_info_error(self, ctx, exc):
        if isinstance(exc, commands.ChannelNotFound) or isinstance(exc, commands.BadArgument):
            exc.embed = set_error_embed(f'Channel is not found.\n\n> Please, pass in `[Channel Mention]` as **Channel Mention** from current server.')
            exc.command_and_example = True
        elif isinstance(exc, commands.CommandInvokeError):
            _exc = exc.original
            
            if isinstance(_exc, NoSubs):
                exc.embed = set_error_embed(f'{ctx.webhook_channel.mention} doesn\'t have any subscriptions.')

    @sub.command(aliases=['delete', 'del', 'd'])
    @commands.bot_has_permissions(manage_webhooks=True, add_reactions=True, manage_messages=True, read_message_history=True, send_messages=True)
    @commands.has_permissions(manage_webhooks=True)
    async def sub_del(self, ctx, vk_id: str=None, webhook_channel: discord.TextChannel=None):
        vk_token = Server.find_by_args(ctx.guild.id).token
        if vk_token == None: raise NotAuthenticated
        if vk_id == None: raise VkIdNotSpecified
        if vk_id == 0: raise VkWallBlocked
        if webhook_channel == None: webhook_channel = ctx.channel
        ctx.webhook_channel = webhook_channel
        chn = Server.find_by_args(ctx.guild.id).find_channel(webhook_channel.id)
        if chn is None: raise NotSub
        messages = []


        async with aiovk.TokenSession(vk_token) as ses:
            vkapi = aiovk.API(ses)

            try: groupi = await vkapi.groups.getById(group_id=vk_id, fields="status,description,members_count", v='5.130')
            except VkAPIError as exc:
                if exc.error_code == 100:
                    groupi = [{'deactivated': True}]

            try: useri = await vkapi.users.get(user_ids=vk_id, fields='photo_max,status,screen_name,followers_count,counters', v='5.130')
            except VkAPIError as exc:
                if exc.error_code == 113:
                    useri = [{'deactivated': True}]

        if not 'deactivated' in groupi[0] and not 'deactivated' in useri[0]:
            subs = chn.find_subs(groupi[0]['id'])
            if len(subs) == 0: raise NotSub

            elif len(subs) == 2:
                group_embed = group_compile_embed(groupi[0])
                user_embed = user_compile_embed(useri[0])

                messages.append(await ctx.send(embed=group_embed))
                messages.append(await ctx.send('React with ⬆️ for **group** wall\nReact with ❌ for cancel\nReact with ⬇️ for **user** wall'))
                messages.append(await ctx.send(embed=user_embed))

                for emoji in ['⬆️', '❌', '⬇️']:
                    await messages[1].add_reaction(emoji)
                
                try:
                    r, u = await self.client.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message == messages[1] and r.emoji in ['⬆️', '❌', '⬇️'], timeout=120.0)
                except asyncio.TimeoutError:
                    await ctx.channel.delete_messages(messages)
                    messages.clear()
                    await ctx.send('❌ Cancelled (timeout)')
                else:
                    await ctx.channel.delete_messages(messages)
                    messages.clear()

                    if r.emoji == '⬆️':
                        await self.setup_wall(ctx, 'del', messages, webhook_channel, 'g', groupi[0], group_embed)

                    elif r.emoji == '⬇️':
                        await self.setup_wall(ctx, 'del', messages, webhook_channel, 'u', useri[0], user_embed)

                    else:
                        await ctx.send('❌ Cancelled')
            
            elif len(subs) == 1:
                if subs[0].type == 'g':
                    wall_embed = group_compile_embed(groupi[0])
                    walli = groupi[0]
                elif subs[0].type == 'u': 
                    wall_embed = user_compile_embed(useri[0])
                    walli = useri[0]
                await self.setup_wall(ctx, 'del', messages, webhook_channel, subs[0].type, walli, wall_embed)

        elif not 'deactivated' in groupi[0]:
            subs = chn.find_subs(groupi[0]['id'])
            if len(subs) == 0: raise NotSub

            await self.setup_wall(ctx, 'del', messages, webhook_channel, 'g', groupi[0], group_compile_embed(groupi[0]))

        elif not 'deactivated' in useri[0]:
            subs = chn.find_subs(groupi[0]['id'])
            if len(subs) == 0: raise NotSub

            await self.setup_wall(ctx, 'del', messages, webhook_channel, 'u', useri[0], user_compile_embed(useri[0]))

        else: raise VkWallBlocked

    @sub_del.error
    async def sub_del_error(self, ctx, exc):
        if isinstance(exc, commands.CommandInvokeError):
            _exc = exc.original

            if isinstance(_exc, NotSub):
                exc.embed = set_error_embed(f'{ctx.webhook_channel.mention} isn\'t subscribed to wall **{ctx.args[2]}**.')

    async def setup_wall(self, ctx, action, messages, channel, wall, walli, embed):
        messages.append(await ctx.send(f'Is this the wall you requested?\nReact with ✅ or ❌', embed=embed))

        for emoji in ['✅', '❌']:
            await messages[0].add_reaction(emoji)

        try:
            r, u = await ctx.bot.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message == messages[0] and r.emoji in ['✅', '❌'], timeout=120.0)
        except asyncio.TimeoutError:
            await ctx.channel.delete_messages(messages)
            messages.clear()
            await ctx.send('❌ Cancelled (timeout)')
        else:
            if r.emoji == '✅':
                await ctx.channel.delete_messages(messages)
                messages.clear()

                if wall == "g":
                    name = walli['name']
                    if not walli['is_closed'] == 0 and walli['is_member'] == 0:
                        raise WallClosed
                elif wall == "u":
                    name = f'{walli["first_name"]} {walli["last_name"]}'
                    if walli['can_access_closed'] == False:
                        raise WallClosed
                
                if action == 'add':
                    _channel = Server.find_by_args(ctx.guild.id).find_channel(channel.id)
                    long_poll = False
                    if wall == 'g':
                        if walli['is_admin'] == 1:
                            if walli['admin_level'] == 3:
                                messages.append(await ctx.send(f'You are the administrator of **{name}**. You can enable \"long-poll\" reposting.\nThis means bla bla bla WIP'))
                                # vkapi.groups.setLongPollSettings(enabled=1, wall_post_new=1, v='5.130')
                                # long_poll = True

                    if _channel is None:
                        _channel = await Channel.add(Server.find_by_args(ctx.guild.id), channel, {'vk_id': abs(walli['id']), 'vk_type': wall, 'long_poll': long_poll, 'last_post_id': 0, 'token': None})

                    elif _channel.find_subs(walli['id'], wall) is None:
                        _sub = await Subscription.add(_channel, {'vk_id': abs(walli['id']), 'vk_type': wall, 'long_poll': long_poll, 'last_post_id': 0, 'token': None})
                        
                    else: raise SubExists

                    await ctx.send(f'✅ Successfully subscribed {channel.mention} to **{name}** wall!')

                if action == 'del':
                    await Server.find_by_args(ctx.guild.id).find_channel(channel.id).find_subs(walli['id'], wall).delete()

                    await ctx.send(f'✅ Successfully unsubscrubed {channel.mention} from **{name}** wall!')

            elif r.emoji == '❌':
                await ctx.channel.delete_messages(messages)
                messages.clear()
                await ctx.send('❌ Cancelled')

    @ipc.server.route()
    async def authentication(self, data):
        try:
            temp_data = list(filter(lambda temp_data: temp_data['key'] == data.key, Server.temp_data))[0]
        except IndexError:
            return "This link has been expired. Get a new one with `sub set` command."

        server = Server.find_by_args(temp_data['server_id'])
        await server.set_token(data.token)

        async with aiovk.TokenSession(server.token) as ses:
            vkapi = aiovk.API(ses)
            await (self.client.get_channel(temp_data['channel_id']).send(f"**{self.client.get_guild(server.id).name}** is now bound to this account.\nYou can change it with `sub set` command.", embed = user_compile_embed((await vkapi.users.get(fields='photo_max,status,screen_name,followers_count,counters', v='5.130'))[0])))

        Server.temp_data.remove(temp_data)

        return 'Your account is now bound to the server. You can now close this tab.'


name = 'Subscriptions'

def setup(client):
    print(f'Load COG {name}')
    cog = Subscriptions(client)
    client.add_cog(cog)

def teardown(client):
    print(f'Unload COG {name}')
    Server.uninit_all()
    client.remove_cog(name)