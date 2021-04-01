import discord
from discord.ext import commands

import psycopg2
import texttable
from cryptography.fernet import Fernet
from aiovk.exceptions import VkAPIError

import traceback
import sys

from rsc.config import sets, psql_sets
from rsc.functions import *
from rsc.errors import *

class Subscriptions(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.group(aliases=['subscriptions', 's'], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def sub(self, ctx):
        with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(f"SELECT token FROM server WHERE id = {ctx.guild.id}")
                vk_token = cur.fetchone()['token']
        dbcon.close

        if vk_token == None: 
            await sub_set(ctx)

        else:
            async with TokenSession(vk_token) as ses:
                vkapi = VKAPI(ses)
                user_embed = user_compile_embed((await vkapi.users.get(fields='photo_max,status,screen_name,followers_count,counters', v='5.130'))[0])
            await ctx.send(f'This is the account that is linked to **{ctx.guild.name}**.\nYou can change it with `sub set` command.', embed=user_embed)
        
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

        else: 
            print(str(error), str(error.original))
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

        if error_embed != None and dm == False:
            await ctx.send(embed=error_embed)

    @sub.command(aliases=['set', 's'])
    @commands.has_permissions(administrator=True)
    async def sub_set(self, ctx):
        with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(f"SELECT key, key_uuid FROM server WHERE id = {ctx.guild.id}")
                res = cur.fetchone()
                key, key_uuid = res['key'], res['key_uuid']
        dbcon.close

        vk = await get_vk_info()

        embed = discord.Embed(
            title = 'Authentication',
            url = f'https://posthound.herokuapp.com/oauth2/login?server_id={Fernet(key).encrypt(str(ctx.guild.id).encode()).decode()}&key_uuid={key_uuid}',
            description = 'Authenticate with your VK profile to be able to interact with VK walls.\n\n**Please, do not pass any arguments from link or link itself to 3rd parties. __It may result in security flaws.__**',
            color = sets["embedColor"]
        )
        embed.set_thumbnail(url=vk['photo'])
        embed.set_footer(text=vk['name'], icon_url=vk['photo'])

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

        else: 
            print(str(error), str(error.original))
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

        if error_embed != None and dm == False:
            await ctx.send(embed=error_embed)

    @sub.command(aliases=['add', 'a'])
    @commands.bot_has_permissions(manage_webhooks=True, add_reactions=True, manage_messages=True, read_message_history=True, send_messages=True)
    @commands.has_permissions(manage_webhooks=True)
    async def sub_add(self, ctx, vk_id: str=None, webhook_channel: discord.TextChannel=None):
        if webhook_channel == None: webhook_channel = ctx.channel
        ctx.webhook_channel = webhook_channel
        if vk_id == None: raise vkIdNotSpecifiedError
        elif len(await webhook_channel.webhooks()) == 10: raise MaximumWebhooksReached
        else:
            with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
                with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                    cur.execute("SELECT token FROM server WHERE id = %s", (ctx.guild.id,))
                    vk_token = cur.fetchone()['token']
            dbcon.close

            if vk_token == None: raise NotAuthenticated
            else: 

                if vk_id != 0:
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

                else: raise vkWallBlockedError

                if not 'deactivated' in groupi[0] and not 'deactivated' in useri[0]:
                    group_embed = group_compile_embed(groupi[0])
                    user_embed = user_compile_embed(useri[0])

                    messages = []
                    messages.append(await ctx.send(embed=group_embed))
                    messages.append(await ctx.send('React with ⬆️ for **group** wall\nReact with ❌ for cancel\nReact with ⬇️ for **user** wall'))
                    messages.append(await ctx.send(embed=user_embed))

                    for emoji in ['⬆️', '❌', '⬇️']:
                        await messages[1].add_reaction(emoji)
                    
                    try:
                        r, u = await self.client.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message == messages[1] and r.emoji in ['⬆️', '❌', '⬇️'], timeout=120.0)
                    except asyncio.TimeoutError:
                        await ctx.channel.delete_messages(messages)
                        messages = []
                        await ctx.send('❌ Cancelled (timeout)')
                    else:
                        await ctx.channel.delete_messages(messages)
                        messages = []

                        if r.emoji == '⬆️':
                            await setup_wall(ctx, 'add', messages, webhook_channel, 'g', groupi[0], group_embed)

                        elif r.emoji == '⬇️':
                            await setup_wall(ctx, 'add', messages, webhook_channel, 'u', useri[0], user_embed)

                        else:
                            await ctx.send('❌ Cancelled')

                elif not 'deactivated' in groupi[0]:
                    group_embed = group_compile_embed(groupi[0])
                    
                    messages = []
                    
                    await setup_wall(ctx, 'add', messages, webhook_channel, 'g', groupi[0], group_embed)

                elif not 'deactivated' in useri[0]:
                    user_embed = user_compile_embed(useri[0])

                    messages = []

                    await setup_wall(ctx, 'add', messages, webhook_channel, 'u', useri[0], user_embed)

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
                error_embed = set_error_embed(f'{ctx.webhook_channel.mention} already subscribed to this wall.')

            else:
                print(error)
                traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

        else: 
            print(str(error), str(error.original))
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

        if error_embed != None and dm == False:
            await ctx.send(embed=error_embed)

    @sub.command(aliases=['information', 'info', 'i'])
    @commands.bot_has_permissions(send_messages=True)
    @commands.has_permissions(manage_webhooks=True)
    async def sub_info(self, ctx, channel: discord.TextChannel=None):
        if channel == None: channel = ctx.channel
        with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT token FROM server WHERE id = %s", (ctx.guild.id,))
                vk_token = cur.fetchone()['token']
        dbcon.close

        if vk_token == None: raise NotAuthenticated
        else:
            with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
                with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                    cur.execute(f"SELECT vk_id, vk_type FROM subscription WHERE channel_id = {channel.id}")
                    subs = cur.fetchall()
            dbcon.close

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

            if len(subs) > 0:
                groups, users = '', ''
                for sub in subs:
                    if sub['vk_type'] == 'g': groups += f"{sub['vk_id']},"
                    else: users += f"{sub['vk_id']},"
                async with TokenSession(vk_token) as ses:
                    vkapi = VKAPI(ses)
                    if groups != '':
                        r_groups = vkapi.groups.getById(group_ids=groups, v='5.130')

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
                        r_users = vkapi.users.get(user_ids=users, fields='screen_name', v='5.130')

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
            else: raise noSubs

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
                error_embed = set_error_embed(f'No subscriptions for this channel.')
            
            else:
                print(str(error), str(error.original))
                traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

        else:
            print(error)
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

        if error_embed != None and dm == False:
            await ctx.send(embed=error_embed)

    @sub.command(aliases=['delete', 'del', 'd'])
    @commands.bot_has_permissions(manage_webhooks=True, add_reactions=True, manage_messages=True, read_message_history=True, send_messages=True)
    @commands.has_permissions(manage_webhooks=True)
    async def sub_del(self, ctx, vk_id: str=None, webhook_channel: discord.TextChannel=None):
        if webhook_channel == None: webhook_channel = ctx.channel
        ctx.webhook_channel = webhook_channel
        if vk_id == None: raise vkIdNotSpecifiedError
        else:
            with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
                with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                    cur.execute("SELECT token FROM server WHERE id = %s", (ctx.guild.id,))
                    vk_token = cur.fetchone()['token']
            dbcon.close

            if vk_token == None: raise NotAuthenticated
            else: 
                if vk_id != 0:
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
                else: raise vkWallBlockedError

                if not 'deactivated' in groupi[0] and not 'deactivated' in useri[0]:
                    with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
                        with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                            cur.execute(f"SELECT vk_id, vk_type FROM subscription WHERE channel_id = {webhook_channel.id} AND (vk_id = {groupi[0]['id']} OR vk_id = {useri[0]['id']})")
                            subs = cur.fetchall()
                    dbcon.close

                    if len(subs) == 2:
                        group_embed = group_compile_embed(groupi[0])
                        user_embed = user_compile_embed(useri[0])

                        messages = []
                        messages.append(await ctx.send(embed=group_embed))
                        messages.append(await ctx.send('React with ⬆️ for **group** wall\nReact with ❌ for cancel\nReact with ⬇️ for **user** wall'))
                        messages.append(await ctx.send(embed=user_embed))

                        for emoji in ['⬆️', '❌', '⬇️']:
                            await messages[1].add_reaction(emoji)
                        
                        try:
                            r, u = await self.client.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message == messages[1] and r.emoji in ['⬆️', '❌', '⬇️'], timeout=120.0)
                        except asyncio.TimeoutError:
                            await ctx.channel.delete_messages(messages)
                            messages = []
                            await ctx.send('❌ Cancelled (timeout)')
                        else:
                            await ctx.channel.delete_messages(messages)
                            messages = []

                            if r.emoji == '⬆️':
                                await setup_wall(ctx, 'del', messages, webhook_channel, 'g', groupi[0], group_embed)

                            elif r.emoji == '⬇️':
                                await setup_wall(ctx, 'del', messages, webhook_channel, 'u', useri[0], user_embed)

                            else:
                                await ctx.send('❌ Cancelled')
                    
                    elif len(subs) == 1:
                        if subs[0]['vk_type'] == 'g':
                            group_embed = group_compile_embed(groupi[0])

                            messages = []

                            await setup_wall(ctx, 'del', messages, webhook_channel, 'g', groupi[0], group_embed)
                        elif subs[0]['vk_type'] == 'u': 
                            user_embed = user_compile_embed(useri[0])

                            messages = []

                            await setup_wall(ctx, 'del', messages, webhook_channel, 'u', useri[0], user_embed)

                    else: raise notSub

                elif not 'deactivated' in groupi[0]:
                    with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
                        with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                            cur.execute(f"SELECT vk_id, vk_type FROM subscription WHERE channel_id = {webhook_channel.id} AND vk_id = {groupi[0]['id']}")
                            subs = cur.fetchall()
                    dbcon.close

                    if len(subs) == 1:
                        group_embed = group_compile_embed(groupi[0])

                        messages = []

                        await setup_wall(ctx, 'del', messages, webhook_channel, 'g', groupi[0], group_embed)

                    else: raise notSub

                elif not 'deactivated' in useri[0]:
                    with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
                        with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                            cur.execute(f"SELECT vk_id, vk_type FROM subscription WHERE channel_id = {webhook_channel.id} AND vk_id = {useri[0]['id']}")
                            subs = cur.fetchall()
                    dbcon.close

                    if len(subs) == 1:
                        user_embed = user_compile_embed(useri[0])

                        messages = []

                        await setup_wall(ctx, 'del', messages, webhook_channel, 'u', useri[0], user_embed)

                    else: raise notSub

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

            else: 
                print(error)
                traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

        else: 
            print(error)
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

        if error_embed != None and dm == False:
            await ctx.send(embed=error_embed)

def setup(client):
    client.add_cog(Subscriptions(client))