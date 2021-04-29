import discord
from discord.ext import commands, tasks, ipc

import psycopg2
import texttable
from cryptography.fernet import Fernet
from aiovk.exceptions import VkAPIError

from rsc.config import sets
from rsc.functions import *
from rsc.exceptions import *


class Subscriptions(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.loop = client.loop
        self.loop.create_task(self.ainit())

    async def ainit(self):
        self.vk = await get_vk_info()

        with psycopg2.connect(sets["psqlUri"]) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT id, token FROM server")
                for server in cur.fetchall():
                    _server = Server.init(server['id'], server['token'])

                    cur.execute("""
                    SELECT json_agg(json_build_object(
                                'channel_id', channel_id,
                                'webhook_url', webhook_url,
                                'subscriptions', s.subscriptions
                                )) as channels
                    FROM (
                        SELECT sb.channel_id, 
                            json_agg(json_build_object(
                                                    'vk_id', sb.vk_id,
                                                    'vk_type', sb.vk_type,
                                                    'long_poll', sb.long_poll,
                                                    'last_post_id', sb.last_post_id,
                                                    'token', sb.token
                                                    )) as subscriptions
                        FROM subscription sb
                        GROUP by sb.channel_id
                    ) s 
                    LEFT JOIN channel ON channel.id = channel_id 
                    LEFT JOIN server ON server.id = server_id
                    WHERE server.id = %s
                    GROUP BY server.id;
                    """, (server['id'],))
                    response = cur.fetchone()

                    if response is not None:
                        for channel in response['channels']:
                            _channel = Channel.init(_server, channel['channel_id'], channel['webhook_url'])

                            for subscription in channel['subscriptions']:
                                Subscription.init(_channel, subscription, self.vk, self.loop)
            
                    print("")
        dbcon.close


    @commands.group(aliases=['subscriptions', 's'], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def sub(self, ctx):
        vk_token = Server.find_by_args(ctx.guild.id).token
        if vk_token is None:
            await self.sub_set(ctx)
        else:
            async with TokenSession(vk_token) as ses:
                vkapi = VKAPI(ses)
                user_embed = user_compile_embed((await vkapi.users.get(fields='photo_max,status,screen_name,followers_count,counters', v='5.130'))[0])
            await ctx.send(f'**{ctx.guild.name}** is bound to this account.\nYou can change it with `sub set` command.', embed=user_embed)
        
    @sub.error
    async def sub_error(self, ctx, error):
        error_embed = None
        dm = False

        if isinstance(error, commands.BotMissingPermissions):
            if 'Send Messages' in str(error):
                dm = True
                error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')
                await ctx.message.author.send(embed=error_embed)
            else:
                error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')

        elif isinstance(error, commands.MissingPermissions):
            error_embed = set_error_embed(f'You are missing permission(s).\n\n> {error}')   

        if error_embed != None and dm == False:
            await ctx.send(embed=error_embed)
        else: 
            self.client.dispatch("command_error", ctx, error, force=True)

    @sub.command(aliases=['set', 's'])
    @commands.has_permissions(administrator=True)
    async def sub_set(self, ctx):
        key = Fernet.generate_key().decode("utf-8")
        Server.temp_data.append({"key": key, "server_id": ctx.guild.id, "channel_id": ctx.channel.id})
        embed = discord.Embed(
            title = 'Authentication',
            url = f'{sets["url"]}oauth2/login?key={key}',
            description = 'Authenticate with your VK profile to be able to use **WallPost VK**.',
            color = sets["embedColor"]
        )
        embed.set_thumbnail(url=self.vk['photo'])
        embed.set_footer(text=self.vk['name'], icon_url=self.vk['photo'])

        await ctx.send('Check your DM for an authentication link!')
        await ctx.author.send(embed=embed)

    @sub_set.error
    async def sub_set_error(self, ctx, error):
        error_embed = None
        dm = False

        if isinstance(error, commands.BotMissingPermissions):
            if 'Send Messages' in str(error):
                dm = True
                error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')
                await ctx.message.author.send(embed=error_embed)
            else:
                error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')

        elif isinstance(error, commands.MissingPermissions):
            error_embed = set_error_embed(f'You are missing permission(s).\n\n> {error}')   

        if error_embed != None and dm == False:
            await ctx.send(embed=error_embed)
        else: 
            self.client.dispatch("command_error", ctx, error, force=True)

    @sub.command(aliases=['add', 'a'])
    @commands.bot_has_permissions(manage_webhooks=True, add_reactions=True, manage_messages=True, read_message_history=True, send_messages=True)
    @commands.has_permissions(manage_webhooks=True)
    async def sub_add(self, ctx, vk_id: str=None, channel: discord.TextChannel=None):
        vk_token = Server.find_by_args(ctx.guild.id).token
        if vk_token is None: raise NotAuthenticated
        if vk_id is None: raise vkIdNotSpecifiedError
        if vk_id == '0': raise vkWallBlockedError
        if channel is None: channel = ctx.channel
        if len(await channel.webhooks()) == 10: raise MaximumWebhooksReached
        ctx.webhook_channel = channel
        messages = []


        async with TokenSession(vk_token) as ses:
            vkapi = VKAPI(ses)

            try: groupi = await vkapi.groups.getById(group_id=vk_id, fields="status,description,members_count", v='5.130')
            except VkAPIError as error:
                if error.error_code == 100:
                    groupi = [{'deactivated': True}]
            
            try: useri = await vkapi.users.get(user_ids=vk_id, fields='photo_max,status,screen_name,followers_count,counters', v='5.130')
            except VkAPIError as error:
                if error.error_code == 113:
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

        else: raise vkWallBlockedError

    @sub_add.error
    async def sub_add_error(self, ctx, error):
        error_embed = None
        dm = False

        if isinstance(error, commands.BotMissingPermissions):
            if 'Send Messages' in str(error):
                dm = True
                error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')
                await ctx.message.author.send(embed=error_embed)
            else:
                error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')

        elif isinstance(error, commands.MissingPermissions):
            error_embed = set_error_embed(f'You are missing permission(s).\n\n> {error}')

        elif isinstance(error, commands.ChannelNotFound):
            error_embed = set_error_embed(f'Channel is not found.\n\n> Please, pass in `[Channel Mention]` as **Channel Mention** from current server.')
            add_command_and_example(ctx, error_embed, f'`sub add [VK Wall] (Channel Mention)`', f'.s a 1')

        elif isinstance(error, commands.BadArgument):
            error_embed = set_error_embed(f'One or more arguments are invalid.\n\n> Please, pass in `[Channel Mention]` as **Channel Mention** and `[VK Wall]` as **String**.')
            add_command_and_example(ctx, error_embed, f'`sub add [VK Wall] (Channel Mention)`', f'.s a 1')

        elif isinstance(error, commands.CommandInvokeError):
            error = error.original

            if isinstance(error, NotAuthenticated):
                error_embed = set_error_embed(f'You aren\'t authenticated.\n\n> Run `sub` command to link your VK profile.')

            elif isinstance(error, vkIdNotSpecifiedError):
                error_embed = set_error_embed(f'`[VK Wall]` is not specified.\n\n> Please, specify `[VK Wall]` as **String**.')
                add_command_and_example(ctx, error_embed, f'`sub add [VK Wall] (Channel Mention)`', f'.s a 1')

            elif isinstance(error, vkWallBlockedError):
                error_embed = set_error_embed(f'`[VK Wall]` is invalid.\n\n> Wall **{ctx.args[2]}** may be blocked, deactivated, deleted or it may not exist.')

            elif isinstance(error, MaximumWebhooksReached):
                error_embed = set_error_embed(f'Maximum number of webhooks reached (10).\n> Try removing a webhook from {ctx.webhook_channel.mention}.')

            elif isinstance(error, WallClosed):
                error_embed = set_error_embed(f'Wall is closed\n\n> Your VK account doesn\'t have access to this closed wall.')

            elif isinstance(error, subExists):
                error_embed = set_error_embed(f'{ctx.webhook_channel.mention} is already subscribed to this wall.')

        if error_embed != None and dm == False:
            await ctx.send(embed=error_embed)
        else: 
            self.client.dispatch("command_error", ctx, error, force=True)

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
            raise noSubs
        else:
            subs = chn.subscriptions
        if len(subs) == 0: raise noSubs

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
            if sub.type == 'g': groups += f"{abs(sub.id)},"
            else: users += f"{abs(sub.id)},"
        async with TokenSession(vk_token) as ses:
            vkapi = VKAPI(ses)
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
    async def sub_info_error(self, ctx, error):
        error_embed = None
        dm = False

        if isinstance(error, commands.BotMissingPermissions):
            if 'Send Messages' in str(error):
                dm = True
                error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')
                await ctx.message.author.send(embed=error_embed)
            else:
                error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')

        elif isinstance(error, commands.MissingPermissions):
            error_embed = set_error_embed(f'You are missing permission(s).\n\n> {error}')

        elif isinstance(error, commands.ChannelNotFound) or isinstance(error, commands.BadArgument):
            error_embed = set_error_embed(f'Channel is not found.\n\n> Please, pass in `[Channel Mention]` as **Channel Mention** from current server.')
            add_command_and_example(ctx, error_embed, f'`sub info (Channel Mention)`', f'.s i')

        elif isinstance(error, commands.CommandInvokeError):
            error = error.original
            if isinstance(error, NotAuthenticated):
                error_embed = set_error_embed(f'You aren\'t authenticated.\n\n> Run `sub` command to link your VK profile.')

            elif isinstance(error, noSubs):
                error_embed = set_error_embed(f'{ctx.webhook_channel.mention} doesn\'t have any subscriptions.')

        if error_embed != None and dm == False:
            await ctx.send(embed=error_embed)
        else:
            self.client.dispatch("command_error", ctx, error, force=True)

    @sub.command(aliases=['delete', 'del', 'd'])
    @commands.bot_has_permissions(manage_webhooks=True, add_reactions=True, manage_messages=True, read_message_history=True, send_messages=True)
    @commands.has_permissions(manage_webhooks=True)
    async def sub_del(self, ctx, vk_id: str=None, webhook_channel: discord.TextChannel=None):
        vk_token = Server.find_by_args(ctx.guild.id).token
        if vk_token == None: raise NotAuthenticated
        if vk_id == None: raise vkIdNotSpecifiedError
        if vk_id == 0: raise vkWallBlockedError
        if webhook_channel == None: webhook_channel = ctx.channel
        ctx.webhook_channel = webhook_channel
        chn = Server.find_by_args(ctx.guild.id).find_channel(webhook_channel.id)
        if chn is None: raise notSub
        messages = []



        async with TokenSession(vk_token) as ses:
            vkapi = VKAPI(ses)

            try: groupi = await vkapi.groups.getById(group_id=vk_id, fields="status,description,members_count", v='5.130')
            except VkAPIError as error:
                if error.error_code == 100:
                    groupi = [{'deactivated': True}]

            try: useri = await vkapi.users.get(user_ids=vk_id, fields='photo_max,status,screen_name,followers_count,counters', v='5.130')
            except VkAPIError as error:
                if error.error_code == 113:
                    useri = [{'deactivated': True}]

        if not 'deactivated' in groupi[0] and not 'deactivated' in useri[0]:
            subs = chn.find_subs(groupi[0]['id'])
            if len(subs) == 0: raise notSub

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
            if len(subs) == 0: raise notSub

            await self.setup_wall(ctx, 'del', messages, webhook_channel, 'g', groupi[0], group_compile_embed(groupi[0]))

        elif not 'deactivated' in useri[0]:
            subs = chn.find_subs(groupi[0]['id'])
            if len(subs) == 0: raise notSub

            await self.setup_wall(ctx, 'del', messages, webhook_channel, 'u', useri[0], user_compile_embed(useri[0]))

        else: raise vkWallBlockedError

    @sub_del.error
    async def sub_del_error(self, ctx, error):
        error_embed = None
        dm = False

        if isinstance(error, commands.BotMissingPermissions):
            if 'Send Messages' in str(error):
                dm = True
                error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')
                await ctx.message.author.send(embed=error_embed)
            else:
                error_embed = set_error_embed(f'Bot is missing permission(s).\n\n> {error}')

        elif isinstance(error, commands.MissingPermissions):
            error_embed = set_error_embed(f'You are missing permission(s).\n\n> {error}')

        elif isinstance(error, commands.ChannelNotFound):
            error_embed = set_error_embed(f'Channel is not found.\n\n> Please, pass in `[Channel Mention]` as **Channel Mention** from current server.')
            add_command_and_example(ctx, error_embed, f'`sub del [VK Wall] (Channel Mention)`', f'.s d 1')

        elif isinstance(error, commands.BadArgument):
            error_embed = set_error_embed(f'One or more arguments are invalid.\n\n> Please, pass in `[Channel Mention]` as **Channel Mention** and `[VK Wall]` as **String**.')
            add_command_and_example(ctx, error_embed, f'`sub del [VK Wall] (Channel Mention)`', f'.s d 1')

        elif isinstance(error, commands.CommandInvokeError):
            error = error.original

            if isinstance(error, NotAuthenticated):
                error_embed = set_error_embed(f'You aren\'t authenticated.\n\n> Run `sub` command to link your VK profile.')

            elif isinstance(error, vkIdNotSpecifiedError):
                error_embed = set_error_embed(f'`[VK Wall]` is not specified.\n\n> Please, specify `[VK Wall]` as **String**.')
                add_command_and_example(ctx, error_embed, f'`sub del [VK Wall] (Channel Mention)`', f'.s d 1')

            elif isinstance(error, vkWallBlockedError):
                error_embed = set_error_embed(f'`[VK Wall]` is invalid.\n\n> Wall **{ctx.args[2]}** may be blocked, deactivated, deleted or it may not exist.')

            elif isinstance(error, notSub):
                error_embed = set_error_embed(f'{ctx.webhook_channel.mention} isn\'t subscribed to wall **{ctx.args[2]}**.')

        if error_embed != None and dm == False:
            await ctx.send(embed=error_embed)
        else: 
            self.client.dispatch("command_error", ctx, error, force=True)


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
                    if _channel is None:
                        _channel = await Channel.add(Server.find_by_args(ctx.guild.id), channel)

                    if _channel.find_subs(walli['id'], wall) is None:
                        long_poll = False
                        if wall == 'g':
                            if walli['is_admin'] == 1:
                                if walli['admin_level'] == 3:
                                    messages.append(await ctx.send(f'You are the administrator of **{name}**. You can enable \"long-poll\" reposting.\nThis means bla bla bla WIP'))
                                    # vkapi.groups.setLongPollSettings(enabled=1, wall_post_new=1, v='5.130')
                                    # long_poll = True

                        _sub = Subscription.add(_channel, {'vk_id': abs(walli['id']), 'vk_type': wall, 'long_poll': long_poll, 'last_post_id': 0, 'token': _channel.server.token}, self.vk, self.loop)
                    else: raise subExists

                    await ctx.send(f'✅ Successfully subscribed {channel.mention} to **{name}** wall!')

                if action == 'del':
                    _channel = Server.find_by_args(ctx.guild.id).find_channel(channel.id)
                    _sub = _channel.find_subs(walli['id'], wall)
                    _sub.delete()

                    if len(_channel.subscriptions) == 0:
                        await _channel.delete()

                    await ctx.send(f'✅ Successfully unsubscrubed {channel.mention} from **{name}** wall!')

            else:
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
        server.token = data.token

        async with TokenSession(server.token) as ses:
            vkapi = VKAPI(ses)
            await (self.client.get_channel(temp_data['channel_id']).send(f"**{self.client.get_guild(server.id).name}** is now bound to this account.\nYou can change it with `sub set` command.", embed = user_compile_embed((await vkapi.users.get(fields='photo_max,status,screen_name,followers_count,counters', v='5.130'))[0])))
        
        with psycopg2.connect(sets["psqlUri"]) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("UPDATE server SET token = %s WHERE id = %s", (server.token, server.id))
        dbcon.close

        Server.temp_data.remove(temp_data)

        return 'Your account is now bound to the server. You can now close this tab.'


def setup(client):
    client.add_cog(Subscriptions(client))