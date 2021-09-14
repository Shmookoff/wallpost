import discord
from discord.ext import commands, ipc
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option
from discord_slash.utils.manage_components import create_button, create_select, create_select_option, create_actionrow, wait_for_component
from discord_slash.model import ButtonStyle

import aiopg
from aiovk.pools import AsyncVkExecuteRequestPool
from asyncio.exceptions import TimeoutError

from psycopg2.extras import DictCursor

from copy import deepcopy
from cryptography.fernet import Fernet

from rsc.config import sets
from rsc.functions import compile_wall_embed, vk
from rsc.classes import SafeDict, VKRespWrapper
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

        self.groups_getById_attrs = {'fields': 'photo_200,status,screen_name,members_count,verified', 'v': '5.84'}
        self.users_get_attrs = {'fields': 'photo_max,status,screen_name,followers_count,verified', 'v': '5.84'}
        self.wall_get_attrs = {'count': 1, 'v': '5.84'}

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
                    _chn, _msg = _srv.Channel_init(chn['id'])
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
    async def sub_add(self, ctx: SlashContext, wall_id: str, channel: discord.TextChannel=None):
        logmsg = str()
        ctx.bot_usr, usrmsg = self.repcog.User.find_by_args(ctx.author.id)
        if ctx.bot_usr is None:
            ctx.bot_usr, usrmsg = await self.repcog.User_add(ctx.author.id)
        logmsg += f'{usrmsg}\n'
        if ctx.bot_usr.token is None:
            raise NotAuthenticated
        if channel is None:
            channel = ctx.channel
        
        reqs = list()
        vk_pool = AsyncVkExecuteRequestPool()
        # Req for walls
        reqs.append({'wall_REQ': vk_pool.add_call('groups.getById', ctx.bot_usr.token, self.groups_getById_attrs | {'group_id': wall_id}), 'ERR': None})
        reqs.append({'wall_REQ': vk_pool.add_call('users.get', ctx.bot_usr.token, self.users_get_attrs | {'user_ids': wall_id}), 'ERR': None})
        await vk_pool.execute()
        # Req for posts
        for req in reqs:
            if req['wall_REQ'].ok:
                req['wall_RESP'] = req['wall_REQ'].result
                if 'name' in req['wall_RESP'][0]:
                    req['id'] = -req['wall_RESP'][0]['id']
                else:
                    req['id'] = req['wall_RESP'][0]['id']
                req['post_REQ'] = vk_pool.add_call('wall.get', ctx.bot_usr.token, self.wall_get_attrs | {'owner_id': req['id']})
            else:
                req['ERR'] = req['wall_REQ'].error
        await vk_pool.execute()
        # Offset req for pinned posts
        for req in reqs:
            if not req['ERR']:
                if req['post_REQ'].ok:
                    req['post_RESP'] = req['post_REQ'].result
                    if len(req['post_RESP']['items']) > 0:
                        if req['post_RESP']['items'][0].get('is_pinned', False):
                            req['post_REQ'] = vk_pool.add_call('wall.get', ctx.bot_usr.token, self.wall_get_attrs | {'owner_id': req['id'], 'offset': 1})
                else:
                    req['ERR'] = req['post_REQ'].error
        await vk_pool.execute()
        # Set post manually if empty wall
        for req in reqs:
            if not req['ERR']:
                req['post_RESP'] = req['post_REQ'].result
                if len(req['post_RESP']['items']) == 0:
                    req['post_RESP'] = {'items': [{'id': 0}]}
        #Wrap
                wrapped = VKRespWrapper(req['wall_RESP'][0], req['post_RESP']['items'][0])
                if wrapped.type == 'grp':
                    grp = wrapped
                else:
                    usr = wrapped
            else:
                wrapped = VKRespWrapper(error=req['ERR'])
                if wrapped.type == 'grp':
                    grp = wrapped
                else:
                    usr = wrapped

        if (not grp.error) and (not usr.error):
            buttons = [create_button(
                    style=ButtonStyle.blue, label=grp.name, custom_id='grp'),
                create_button(
                    style=ButtonStyle.blue, label=usr.name if len(usr.name) <= 80 else f'{usr.name[:79]}…', custom_id='usr'),
                create_button(
                    style=ButtonStyle.red, label="Cancel", custom_id='cancel')]
            action_row = create_actionrow(*buttons)

            ctx.msg = await ctx.send(content='Select the wall', embeds=[grp.embed, usr.embed], components=[action_row])
            button = await wait_for_component(self.client, components=action_row, check=lambda btn_ctx: btn_ctx.author_id == ctx.author_id, timeout=120.0)
            await button.defer(edit_origin=True)

            if button.custom_id == 'grp':
                wrapped = grp
            elif button.custom_id == 'usr':
                wrapped = usr
            else:
                await ctx.msg.edit(content='❌ Cancelled', embeds=[], components=[])
                return
        elif not grp.error:
            wrapped = grp
        elif not usr.error:
            wrapped = usr
        else:
            raise CouldNotFindWall(grp.error, usr.error)

        buttons = [create_button(
                style=ButtonStyle.green, label='Yes', custom_id='yes'),
            create_button(
                style=ButtonStyle.red, label='No', custom_id='no')]
        action_row = create_actionrow(*buttons)
        if hasattr(ctx, 'msg'):
            await ctx.msg.edit(content='Is this the wall you requested?', embed=wrapped.embed, components=[action_row])
        else:
            ctx.msg = await ctx.send(content='Is this the wall you requested?', embed=wrapped.embed, components=[action_row])
        button = await wait_for_component(self.client, components=action_row, check=lambda btn_ctx: btn_ctx.author_id == ctx.author_id, timeout=120.0)
        await button.defer(edit_origin=True)

        if button.custom_id == 'yes':
            srv, srvmsg = self.repcog.Server.find_by_args(ctx.guild.id)
            logmsg += f'{srvmsg}\n'
            chn, chnmsg = srv.find_channel(channel.id)
            if chn is None:
                chn, chnmsg = await srv.Channel_add(channel.id)
            logmsg += f'\t{chnmsg}\n'

            subs, _ = chn.find_subs(wrapped.id, True)
            if len(subs) == 0:
                wall, wallmsg = self.repcog.Wall.find_by_args(wrapped.id)
                if wall is None:
                    wall, wallmsg = await self.repcog.Wall_add(wrapped.id, wrapped.post['id'])
                
                buttons = [create_button(
                        style=ButtonStyle.green, label='Yes', custom_id='yes'),
                    create_button(
                        style=ButtonStyle.red, label='No', custom_id='no')]
                action_row = create_actionrow(*buttons)
                await ctx.msg.edit(content=f'Would you like to set a message to be sent with new posts?', embeds=[], components=[action_row])
                button = await wait_for_component(self.client, components=action_row, check=lambda btn_ctx: btn_ctx.author_id == ctx.author_id, timeout=120.0)
                await button.defer(edit_origin=True)

                if button.custom_id == 'yes':
                    await ctx.msg.edit(content=f'Reply with the text you want to be in the notification message (255 chars max).\nSend `None` if you want the message to be empty.',
                        embeds=[], components=[])
                    m = await self.client.wait_for('message', check=
                        lambda m: m.reference is not None and m.reference.message_id == ctx.msg.id and m.author.id == ctx.author.id, timeout=120.0)
                    msg = m.content
                    await m.delete()
                else:
                    msg = None
                sub, submsg = await chn.Subscription_add(wall, ctx.bot_usr, msg)

                sub_embed = wrapped.embed.copy()
                sub_embed.add_field(
                    name='Added by',
                    value=self.client.get_user(sub.user.id).mention,
                    inline=False)
                sub_embed.add_field(
                    name='Notification message',
                    value=sub.msg if sub.msg is not None else 'None',
                    inline=False)
                
                logmsg += f'\t\t{submsg}\n{wallmsg}\n'
            else:
                raise SubExists
            await ctx.msg.edit(content=f'✅ Successfully subscribed {channel.mention} to this wall!', embeds=[sub_embed], components=[])
            self.logger.info('Add {aa}SUB{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=logmsg)))
        else:
            await ctx.msg.edit(content='❌ Cancelled', embeds=[], components=[])

    @cog_ext.cog_subcommand(base='subs', name='manage',
                            description='Manage Channel Subscriptions',
                            options=[create_option(
                                name='channel',
                                description='Default: current Channel',
                                option_type=7,
                                required=False)],
                                guild_ids=None if sets['version'] == 'MAIN' else [sets['srvcSrv']])
    @commands.bot_has_permissions(manage_webhooks=True, send_messages=True, embed_links=True, add_reactions=True, manage_messages=True, read_message_history=True)
    async def subs_mng(self, ctx: SlashContext, channel: discord.TextChannel=None):
        ctx.bot_usr, usrmsg = self.repcog.User.find_by_args(ctx.author.id)
        if ctx.bot_usr is None:
            ctx.bot_usr, usrmsg = await self.repcog.User_add(ctx.author.id)
        if ctx.bot_usr.token is None:
            raise NotAuthenticated
        logmsg = f'{usrmsg}\n'
        if channel is None:
            channel = ctx.channel
        ctx.webhook_channel = channel

        srv, srvmsg = self.repcog.Server.find_by_args(ctx.guild.id)
        logmsg += f'{srvmsg}\n'
        chn, chnmsg = srv.find_channel(channel.id)
        if chn is None:
            raise NoSubs

        select_options = list()
        walls = list()
        async with AsyncVkExecuteRequestPool() as vk_pool:
            for sub in chn.subscriptions:
                if sub.wall.id < 0:
                    walls.append({'wall_REQ': vk_pool.add_call('groups.getById', ctx.bot_usr.token, self.groups_getById_attrs | {'group_id': abs(sub.wall.id)})})
                else:
                    walls.append({'wall_REQ': vk_pool.add_call('users.get', ctx.bot_usr.token, self.users_get_attrs | {'user_ids': sub.wall.id})})
        for wall in walls:
            wall_REQ = wall['wall_REQ']
            if wall_REQ.ok:
                wall['wrapped'] = VKRespWrapper(wall_REQ.result[0])
                if len(wall['wrapped'].name) > 100:
                    wall['wrapped'].name = f'{wall["wrapped"].name[:99]}…'
                select_options.append(create_select_option(label=wall['wrapped'].name, emoji='🔘', value=str(wall['wrapped'].id), description=f"{wall['wrapped'].wall['screen_name']}"))
        select = create_select(options=select_options, placeholder='Select the Wall', min_values=1, max_values=1)
        action_row = create_actionrow(select)

        ctx.msg = await ctx.send(content='Select the Wall you want to manage', components=[action_row])
        dropdown = await wait_for_component(self.client, components=action_row, check=lambda btn_ctx: btn_ctx.author_id == ctx.author_id, timeout=120.0)
        await dropdown.defer(edit_origin=True)
        wall_id = int(dropdown.selected_options[0])

        subs, _ = chn.find_subs(wall_id, wall_type=True)
        sub = subs[0]
        for wall in walls:
            if wall_id == wall['wrapped'].id:
                wrapped = wall['wrapped']
                break

        sub_embed = discord.Embed.from_dict(deepcopy(wrapped.embed.to_dict()))
        sub_embed.add_field(
            name='Added by',
            value=self.client.get_user(sub.user.id).mention,
            inline=False)
        sub_embed.add_field(
            name='Notification message',
            value=sub.msg if sub.msg is not None else 'None',
            inline=False)

        buttons = [create_button(
                style=ButtonStyle.blue, label='Change notification message', emoji='📝', custom_id='change'),
            create_button(
                style=ButtonStyle.red, label='Delete subscription', emoji='🗑️', custom_id='delete')]
        action_row = create_actionrow(*buttons)

        await ctx.msg.edit(content='Subscription details', embeds=[sub_embed], components=[action_row])
        try:
            button = await wait_for_component(self.client, components=action_row, check=lambda btn_ctx: btn_ctx.author_id == ctx.author_id, timeout=120.0)
        except TimeoutError:
            buttons = [create_button(
                    style=ButtonStyle.blue, label='Change notification message (Timeout)', emoji='📝', disabled=True),
                create_button(
                    style=ButtonStyle.red, label='Delete subscription (Timeout)', emoji='🗑️', disabled=True)]
            action_row = create_actionrow(*buttons)

            await ctx.msg.edit(content='Subsctiption details', embeds=[sub_embed], components=[action_row])
        else:
            await button.defer(edit_origin=True)

            if button.custom_id == 'change':
                await ctx.msg.edit(content='Reply with the text you want to be in the notification message (255 chars max).\nSend `None` if you want the message to be empty.',
                    embeds=[], components=[])
                m = await self.client.wait_for('message', check=
                    lambda m: m.reference is not None and m.reference.message_id == ctx.msg.id and m.author.id == ctx.author.id, timeout=120.0)
                submsg = await sub.change_msg(m.content)
                await m.delete()
                sub_embed.set_field_at(5,
                    name='Notification message',
                    value=sub.msg if sub.msg is not None else 'None',
                    inline=False)
                await ctx.msg.edit(content='📝 Successfully changed the notification message!', embeds=[sub_embed], components=[])
                logmsg += f'\t{chnmsg}\n'
                logmsg += f'\t\t{submsg}\n'
                self.logger.info('Change msg {aa}SUB{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=logmsg)))
            else:
                if len(chn.subscriptions) == 1:
                    chnmsg = await chn.delete()
                    logmsg += f'\t{chnmsg}\n'
                else:
                    logmsg += f'\t{chnmsg}\n'
                    submsg = await sub.delete()
                    logmsg += f'\t\t{submsg}\n'

                wall, wallmsg = self.repcog.Wall.find_by_args(wrapped.id)
                if len(wall.subscriptions) == 0:
                    wallmsg = await wall.delete()
                logmsg += f'{wallmsg}\n'
                await ctx.msg.edit(content=f'🗑️ Successfully unsubscrubed {ctx.webhook_channel.mention} from this wall!', embeds=[wrapped.embed], components=[])
                self.logger.info('Del {aa}SUB{aa} {tttpy}\n{msg} {ttt}'.format_map(SafeDict(msg=logmsg)))
    
    @cog_ext.cog_subcommand(base='subs', name='account',
                            description='Login with VK and show account you are logged in',
                            guild_ids=None if sets['version'] == 'MAIN' else [sets['srvcSrv']])
    @commands.bot_has_permissions(manage_webhooks=True, send_messages=True, embed_links=True, add_reactions=True, manage_messages=True, read_message_history=True)
    async def account(self, ctx: SlashContext):
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