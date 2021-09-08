import discord
from discord.ext import commands, ipc
from discord_slash import cog_ext
from discord_slash.utils.manage_commands import create_option
from discord_slash.utils.manage_components import create_button, create_actionrow, wait_for_component
from discord_slash.model import ButtonStyle

import aiopg
import aiovk
from aiovk.pools import AsyncVkExecuteRequestPool
from aiovk.exceptions import VkAPIError

from psycopg2.extras import DictCursor

import texttable
from cryptography.fernet import Fernet

from rsc.config import sets
from rsc.functions import compile_wall_embed, vk
from rsc.classes import SafeDict
from rsc.exceptions import *


class Subscriptions(commands.Cog):
    __name__ = 'Subscriptions Command'

    def __init__(self, client):
        self.client = client
        self.logger = self.client.logger
        self.loop = self.client.loop
        self.repcog = self.client.get_cog('Repost')
        self.loop.create_task(self.ainit())

        msg = f'Load COG {self.__name__}'
        if hasattr(self.client, 'cogs_msg'):
            self.client.cogs_msg += f'\n\t{msg}'
        else:
            self.client.logger.info(msg)

        self.user_fields = 'photo_max,status,screen_name,followers_count,verified'
        self.group_fields = 'photo_200,status,screen_name,members_count,verified'

    async def ainit(self):
        async with aiopg.connect(sets["psqlUri"]) as conn:
            async with conn.cursor(cursor_factory=DictCursor) as cur:
                await cur.execute("SELECT id, lang FROM server")
                srvs = await cur.fetchall()
                await cur.execute("SELECT id, webhook_url, server_id FROM channel")
                chns = await cur.fetchall()
                await cur.execute("SELECT wall_id, users_id, channel_id, msg, id FROM subscription")
                subs = await cur.fetchall()
                await cur.execute("SELECT id, public, last_id FROM wall")
                walls = await cur.fetchall()
                await cur.execute("SELECT id, token FROM users")
                usrs = await cur.fetchall()

        msg = 'INIT {aa}USRs{aa} {tttpy}\n'
        for usr in usrs:
            _usr, _msg = self.repcog.User_init(usr['id'], usr['token'])
            msg += f'{_msg}\n'
        msg += ' {ttt}'
        del usrs
        self.logger.info(msg)

        msg = 'INIT {aa}WALLs{aa} {tttpy}\n'
        for wall in walls:
            _wall, _msg = self.repcog.Wall_init(wall['id'], wall['public'], wall['last_id'])
            msg += f'{_msg}\n'
        msg += ' {ttt}'
        del walls
        self.logger.info(msg)

        msg = 'INIT {aa}SRVs{aa} {tttpy}\n'
        for srv in srvs:
            _srv, _msg = self.repcog.Server_init(srv['id'], srv['lang'])
            msg += f'{_msg}\n'
            for chn in chns:
                if chn['server_id'] == _srv.id:
                    _chn, _msg = _srv.Channel_init(chn['id'], chn['webhook_url'])
                    msg += f'\t{_msg}\n'
                    for sub in subs:
                        if sub['channel_id'] == _chn.id:
                            usr, _ = self.repcog.User.find_by_args(sub['users_id'])
                            wall, _ = self.repcog.Wall.find_by_args(sub['wall_id'])
                            _sub, _msg = _chn.Subscription_init(wall, usr, sub['msg'], sub['id'])
                            msg += f'\t\t{_msg}\n'
        msg += ' {ttt}'
        del srvs, chns, subs
        self.logger.info(msg)

    def cog_unload(self):
        msg = f'Unload COG {self.__name__}'
        if hasattr(self.client, 'cogs_msg'):
            self.client.cogs_msg += f'\n\t{msg}'
        else:
            self.client.logger.info(msg)


    @cog_ext.cog_subcommand(base='subs', name='add',
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
    @commands.bot_has_permissions(manage_webhooks=True, send_messages=True, embed_links=True, add_reactions=True, manage_messages=True, read_message_history=True)
    @commands.has_permissions(manage_webhooks=True)
    async def sub_add(self, ctx, wall_id, channel=None):
        logmsg = str()
        usr, usrmsg = self.repcog.User.find_by_args(ctx.author.id)
        if usr is None:
            usr, usrmsg = self.repcog.User_add(ctx.author.id)
        logmsg += f'{usrmsg}\n'
        token = usr.token
        if token is None:
            raise NotAuthenticated
        if wall_id.startswith('<') and wall_id.endswith('>'):
            raise WallIdBadArgument
        elif wall_id == '0':
            raise VkWallBlocked
        if channel is None:
            channel = ctx.channel
        ctx.webhook_channel = channel


        async with aiovk.TokenSession(token) as ses:
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

            if len(group['name']) > 25:
                grp_name = f"{group['name'][:24]}…"
            usr_name = f"{user['first_name']} {user['last_name']}"
            if len(usr_name) > 25:
                usr_name = f"{usr_name[:24]}…"
            
            buttons = [create_button(
                    style=ButtonStyle.blue, label=grp_name, emoji="1️⃣", custom_id='group'),
                create_button(
                    style=ButtonStyle.blue, label=usr_name, emoji="2️⃣", custom_id='user'),
                create_button(
                    style=ButtonStyle.red, label="Cancel", emoji="❌", custom_id='cancel')]
            action_row = create_actionrow(*buttons)
            ctx.msg = await ctx.send(content='Select the wall', embeds=[group_embed, user_embed], components=[action_row])
            button = await wait_for_component(self.client, components=action_row, check=lambda btn_ctx: btn_ctx.author_id == ctx.author_id, timeout=120.0)
            await button.defer(edit_origin=True)

            if button.custom_id == 'group':
                await self.setup_wall(ctx, logmsg, usr, group, group_embed)
            elif button.custom_id == 'user':
                await self.setup_wall(ctx, logmsg, usr, user, user_embed)
            else:
                await ctx.msg.edit(content='❌ Cancelled', embed=None, components=[])

        elif not 'deactivated' in group:
            await self.setup_wall(ctx, logmsg, usr, group, compile_wall_embed(group))

        elif not 'deactivated' in user:
            await self.setup_wall(ctx, logmsg, usr, user, compile_wall_embed(user))

        else: raise VkWallBlocked

    @cog_ext.cog_subcommand(base='subs', name='info',
                            description='Show all Subscriptions for Channel',
                            options=[create_option(
                                name='channel',
                                description='Default: current Channel',
                                option_type=7,
                                required=False
                            )],
                            guild_ids=None if sets['version'] == 'MAIN' else [sets['srvcSrv']])
    @commands.bot_has_permissions(manage_webhooks=True, send_messages=True, embed_links=True, add_reactions=True, manage_messages=True, read_message_history=True)
    @commands.has_permissions(manage_webhooks=True)
    async def sub_info(self, ctx, channel=None):
        logmsg = str()
        usr, _ = self.repcog.User.find_by_args(ctx.author.id)
        if usr is None:
            usr, usrmsg = self.repcog.User_add(ctx.author.id)
            logmsg += f'{usrmsg}\n'
            self.logger.info('Add {aa}USR{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=logmsg)))
        token = usr.token
        if token is None:
            raise NotAuthenticated
        if channel is None:
            channel = ctx.channel
        ctx.webhook_channel = channel

        srv, _ = self.repcog.Server.find_by_args(ctx.guild.id)
        chn, _ = srv.find_channel(channel.id)
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

        pool = AsyncVkExecuteRequestPool()
        walls = list()
        async with AsyncVkExecuteRequestPool() as pool:
            for sub in subs:
                if sub.wall.id < 0:
                    walls.append({
                        'subObject': sub, 'resp': pool.add_call('groups.getById', sub.user.token, {'group_ids': abs(sub.wall.id)})})
                else:
                    walls.append({
                        'subObject': sub, 'resp': pool.add_call('users.get', sub.user.token, {'user_ids': sub.wall.id, 'fields': 'screen_name'})})
        
        for wall in walls:
            sub = wall['subObject']
            resp = wall['resp'].result[0]

            if sub.wall.id < 0:
                wall_type = 'Group'
            else:
                resp['name'] = f"{resp['first_name']} {resp['last_name']}"
                wall_type = 'User'
            added_by = self.client.get_user(sub.user.id)

            table.add_row([resp['name'], resp['screen_name'], wall_type, resp['id'], f'{added_by.name}#{added_by.discriminator}'])
            embed.add_field(
                name = resp['name'],
                value = f"Short address: `{resp['screen_name']}`\nType: `{wall_type}`\nID: `{resp['id']}`\nAdded by: {added_by.mention}",
                inline = True
            )

        await ctx.send(f"**Wall subscriptions for **{channel.mention}** channel:**\n```{table.draw()}```", embed=embed)

    @cog_ext.cog_subcommand(base='subs', name='del',
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
    @commands.bot_has_permissions(manage_webhooks=True, send_messages=True, embed_links=True, add_reactions=True, manage_messages=True, read_message_history=True)
    @commands.has_permissions(manage_webhooks=True)
    async def sub_del(self, ctx, wall_id, channel=None):
        logmsg = str()
        usr, usrmsg = self.repcog.User.find_by_args(ctx.author.id)
        if usr is None:
            usr, usrmsg = self.repcog.User_add(ctx.author.id)
        logmsg += f'{usrmsg}\n'
        token = usr.token
        if token is None:
            raise NotAuthenticated
        if wall_id.startswith('<') and wall_id.endswith('>'):
            raise WallIdBadArgument
        elif wall_id == '0':
            raise VkWallBlocked
        if channel is None:
            channel = ctx.channel
        ctx.webhook_channel = channel
        
        srv, srvmsg = self.repcog.Server.find_by_args(ctx.guild.id)
        chn, chnmsg = srv.find_channel(channel.id)
        if chn is None:
            raise NotSub


        async with aiovk.TokenSession(token) as ses:
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
            subs, _ = chn.find_subs(group['id'])
            if len(subs) == 0:
                raise NotSub

            elif len(subs) == 2:
                group_embed = compile_wall_embed(group)
                user_embed = compile_wall_embed(user)

                if len(group['name']) > 25:
                    grp_name = f"{group['name'][:24]}…"
                usr_name = f"{user['first_name']} {user['last_name']}"
                if len(usr_name) > 25:
                    usr_name = f"{usr_name[:24]}…"

                buttons = [create_button(
                        style=ButtonStyle.blue, label=grp_name, emoji="1️⃣", custom_id='group'),
                    create_button(
                        style=ButtonStyle.blue, label=usr_name, emoji="2️⃣", custom_id='user'),
                    create_button(
                        style=ButtonStyle.red, label="Cancel", emoji="❌", custom_id='cancel')]
                action_row = create_actionrow(*buttons)
                ctx.msg = await ctx.send(content='Select the wall', embeds=[group_embed, user_embed], components=[action_row])
                button = await wait_for_component(self.client, components=action_row, check=lambda btn_ctx: btn_ctx.author_id == ctx.author_id, timeout=120.0)
                await button.defer(edit_origin=True)

                if button.custom_id == 'group':
                    await self.setup_wall(ctx, logmsg, usr, group, group_embed)
                elif button.custom_id == 'user':
                    await self.setup_wall(ctx, logmsg, usr, user, user_embed)
                else:
                    await ctx.msg.edit(content='❌ Cancelled', embed=None, components=[])
            
            elif len(subs) == 1:
                if subs[0].wall.id < 0:
                    await self.setup_wall(ctx, logmsg, usr, group, compile_wall_embed(group))
                else: 
                    await self.setup_wall(ctx, logmsg, usr, user, compile_wall_embed(user))

        elif not 'deactivated' in group:
            subs = chn.find_subs(group['id'])
            if len(subs) == 0:
                raise NotSub

            await self.setup_wall(ctx, logmsg, usr, group, compile_wall_embed(group))

        elif not 'deactivated' in user:
            subs = chn.find_subs(user['id'])
            if len(subs) == 0:
                raise NotSub

            await self.setup_wall(ctx, logmsg, usr, user, compile_wall_embed(user))

        else: raise VkWallBlocked

    @cog_ext.cog_subcommand(base='subs', name='account',
                            description='Show VK Account you are logged in',
                            guild_ids=None if sets['version'] == 'MAIN' else [sets['srvcSrv']])
    @commands.bot_has_permissions(manage_webhooks=True, send_messages=True, embed_links=True, add_reactions=True, manage_messages=True, read_message_history=True)
    @commands.has_permissions(administrator=True)
    async def account(self, ctx):
        logmsg = str()
        usr, _ = self.repcog.User.find_by_args(ctx.author.id)
        if usr is None:
            usr, usrmsg = self.repcog.User_add(ctx.author.id)
            logmsg += f'{usrmsg}\n'
            self.logger.info('Add {aa}USR{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=logmsg)))
        token = usr.token
        if token is None:
            raise NotAuthenticated


        async with aiovk.TokenSession(token) as ses:
            vkapi = aiovk.API(ses)
            user_embed = compile_wall_embed((await vkapi.users.get(fields=self.user_fields, v='5.130'))[0])
        await ctx.send(f'You are logged in **{ctx.guild.name}** is linked to this account.\nYou can change it with `/subs link` command.', embed=user_embed)

    @cog_ext.cog_subcommand(base='subs', name='link',
                            description='Login to your VK Account',
                            guild_ids=None if sets['version'] == 'MAIN' else [sets['srvcSrv']])
    @commands.bot_has_permissions(manage_webhooks=True, send_messages=True, embed_links=True, add_reactions=True, manage_messages=True, read_message_history=True)
    @commands.has_permissions(administrator=True)
    async def link(self, ctx):
        logmsg = str()
        usr, _ = self.repcog.User.find_by_args(ctx.author.id)
        if usr is None:
            usr, usrmsg = self.repcog.User_add(ctx.author.id)
            logmsg += f'{usrmsg}\n'
            self.logger.info('Add {aa}USR{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=logmsg)))

        ctx.msg = await ctx.send('Check your DM for login link')

        key = Fernet.generate_key().decode("utf-8")
        self.repcog.User.auth_data.append({"key": key, "usr_id": usr.id, "chn_id": ctx.channel.id, "msg_id": ctx.msg.id})
        buttons = [create_button(
            style=ButtonStyle.URL, label='Login', url=f'{sets["url"]}/oauth2/login?key={key}')]
        action_row = create_actionrow(*buttons)
        await ctx.author.send(content='Follow the link to login to your VK profile', components=[action_row])


    async def setup_wall(self, ctx, logmsg, usr, resp, embed):
        buttons = [create_button(
                style=ButtonStyle.green, emoji="✅", custom_id='yes'),
            create_button(
                style=ButtonStyle.red, emoji="❌", custom_id='no')]
        action_row = create_actionrow(*buttons)
        if hasattr(ctx, 'msg'):
            await ctx.msg.edit(content='Is this the wall you requested?', embed=embed, components=[action_row])
        else:
            ctx.msg = await ctx.send(content='Is this the wall you requested?', embed=embed, components=[action_row])
        button = await wait_for_component(self.client, components=action_row, check=lambda btn_ctx: btn_ctx.author_id == ctx.author_id, timeout=120.0)
        await button.defer(edit_origin=True)

        if button.custom_id == 'yes':
            if 'name' in resp:
                if not resp['is_closed'] == 0 and resp['is_member'] == 0:
                    raise WallClosed
                name = resp['name']
                resp['id'] = -resp['id']
            else:
                if resp['can_access_closed'] == False:
                    raise WallClosed
                name = f'{resp["first_name"]} {resp["last_name"]}'
            
            srv, srvmsg = self.repcog.Server.find_by_args(ctx.guild.id)
            logmsg += f'{srvmsg}\n'
            chn, chnmsg = srv.find_channel(ctx.webhook_channel.id)
            if ctx.subcommand_name == 'add':
                if chn is None:
                    chn, chnmsg = await srv.Channel_add(ctx.webhook_channel)
                logmsg += f'\t{chnmsg}\n'
                subs, _ = chn.find_subs(resp['id'], True)
                if len(subs) == 0:
                    wall, wallmsg = self.repcog.Wall.find_by_args(resp['id'])
                    if wall is None:
                        wall, wallmsg = await self.repcog.Wall_add(resp['id'])
                    
                    buttons = [create_button(
                            style=ButtonStyle.green, emoji="✅", custom_id='yes'),
                        create_button(
                            style=ButtonStyle.red, emoji="❌", custom_id='no')]
                    action_row = create_actionrow(*buttons)
                    await ctx.msg.edit(content=f'Would you like to set a message to be sent with new posts?', components=[action_row], embed=None)
                    button = await wait_for_component(self.client, components=action_row, check=lambda btn_ctx: btn_ctx.author_id == ctx.author_id, timeout=120.0)
                    await button.defer(edit_origin=True)

                    if button.custom_id == 'yes':
                        await ctx.msg.edit(content=f'Reply with the text you want to be in the notification message (255 chars max)', components=[], embed=None)
                        m = await self.client.wait_for('message', check=
                            lambda m: m.reference is not None and m.reference.message_id == ctx.msg.id and m.author.id == ctx.author.id, timeout=120.0)
                        msg = m.content
                        if len(msg) > 255:
                            raise MsgTooLong
                        await m.delete()
                    else:
                        msg = None
                    
                    sub, submsg = await chn.Subscription_add(wall, usr, msg)
                    logmsg += f'\t\t{submsg}\n{wallmsg}\n'
                else:
                    raise SubExists
                await ctx.msg.edit(content=f'✅ Successfully subscribed {ctx.webhook_channel.mention} to **{name}** wall!', components=[], embed=None)
                self.logger.info('Add {aa}SUB{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=logmsg)))

            elif ctx.subcommand_name == 'del':
                if len(chn.subscriptions) == 1:
                    chnmsg = await chn.delete()
                    logmsg += f'\t{chnmsg}\n'
                else:
                    logmsg += f'\t{chnmsg}\n'
                    sub, submsg = chn.find_subs(resp['id'], wall_type=True)
                    logmsg += f'\t\t{submsg}\n'
                    await sub[0].delete()

                wall, wallmsg = self.repcog.Wall.find_by_args(resp['id'])
                if len(wall.subscriptions) == 0:
                    wallmsg = await wall.delete()
                logmsg += f'{wallmsg}\n'
                await ctx.msg.edit(content=f'✅ Successfully unsubscrubed {ctx.webhook_channel.mention} from **{name}** wall!', components=[], embed=None)
                self.logger.info('Del {aa}SUB{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=logmsg)))

        else:
            await ctx.msg.edit(content='❌ Cancelled', embed=None, components=[])

    @ipc.server.route()
    async def authentication(self, data):
        try:
            auth_data = list(filter(lambda auth_data: auth_data['key'] == data.key, self.repcog.User.auth_data))[0]
        except IndexError:
            return "This link has been expired. Get a new one with `/subs link` command."

        usr, _ = self.repcog.User.find_by_args(auth_data['usr_id'])
        await usr.set_token(data.token)

        async with aiovk.TokenSession(usr.token) as ses:
            vkapi = aiovk.API(ses)
            user = (await vkapi.users.get(fields=self.user_fields, v='5.130'))[0]
        msg = self.client.get_channel(auth_data["chn_id"]).get_partial_message(auth_data['msg_id'])
        await msg.edit(content=f"Your profile is now linked to this account.\nYou can change it with `/subs link` command.", embed=compile_wall_embed(user))

        self.repcog.User.auth_data.remove(auth_data)

        return 'Your account is now bound to the server. You can now close this tab.'


def setup(client):
    client.add_cog(Subscriptions(client))