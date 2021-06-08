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
from rsc.functions import compile_wall_embed, add_command_and_example, vk
from rsc.classes import Server, Channel, Subscription
from rsc.exceptions import *


class Subscriptions(commands.Cog):
    __name__ = 'Subscriptions Command'

    def __init__(self, client):
        msg = f'Load COG {self.__name__}'
        if hasattr(client, 'cogs_msg'):
            client.cogs_msg += f'\n\t{msg}'
        else:
            client.logger.info(msg)

        self.user_fields = 'photo_max,status,screen_name,followers_count,verified'
        self.group_fields = 'photo_200,status,screen_name,members_count,verified'

        self.client = client
        self.loop = client.loop
        self.loop.create_task(self.ainit())

    async def ainit(self):
        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("SELECT id, lang, token FROM server")
                srvs = await cur.fetchall()
                await cur.execute("SELECT id, webhook_url, server_id FROM channel")
                chns = await cur.fetchall()
                await cur.execute("SELECT wall_id, wall_type, last_id, token, added_by, channel_id FROM subscription")
                subs = await cur.fetchall()

                msg = 'INIT {{aa}}SRVs{{aa}} {{tttpy}}'
                for srv in srvs:
                    _srv, _msg = Server.init(srv['id'], srv['lang'], srv['token'])
                    msg += f'\n{_msg}'
                    for chn in chns:
                        if chn['server_id'] == _srv.id:
                            _chn, _msg = Channel.init(_srv, chn['id'], chn['webhook_url'])
                            msg += f'\n{_msg}'
                            for sub in subs:
                                if sub['channel_id'] == _chn.id:
                                    _sub, _msg = Subscription.init(_chn, {
                                        'wall_id': sub['wall_id'], 'wall_type': sub['wall_type'], 'last_id': sub['last_id'], 'token': sub['token'], 'added_by': sub['added_by']
                                    })
                                    msg += f'\n{_msg}'
                msg += ' {{ttt}}'
                del srvs, chns, subs
        self.client.logger.info(msg.format())

    def cog_unload(self):
        msg = f'Unload COG {self.__name__}'
        if hasattr(client, 'cogs_msg'):
            client.cogs_msg += f'\n\t{msg}'
        else:
            client.logger.info(msg)
        Server.uninit_all()


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
                            )],
                            guild_ids=None if sets['version'] == 'MAIN' else [sets['srvcSrv']])
    @commands.bot_has_permissions(manage_webhooks=True, add_reactions=True, manage_messages=True)
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
            raise commands.BotMissingPermissions(['manage_webhooks'])


        async with aiovk.TokenSession(vk_token) as ses:
            vkapi = aiovk.API(ses)

            try:
                group = (await vkapi.groups.getById(group_id=wall_id, fields=self.group_fields, v='5.130'))[0]
                if group['is_closed'] == 1 and not 'is_member' in group:
                    group = {'deactivated': True}
            except VkAPIError as exc:
                if exc.error_code == 100:
                    group = {'deactivated': True}
            
            try:
                user = (await vkapi.users.get(user_ids=wall_id, fields=self.user_fields, v='5.130'))[0]
            except VkAPIError as exc:
                if exc.error_code == 113:
                    user = {'deactivated': True}

        if (not 'deactivated' in group) and (not 'deactivated' in user):
            group_embed = compile_wall_embed(group)
            user_embed = compile_wall_embed(user)

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
                    await self.setup_wall(ctx, group, group_embed)
                elif r.emoji == '2️⃣':
                    await self.setup_wall(ctx, user, user_embed)
                else:
                    await ctx.msg.edit(content='❌ Cancelled', embed=None)

        elif not 'deactivated' in group:
            await self.setup_wall(ctx, group, compile_wall_embed(group))

        elif not 'deactivated' in user:
            await self.setup_wall(ctx, user, compile_wall_embed(user))

        else: raise VkWallBlocked

    @cog_ext.cog_subcommand(name='info',
                            base='subs',
                            description='Show all Subscriptions for Channel',
                            options=[create_option(
                                name='channel',
                                description='Default: current Channel',
                                option_type=7,
                                required=False
                            )],
                            guild_ids=None if sets['version'] == 'MAIN' else [sets['srvcSrv']])
    @commands.bot_has_permissions(manage_webhooks=True, add_reactions=True, manage_messages=True)
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
        elif len(chn.subscriptions) == 0:
            raise NoSubs
        subs = chn.subscriptions


        embed = discord.Embed(
            title = f'Wall subscriptions',
            description = f'for {channel.mention} channel:',
            color = sets["embedColor"]
        )
        table = texttable.Texttable(max_width=0)
        table.set_cols_align(['c','c','c','c','c'])
        table.header(['Name', 'Short address', 'Type', 'ID', 'Added by'])
        table.set_cols_dtype(['t','t','t','i','t'])
        table.set_chars(['─','│','┼','─'])

        groups, users = '', ''
        added_by_groups, added_by_users = [], []
        for sub in subs:
            if sub.wall_type == 'g':
                groups += f"{sub.wall_id},"
                added_by_groups.append(sub.added_by)
            else:
                users += f"{sub.wall_id},"
                added_by_users.append(sub.added_by)
        async with aiovk.TokenSession(vk_token) as ses:
            vkapi = aiovk.API(ses)
            if groups != '':
                resp_groups = await vkapi.groups.getById(group_ids=groups, v='5.130')

                for wall, added_by in zip(resp_groups, added_by_groups):
                    name = f"{wall['name']}"
                    added_by = self.client.get_user(added_by)

                    table.add_row([name, wall['screen_name'], 'Group', wall['id'], f'{added_by.name}#{added_by.discriminator}'])
                    embed.add_field(
                        name = name,
                        value = f"Short address: `{wall['screen_name']}`\nType: `Group`\nID: `{wall['id']}`\nAdded by: {added_by.mention}",
                        inline = True
                    )
            if users != '':
                r_users = await vkapi.users.get(user_ids=users, fields='screen_name', v='5.130')

                for wall, added_by in zip(r_users, added_by_users):
                    name = f"{wall['first_name']} {wall['last_name']}"
                    added_by = self.client.get_user(added_by)

                    table.add_row([name, wall['screen_name'], 'User', wall['id'], f'{added_by.name}#{added_by.discriminator}'])
                    embed.add_field(
                        name = name,
                        value = f"Short address: `{wall['screen_name']}`\nType: `User`\nID: `{wall['id']}`\nAdded by: {added_by.mention}",
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
                            )],
                            guild_ids=None if sets['version'] == 'MAIN' else [sets['srvcSrv']])
    @commands.bot_has_permissions(manage_webhooks=True, add_reactions=True, manage_messages=True)
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

            try:
                group = (await vkapi.groups.getById(group_id=wall_id, fields=self.group_fields, v='5.130'))[0]
            except VkAPIError as exc:
                if exc.error_code == 100:
                    group = {'deactivated': True}

            try:
                user = (await vkapi.users.get(user_ids=wall_id, fields=self.user_fields, v='5.130'))[0]
            except VkAPIError as exc:
                if exc.error_code == 113:
                    user = {'deactivated': True}

        if (not 'deactivated' in group) and (not 'deactivated' in user):
            subs = chn.find_subs(group['id'])
            if len(subs) == 0: raise NotSub

            elif len(subs) == 2:
                group_embed = compile_wall_embed(group)
                user_embed = compile_wall_embed(user)

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
                        await self.setup_wall(ctx, group, group_embed)

                    elif r.emoji == '2️⃣':
                        await self.setup_wall(ctx, user, user_embed)

                    else:
                        await ctx.msg.edit(content='❌ Cancelled', embed=None)
            
            elif len(subs) == 1:
                if subs[0].wall_type == 'g':
                    await self.setup_wall(ctx, group, compile_wall_embed(group))
                elif subs[0].wall_type == 'u': 
                    await self.setup_wall(ctx, user, compile_wall_embed(user))

        elif not 'deactivated' in group:
            subs = chn.find_subs(group['id'])
            if len(subs) == 0:
                raise NotSub

            await self.setup_wall(ctx, group, compile_wall_embed(group))

        elif not 'deactivated' in user:
            subs = chn.find_subs(group['id'])
            if len(subs) == 0: raise NotSub

            await self.setup_wall(ctx, user, compile_wall_embed(user))

        else: raise VkWallBlocked

    @cog_ext.cog_subcommand(name='account',
                            base='subs',
                            description='Show VK Account linked to this Server',
                            guild_ids=None if sets['version'] == 'MAIN' else [sets['srvcSrv']])
    @commands.has_permissions(administrator=True)
    async def account(self, ctx):
        vk_token = Server.find_by_args(ctx.guild.id).token
        if vk_token is None:
            raise NotAuthenticated


        async with aiovk.TokenSession(vk_token) as ses:
            vkapi = aiovk.API(ses)
            user_embed = compile_wall_embed((await vkapi.users.get(fields=self.user_fields, v='5.130'))[0])
        await ctx.send(f'**{ctx.guild.name}** is linked to this account.\nYou can change it with `/subs link` command.', embed=user_embed)

    @cog_ext.cog_subcommand(name='link',
                            base='subs',
                            description='Link this Server to your VK Account',
                            guild_ids=None if sets['version'] == 'MAIN' else [sets['srvcSrv']])
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


    async def setup_wall(self, ctx, wall, embed):
        if hasattr(ctx, 'msg'):
            await ctx.msg.edit(content='Is this the wall you requested?\nReact with ✅ or ❌', embed=embed)
        else:
            ctx.msg = await ctx.send(content='Is this the wall you requested?\nReact with ✅ or ❌', embed=embed)

        for emoji in ['✅', '❌']:
            await ctx.msg.add_reaction(emoji)

        try:
            r, u = await self.client.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message.id == ctx.msg.id and r.emoji in ['✅', '❌'], timeout=120.0)
        except asyncio.TimeoutError:
            await ctx.msg.clear_reactions()
            await ctx.msg.edit(content='❌ Cancelled (timeout)', embed=None)
        else:
            await ctx.msg.clear_reactions()

            if r.emoji == '✅':
                if 'name' in wall:
                    if not wall['is_closed'] == 0 and wall['is_member'] == 0:
                        raise WallClosed
                    name = wall['name']
                    wall_type = 'g'
                else:
                    if wall['can_access_closed'] == False:
                        raise WallClosed
                    name = f'{wall["first_name"]} {wall["last_name"]}'
                    wall_type = 'u'
                
                if ctx.subcommand_name == 'add':
                    _channel = Server.find_by_args(ctx.guild.id).find_channel(ctx.webhook_channel.id)
                    long_poll = False
                    # if wall == 'g':
                    #     if wall['is_admin'] == 1:
                    #         if wall['admin_level'] == 3:
                    #             await ctx.send(f'You are the administrator of **{name}**. You can enable \"long-poll\" reposting.\nThis means bla bla bla WIP')
                                # vkapi.groups.setLongPollSettings(enabled=1, wall_post_new=1, v='5.130')
                                # long_poll = True
                    if _channel is None:
                        _channel = await Channel.add(Server.find_by_args(ctx.guild.id), ctx.webhook_channel, {
                            'wall_id': wall['id'], 'wall_type': wall_type, 'last_id': 0, 'token': None, 'added_by': ctx.author.id})
                    elif _channel.find_subs(wall['id'], wall_type) is None:
                        _sub = await Subscription.add(_channel, {
                            'wall_id': wall['id'], 'wall_type': wall_type, 'last_id': 0, 'token': None, 'added_by': ctx.author.id})
                        
                    else: raise SubExists

                    await ctx.msg.edit(content=f'✅ Successfully subscribed {ctx.webhook_channel.mention} to **{name}** wall!', embed=None)

                if ctx.subcommand_name == 'del':
                    await Server.find_by_args(ctx.guild.id).find_channel(ctx.webhook_channel.id).find_subs(wall['id'], wall_type).delete()

                    await ctx.msg.edit(content=f'✅ Successfully unsubscrubed {ctx.webhook_channel.mention} from **{name}** wall!', embed=None)

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
            user = (await vkapi.users.get(fields=self.user_fields, v='5.130'))[0]
        msg = self.client.get_channel(temp_data["chn_id"]).get_partial_message(temp_data['msg_id'])
        await msg.edit(content=f"**{self.client.get_guild(server.id).name}** is now linked to this account.\nYou can change it with `/subs link` command.", embed=compile_wall_embed(user))

        Server.temp_data.remove(temp_data)

        return 'Your account is now bound to the server. You can now close this tab.'


def setup(client):
    client.add_cog(Subscriptions(client))