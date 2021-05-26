import discord
from discord.errors import Forbidden as DiscordForbidden
from discord.ext import commands, ipc
from discord_slash import cog_ext
from discord_slash.utils.manage_commands import create_option, create_choice

import asyncio
import aiopg
import aiovk
from aiovk.exceptions import VkAPIError

from psycopg2.extras import DictCursor

import texttable
from cryptography.fernet import Fernet

from rsc.config import sets
from rsc.functions import user_compile_embed, add_command_and_example, group_compile_embed, vk
from rsc.classes import Server, Channel, Subscription
from rsc.exceptions import *


class Subscriptions(commands.Cog):
    __name__ = 'Subscriptions Command'

    def __init__(self, client):
        print(f'Load COG {self.__name__}')

        self.client = client
        self.loop = client.loop
        self.loop.create_task(self.ainit())

    def cog_unload(self):
        print(f'Unload COG {self.__name__}')
        Server.uninit_all()


    async def ainit(self):
        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("SELECT id, lang, token FROM server")
                srvs = await cur.fetchall()
                await cur.execute("SELECT id, webhook_url, server_id FROM channel")
                chns = await cur.fetchall()
                await cur.execute("SELECT vk_id, vk_type, long_poll, last_post_id, token, channel_id FROM subscription")
                subs = await cur.fetchall()

                for srv in srvs:
                    _srv = Server.init(srv['id'], srv['lang'], srv['token'])

                    for chn in chns:
                        if chn['server_id'] == _srv.id:
                            _chn = Channel.init(_srv, chn['id'], chn['webhook_url'])

                            for sub in subs:
                                if sub['channel_id'] == _chn.id:
                                    _sub = Subscription.init(_chn, {
                                        'vk_id': sub['vk_id'], 'vk_type': sub['vk_type'], 'long_poll': sub['long_poll'], 'last_post_id': sub['last_post_id'], 'token': sub['token']
                                    })
                del srvs, chns, subs
        print()


    @cog_ext.cog_subcommand(name='add',
                            base='subs',
                            description='Subscribe Channel to VK Wall',
                            options=[create_option(
                                name='wall_id',
                                description='Can be both VK Wall ID and Short-name',
                                option_type=3,
                                required=True
                            ), create_option(
                                name='channel',
                                description='Default: current Channel',
                                option_type=7,
                                required=False
                            )])
    @commands.bot_has_permissions(manage_webhooks=True, add_reactions=True, manage_messages=True, read_message_history=True, send_messages=True)
    @commands.has_permissions(manage_webhooks=True)
    async def sub_add(self, ctx, wall_id, channel=None):
        vk_token = Server.find_by_args(ctx.guild.id).token
        if vk_token is None:
            raise NotAuthenticated
        if wall_id.startswith('<') and wall_id.endswith('>'):
            raise WallIdBadArgument
        elif wall_id == '0':
            raise VkWallBlocked
        if channel is None:
            channel = ctx.channel
        ctx.webhook_channel = channel
        try:
            if len(await channel.webhooks()) == 10:
                raise MaximumWebhooksReached
        except DiscordForbidden as exc:
            raise ChannelForbiddenWebhooks


        async with aiovk.TokenSession(vk_token) as ses:
            vkapi = aiovk.API(ses)

            try:
                groupi = await vkapi.groups.getById(group_id=wall_id, fields="status,description,members_count", v='5.130')
                if groupi[0]['is_closed'] == 1 and not 'is_member' in groupi[0]:
                    groupi = [{'deactivated': True}]
            except VkAPIError as exc:
                if exc.error_code == 100:
                    groupi = [{'deactivated': True}]
            
            try:
                useri = await vkapi.users.get(user_ids=wall_id, fields='photo_max,status,screen_name,followers_count,counters', v='5.130')
            except VkAPIError as exc:
                if exc.error_code == 113:
                    useri = [{'deactivated': True}]

        if not 'deactivated' in groupi[0] and not 'deactivated' in useri[0]:
            group_embed = group_compile_embed(groupi[0])
            user_embed = user_compile_embed(useri[0])

            ctx.msg = await ctx.send(content='React with\n\t:one: for **first** wall\n\t:two: for **second** wall,\n\t❌ for cancel.', embeds=[group_embed, user_embed])
            for emoji in ['1️⃣', '2️⃣', '❌']:
                await ctx.msg.add_reaction(emoji)
            
            try:
                r, u = await self.client.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message.id == ctx.msg.id and r.emoji in ['1️⃣', '❌', '2️⃣'], timeout=120.0)
            except asyncio.TimeoutError:
                await ctx.msg.clear_reactions()
                await ctx.msg.edit(content='❌ Cancelled (timeout)', embed=None)
            else:
                await ctx.msg.clear_reactions()

                if r.emoji == '1️⃣':
                    await self.setup_wall(ctx, 'add', channel, 'g', groupi[0], group_embed)
                elif r.emoji == '2️⃣':
                    await self.setup_wall(ctx, 'add', channel, 'u', useri[0], user_embed)
                else:
                    await ctx.msg.edit(content='❌ Cancelled', embed=None)

        elif not 'deactivated' in groupi[0]:
            await self.setup_wall(ctx, 'add', channel, 'g', groupi[0], group_compile_embed(groupi[0]))

        elif not 'deactivated' in useri[0]:
            await self.setup_wall(ctx, 'add', channel, 'u', useri[0], user_compile_embed(useri[0]))

        else: raise VkWallBlocked

    @cog_ext.cog_subcommand(name='info',
                            base='subs',
                            description='Show all Subscriptions for Channel',
                            options=[create_option(
                                name='channel',
                                description='Default: current Channel',
                                option_type=7,
                                required=False
                            )])
    @commands.bot_has_permissions(send_messages=True)
    @commands.has_permissions(manage_webhooks=True)
    async def sub_info(self, ctx, channel=None):
        vk_token = Server.find_by_args(ctx.guild.id).token
        if vk_token is None:
            raise NotAuthenticated
        if channel is None:
            channel = ctx.channel
        ctx.webhook_channel = channel

        chn = Server.find_by_args(ctx.guild.id).find_channel(channel.id)
        if chn is None:
            raise NoSubs
        subs = chn.subscriptions

        if len(subs) == 0:
            raise NoSubs

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

    @cog_ext.cog_subcommand(name='del',
                            base='subs',
                            description='Unsubscribe Channel from VK Wall',
                            options=[create_option(
                                name='wall_id',
                                description='Can be both VK Wall ID and Short-name',
                                option_type=3,
                                required=True
                            ),create_option(
                                name='channel',
                                description='Default: current Channel',
                                option_type=7,
                                required=False
                            )])
    @commands.bot_has_permissions(manage_webhooks=True, add_reactions=True, manage_messages=True, read_message_history=True, send_messages=True)
    @commands.has_permissions(manage_webhooks=True)
    async def sub_del(self, ctx, wall_id, channel=None):
        vk_token = Server.find_by_args(ctx.guild.id).token
        if vk_token == None:
            raise NotAuthenticated
        if wall_id.startswith('<') and wall_id.endswith('>'):
            raise WallIdBadArgument
        elif wall_id == '0':
            raise VkWallBlocked
        if channel is None:
            channel = ctx.channel
        ctx.webhook_channel = channel
        chn = Server.find_by_args(ctx.guild.id).find_channel(channel.id)
        if chn is None:
            raise NotSub


        async with aiovk.TokenSession(vk_token) as ses:
            vkapi = aiovk.API(ses)

            try: groupi = await vkapi.groups.getById(group_id=wall_id, fields="status,description,members_count", v='5.130')
            except VkAPIError as exc:
                if exc.error_code == 100:
                    groupi = [{'deactivated': True}]

            try: useri = await vkapi.users.get(user_ids=wall_id, fields='photo_max,status,screen_name,followers_count,counters', v='5.130')
            except VkAPIError as exc:
                if exc.error_code == 113:
                    useri = [{'deactivated': True}]

        if not 'deactivated' in groupi[0] and not 'deactivated' in useri[0]:
            subs = chn.find_subs(groupi[0]['id'])
            if len(subs) == 0: raise NotSub

            elif len(subs) == 2:
                group_embed = group_compile_embed(groupi[0])
                user_embed = user_compile_embed(useri[0])

                ctx.msg = await ctx.send(content='React with\n\t:one: for **first** wall,\n\t:two: for **second** wall,\n\t❌ for cancel.', embeds=[group_embed, user_embed])
                for emoji in ['1️⃣', '2️⃣', '❌']:
                    await ctx.msg.add_reaction(emoji)
                
                try:
                    r, u = await self.client.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message.id == ctx.msg.id and r.emoji in ['1️⃣', '❌', '2️⃣'], timeout=120.0)
                except asyncio.TimeoutError:
                    await ctx.msg.clear_reactions()
                    await ctx.msg.edit(content='❌ Cancelled (timeout)', embed=None)
                else:
                    await ctx.msg.clear_reactions()

                    if r.emoji == '1️⃣':
                        await self.setup_wall(ctx, 'del', channel, 'g', groupi[0], group_embed)

                    elif r.emoji == '2️⃣':
                        await self.setup_wall(ctx, 'del', channel, 'u', useri[0], user_embed)

                    else:
                        await ctx.msg.edit(content='❌ Cancelled', embed=None)
            
            elif len(subs) == 1:
                if subs[0].type == 'g':
                    wall_embed = group_compile_embed(groupi[0])
                    walli = groupi[0]
                elif subs[0].type == 'u': 
                    wall_embed = user_compile_embed(useri[0])
                    walli = useri[0]
                await self.setup_wall(ctx, 'del', channel, subs[0].type, walli, wall_embed)

        elif not 'deactivated' in groupi[0]:
            subs = chn.find_subs(groupi[0]['id'])
            if len(subs) == 0: raise NotSub

            await self.setup_wall(ctx, 'del', channel, 'g', groupi[0], group_compile_embed(groupi[0]))

        elif not 'deactivated' in useri[0]:
            subs = chn.find_subs(groupi[0]['id'])
            if len(subs) == 0: raise NotSub

            await self.setup_wall(ctx, 'del', channel, 'u', useri[0], user_compile_embed(useri[0]))

        else: raise VkWallBlocked

    @cog_ext.cog_subcommand(name='account',
                            base='subs',
                            description='Show VK Account linked to this Server')
    @commands.has_permissions(administrator=True)
    async def account(self, ctx):
        vk_token = Server.find_by_args(ctx.guild.id).token
        if vk_token is None:
            raise NotAuthenticated


        async with aiovk.TokenSession(vk_token) as ses:
            vkapi = aiovk.API(ses)
            user_embed = user_compile_embed((await vkapi.users.get(fields='photo_max,status,screen_name,followers_count,counters', v='5.130'))[0])
        await ctx.send(f'**{ctx.guild.name}** is linked to this account.\nYou can change it with `/subs link` command.', embed=user_embed)

    @cog_ext.cog_subcommand(name='link',
                            base='subs',
                            description='Link this Server to your VK Account')
    @commands.has_permissions(administrator=True)
    async def link(self, ctx):
        key = Fernet.generate_key().decode("utf-8")
        embed = discord.Embed(
            title = 'Authentication',
            url = f'{sets["url"]}/oauth2/login?key={key}',
            description = 'Follow the link to authenticate with your VK profile to be able to use **WallPost VK**.',
            color = sets["embedColor"]
        )
        embed.set_thumbnail(url=vk['photo'])
        embed.set_footer(text=vk['name'], icon_url=vk['photo'])

        ctx.msg = await ctx.send('Check your DM for an authentication link!')
        Server.temp_data.append({"key": key, "server_id": ctx.guild.id, "chn_id": ctx.channel.id, "msg_id": ctx.msg.id})
        await ctx.author.send(embed=embed)


    async def setup_wall(self, ctx, action, channel, wall, walli, embed):
        if hasattr(ctx, 'msg'):
            await ctx.msg.edit(content='Is this the wall you requested?\nReact with ✅ or ❌', embed=embed)
        else:
            ctx.msg = await ctx.send(content='Is this the wall you requested?\nReact with ✅ or ❌', embed=embed)

        for emoji in ['✅', '❌']:
            await ctx.msg.add_reaction(emoji)

        try:
            r, u = await ctx.bot.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message.id == ctx.msg.id and r.emoji in ['✅', '❌'], timeout=120.0)
        except asyncio.TimeoutError:
            await ctx.msg.clear_reactions()
            await ctx.msg.edit(content='❌ Cancelled (timeout)', embed=None)
        else:
            await ctx.msg.clear_reactions()

            if r.emoji == '✅':
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
                    # if wall == 'g':
                    #     if walli['is_admin'] == 1:
                    #         if walli['admin_level'] == 3:
                    #             await ctx.send(f'You are the administrator of **{name}**. You can enable \"long-poll\" reposting.\nThis means bla bla bla WIP')
                                # vkapi.groups.setLongPollSettings(enabled=1, wall_post_new=1, v='5.130')
                                # long_poll = True

                    if _channel is None:
                        _channel = await Channel.add(Server.find_by_args(ctx.guild.id), channel, {'vk_id': abs(walli['id']), 'vk_type': wall, 'long_poll': long_poll, 'last_post_id': 0, 'token': None})

                    elif _channel.find_subs(walli['id'], wall) is None:
                        _sub = await Subscription.add(_channel, {'vk_id': abs(walli['id']), 'vk_type': wall, 'long_poll': long_poll, 'last_post_id': 0, 'token': None})
                        
                    else: raise SubExists

                    await ctx.msg.edit(content=f'✅ Successfully subscribed {channel.mention} to **{name}** wall!', embed=None)

                if action == 'del':
                    await Server.find_by_args(ctx.guild.id).find_channel(channel.id).find_subs(walli['id'], wall).delete()

                    await ctx.msg.edit(content=f'✅ Successfully unsubscrubed {channel.mention} from **{name}** wall!', embed=None)

            elif r.emoji == '❌':
                await ctx.msg.edit(content='❌ Cancelled', embed=None)

    @ipc.server.route()
    async def authentication(self, data):
        try:
            temp_data = list(filter(lambda temp_data: temp_data['key'] == data.key, Server.temp_data))[0]
        except IndexError:
            return "This link has been expired. Get a new one with `/subs link` command."

        server = Server.find_by_args(temp_data['server_id'])
        await server.set_token(data.token)

        async with aiovk.TokenSession(server.token) as ses:
            vkapi = aiovk.API(ses)
            user = (await vkapi.users.get(fields='photo_max,status,screen_name,followers_count,counters', v='5.130'))[0]
        msg = self.client.get_channel(temp_data["chn_id"]).get_partial_message(temp_data['msg_id'])
        await msg.edit(content=f"**{self.client.get_guild(server.id).name}** is now linked to this account.\nYou can change it with `/subs link` command.", embed=user_compile_embed(user))

        Server.temp_data.remove(temp_data)

        return 'Your account is now bound to the server. You can now close this tab.'


def setup(client):
    client.add_cog(Subscriptions(client))