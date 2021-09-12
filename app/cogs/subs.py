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
from asyncio.exceptions import TimeoutError

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

        self.grp_call_attrs = {'extended': 1, 'count': 1, 'fields': 'photo_200,status,screen_name,members_count,verified', 'v': '5.84'}
        self.usr_call_attrs = {'extended': 1, 'count': 1, 'fields': 'photo_max,status,screen_name,followers_count,verified', 'v': '5.84'}

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
            usr, usrmsg = await self.repcog.User_add(ctx.author.id)
        logmsg += f'{usrmsg}\n'
        ctx.vk_token = usr.token
        if ctx.vk_token is None:
            raise NotAuthenticated
        if channel is None:
            channel = ctx.channel
        ctx.webhook_channel = channel
        ctx.wall_id = wall_id

        await self.request_walls(ctx)

        if (not ctx.grp_ERR) and (not ctx.usr_ERR):
            buttons = [create_button(
                    style=ButtonStyle.blue, label=ctx.grp_NAME if len(ctx.grp_NAME) <= 25 else f'{ctx.grp_NAME[:24]}…', custom_id='grp'),
                create_button(
                    style=ButtonStyle.blue, label=ctx.usr_NAME if len(ctx.usr_NAME) <= 25 else f'{ctx.usr_NAME[:24]}…', custom_id='usr'),
                create_button(
                    style=ButtonStyle.red, label="Cancel", custom_id='cancel')]
            action_row = create_actionrow(*buttons)
            ctx.msg = await ctx.send(content='Select the wall', embeds=[ctx.grp_EMBED, ctx.usr_EMBED], components=[action_row])
            button = await wait_for_component(self.client, components=action_row, check=lambda btn_ctx: btn_ctx.author_id == ctx.author_id, timeout=120.0)
            await button.defer(edit_origin=True)

            if button.custom_id == 'grp':
                await self.setup_wall(ctx, logmsg, usr, 'grp')
            elif button.custom_id == 'usr':
                await self.setup_wall(ctx, logmsg, usr, 'usr')
            else:
                await ctx.msg.edit(content='❌ Cancelled', embed=None, components=[])
        elif not ctx.grp_ERR:
            await self.setup_wall(ctx, logmsg, usr, 'grp')
        elif not ctx.usr_ERR:
            await self.setup_wall(ctx, logmsg, usr, 'usr')
        else:
            raise CouldNotFindWall(ctx.grp_RESP, ctx.usr_RESP)

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
            usr, usrmsg = await self.repcog.User_add(ctx.author.id)
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
            usr, usrmsg = await self.repcog.User_add(ctx.author.id)
        logmsg += f'{usrmsg}\n'
        ctx.vk_token = usr.token
        if ctx.vk_token is None:
            raise NotAuthenticated
        if channel is None:
            channel = ctx.channel
        ctx.webhook_channel = channel
        ctx.wall_id = wall_id
        
        srv, _ = self.repcog.Server.find_by_args(ctx.guild.id)
        chn, _ = srv.find_channel(channel.id)
        if chn is None:
            raise NotSub

        await self.request_walls(ctx)

        if (not ctx.grp_ERR) and (not ctx.usr_ERR):
            subs, _ = chn.find_subs(ctx.wall_id)
            if len(subs) == 0:
                raise NotSub
            elif len(subs) == 2:
                buttons = [create_button(
                        style=ButtonStyle.blue, label=ctx.grp_NAME if len(ctx.grp_NAME) <= 25 else f'{ctx.grp_NAME[:24]}…', custom_id='grp'),
                    create_button(
                        style=ButtonStyle.blue, label=ctx.usr_NAME if len(ctx.usr_NAME) <= 25 else f'{ctx.usr_NAME[:24]}…', custom_id='usr'),
                    create_button(
                        style=ButtonStyle.red, label="Cancel", custom_id='cancel')]
                action_row = create_actionrow(*buttons)
                ctx.msg = await ctx.send(content='Select the wall', embeds=[ctx.grp_EMBED, ctx.usr_EMBED], components=[action_row])
                button = await wait_for_component(self.client, components=action_row, check=lambda btn_ctx: btn_ctx.author_id == ctx.author_id, timeout=120.0)
                await button.defer(edit_origin=True)

                if button.custom_id == 'grp':
                    await self.setup_wall(ctx, logmsg, usr, 'grp')
                elif button.custom_id == 'usr':
                    await self.setup_wall(ctx, logmsg, usr, 'usr')
                else:
                    await ctx.msg.edit(content='❌ Cancelled', embed=None, components=[])
            elif len(subs) == 1:
                if subs[0].wall.id < 0:
                    await self.setup_wall(ctx, logmsg, usr, 'grp')
                else: 
                    await self.setup_wall(ctx, logmsg, usr, 'usr')
        elif not ctx.grp_ERR:
            subs = chn.find_subs(ctx.wall_id)
            if len(subs) == 0:
                raise NotSub
            else:
                await self.setup_wall(ctx, logmsg, usr, 'grp')
        elif not ctx.usr_ERR:
            subs = chn.find_subs(ctx.wall_id)
            if len(subs) == 0:
                raise NotSub
            else:
                await self.setup_wall(ctx, logmsg, usr, 'usr')
        else:
            raise CouldNotFindWall(ctx.grp_ERR, ctx.usr_ERR)

    @cog_ext.cog_subcommand(base='subs', name='manage',
                            description='Manage Channel Subscriptions',
                            options=[create_option(
                                name='channel',
                                description='Default: current Channel',
                                option_type=7,
                                required=False)],
                                guild_ids=None if sets['version'] == 'MAIN' else [sets['srvcSrv']])
    @commands.bot_has_permissions(manage_webhooks=True, send_messages=True, embed_links=True, add_reactions=True, manage_messages=True, read_message_history=True)
    async def sub_man(self, ctx, channel=None):
        pass

    async def request_walls(self, ctx):
        ctx.grp_ERR, ctx.usr_ERR = None, none, None

        vk_pool = AsyncVkExecuteRequestPool()
        groupsGetById_REQ = vk_pool.add_call('groups.getById', ctx.vk_token, self.grp_call_attrs | {'group_id': ctx.wall_id})
        usersGet_REQ = vk_pool.add_call('users.get', ctx.vk_token, self.usr_call_attrs | {'user_ids': ctx.wall_id})
        await vk_pool.execute()

        if groupsGetById_REQ.ok:
            groupsGetById_RESP = groupsGetById_REQ.result
            ctx.grp_REQ = vk_pool.add_call('wall.get', ctx.vk_token, self.grp_call_attrs | {'owner_id': -groupsGetById_RESP[0]['id']})
        else:
            ctx.grp_ERR = groupsGetById_REQ.error
        if usersGet_REQ.ok:
            usersGet_RESP = usersGet_REQ.result
            ctx.usr_REQ = vk_pool.add_call('wall.get', ctx.vk_token, self.usr_call_attrs | {'owner_id': usersGet_RESP[0]['id']})
        else:
            ctx.usr_ERR = usersGet_REQ.error
        await vk_pool.execute()

        if not ctx.grp_ERR:
            if ctx.grp_REQ.ok:
                ctx.grp_RESP = ctx.grp_REQ.result
                if len(ctx.grp_RESP['items']) > 0:
                    if ctx.grp_RESP['items'][0].get('is_pinned', False):
                        ctx.grp_REQ = vk_pool.add_call('wall.get', ctx.vk_token, self.grp_call_attrs | {'owner_id': -groupsGetById_RESP[0]['id'], 'offset': 1})
                        await vk_pool.execute()
                        ctx.grp_RESP = ctx.grp_REQ.result
                if len(ctx.grp_RESP['items']) == 0:
                    ctx.grp_RESP = {'items': [{'id': 0, 'owner_id': -groupsGetById_RESP[0]['id']}], 'groups': groupsGetById_RESP}
            else:
                ctx.grp_ERR = ctx.grp_REQ.error

        if not ctx.usr_ERR:
            if ctx.usr_REQ.ok:
                ctx.usr_RESP = ctx.usr_REQ.result
                if len(ctx.usr_RESP['items']) > 0:
                    if ctx.usr_RESP['items'][0].get('is_pinned', False):
                        ctx.usr_REQ = vk_pool.add_call('wall.get', ctx.vk_token, self.usr_call_attrs | {'owner_id': usersGet_RESP[0]['id'], 'offset': 1})
                        await vk_pool.execute()
                        ctx.usr_RESP = ctx.usr_REQ.result
                if len(ctx.usr_RESP['items']) == 0:
                    ctx.usr_RESP = {'items': [{'id': 0, 'owner_id': usersGet_RESP[0]['id'], 'offset': 1}], 'profiles': usersGet_RESP}
            else:
                ctx.usr_ERR = ctx.grp_REQ.error
        
        if not ctx.grp_ERR:
            ctx.grp_POST = ctx.grp_RESP['items'][0]
            ctx.wall_id = abs(ctx.grp_POST['owner_id'])
            for grp_WALL in ctx.grp_RESP['groups']:
                if grp_WALL['id'] == ctx.wall_id:
                    ctx.grp_WALL = grp_WALL
                    break
            ctx.grp_NAME = ctx.grp_WALL['name']
            ctx.grp_EMBED = compile_wall_embed(ctx.grp_WALL)

        if not ctx.usr_ERR:
            ctx.usr_POST = ctx.usr_RESP['items'][0]
            ctx.wall_id = ctx.usr_POST['owner_id']
            for usr_WALL in ctx.usr_RESP['profiles']:
                if usr_WALL['id'] == ctx.wall_id:
                    ctx.usr_WALL = usr_WALL
                    break
            ctx.usr_NAME = f"{ctx.usr_WALL['first_name']} {ctx.usr_WALL['last_name']}"
            ctx.usr_EMBED = compile_wall_embed(ctx.usr_WALL)

    async def setup_wall(self, ctx, logmsg, usr, mode):
        if mode == 'grp':
            wall_id = -ctx.wall_id
            name = ctx.grp_NAME
            post = ctx.grp_POST
            embed = ctx.grp_EMBED
        else:
            wall_id = ctx.wall_id
            name = ctx.usr_NAME
            post = ctx.usr_POST
            embed = ctx.usr_EMBED

        buttons = [create_button(
                style=ButtonStyle.green, label='Yes', custom_id='yes'),
            create_button(
                style=ButtonStyle.red, label='No', custom_id='no')]
        action_row = create_actionrow(*buttons)
        if hasattr(ctx, 'msg'):
            await ctx.msg.edit(content='Is this the wall you requested?', embed=embed, components=[action_row])
        else:
            ctx.msg = await ctx.send(content='Is this the wall you requested?', embed=embed, components=[action_row])
        button = await wait_for_component(self.client, components=action_row, check=lambda btn_ctx: btn_ctx.author_id == ctx.author_id, timeout=120.0)
        await button.defer(edit_origin=True)

        if button.custom_id == 'yes':
            srv, srvmsg = self.repcog.Server.find_by_args(ctx.guild.id)
            logmsg += f'{srvmsg}\n'
            chn, chnmsg = srv.find_channel(ctx.webhook_channel.id)
            if ctx.subcommand_name == 'add':
                if chn is None:
                    chn, chnmsg = await srv.Channel_add(ctx.webhook_channel)
                logmsg += f'\t{chnmsg}\n'
                subs, _ = chn.find_subs(wall_id, True)
                if len(subs) == 0:
                    wall, wallmsg = self.repcog.Wall.find_by_args(wall_id)
                    if wall is None:
                        wall, wallmsg = await self.repcog.Wall_add(wall_id, post['id'])
                    
                    buttons = [create_button(
                            style=ButtonStyle.green, label='Yes', custom_id='yes'),
                        create_button(
                            style=ButtonStyle.red, label='No', custom_id='no')]
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
                    sub, submsg = chn.find_subs(wall_id, wall_type=True)
                    logmsg += f'\t\t{submsg}\n'
                    await sub[0].delete()

                wall, wallmsg = self.repcog.Wall.find_by_args(wall_id)
                if len(wall.subscriptions) == 0:
                    wallmsg = await wall.delete()
                logmsg += f'{wallmsg}\n'
                await ctx.msg.edit(content=f'✅ Successfully unsubscrubed {ctx.webhook_channel.mention} from **{name}** wall!', components=[], embed=None)
                self.logger.info('Del {aa}SUB{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=logmsg)))

        else:
            await ctx.msg.edit(content='❌ Cancelled', embed=None, components=[])
    
    @cog_ext.cog_subcommand(base='subs', name='account',
                            description='Login with VK and show account you are logged in',
                            guild_ids=None if sets['version'] == 'MAIN' else [sets['srvcSrv']])
    @commands.bot_has_permissions(manage_webhooks=True, send_messages=True, embed_links=True, add_reactions=True, manage_messages=True, read_message_history=True)
    async def account(self, ctx):
        logmsg = str()
        ctx.usr, _ = self.repcog.User.find_by_args(ctx.author.id)
        if ctx.usr is None:
            ctx.usr, usrmsg = await self.repcog.User_add(ctx.author.id)
            logmsg += f'{usrmsg}\n'
            self.logger.info('Add {aa}USR{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=logmsg)))
        token = ctx.usr.token
        if token is None:
            await self.login(ctx)
            return

        async with AsyncVkExecuteRequestPool() as pool:
            usr_REQ = pool.add_call('users.get', ctx.usr.token, self.usr_call_attrs)
        usr_RESP = usr_REQ.result
        embed = compile_wall_embed(usr_RESP[0])

        buttons = [create_button(style=ButtonStyle.blue, label='Relogin')]
        action_row = create_actionrow(*buttons)
        ctx.msg = await ctx.send(content='You are logged in with this account', embed=embed, components=[action_row])
        try:
            button = await wait_for_component(self.client, components=action_row, check=lambda btn_ctx: btn_ctx.author_id == ctx.author_id, timeout=120.0)
        except TimeoutError:
            buttons = [create_button(style=ButtonStyle.blue, label='Relogin (timeout)', disabled=True)]
            action_row = create_actionrow(*buttons)
            await ctx.msg.edit(content='You are logged in with this account', embed=embed, components=[action_row])
        else:
            await button.defer(edit_origin=True)
            await self.login(ctx)

    async def login(self, ctx):
        if hasattr(ctx, 'msg'):
            await ctx.msg.edit(content='Check your DM for login link', embed=None, components=[])
        else:
            ctx.msg = await ctx.send(content='Check your DM for login link')

        key = Fernet.generate_key().decode("utf-8")
        buttons = [create_button(style=ButtonStyle.URL, label='Login', url=f'{sets["url"]}/oauth2/login?key={key}')]
        action_row = create_actionrow(*buttons)
        usr_msg = await ctx.author.send(content='Follow the link to login with your VK profile', components=[action_row])
        self.repcog.User.auth_data.append({"key": key, "usr_id": ctx.usr.id, "chn_id": ctx.channel.id, "msg_id": ctx.msg.id, "usr_msg_id": usr_msg.id})

    @ipc.server.route()
    async def authentication(self, data):
        try:
            auth_data = list(filter(lambda auth_data: auth_data['key'] == data.key, self.repcog.User.auth_data))[0]
        except IndexError:
            return "This link has been expired. Get a new one with `/subs link` command."

        usr, _ = self.repcog.User.find_by_args(auth_data['usr_id'])
        await usr.set_token(data.token)

        async with AsyncVkExecuteRequestPool() as pool:
            usr_REQ = pool.add_call('users.get', usr.token, self.usr_call_attrs)
        usr_RESP = usr_REQ.result
        embed = compile_wall_embed(usr_RESP[0])

        dc_usr = self.client.get_user(auth_data['usr_id'])
        dm = await dc_usr.create_dm()
        msg = dm.get_partial_message(auth_data['usr_msg_id'])
        await msg.edit(content="You are now logged in with this account", embed=embed, components=[])
        msg = self.client.get_channel(auth_data["chn_id"]).get_partial_message(auth_data['msg_id'])
        await msg.edit(content="You are now logged in with this account", embed=embed, components=[])

        self.repcog.User.auth_data.remove(auth_data)
        return 'All done! You can now close this tab.'


def setup(client):
    client.add_cog(Subscriptions(client))