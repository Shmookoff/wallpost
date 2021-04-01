import discord
from discord.ext import commands

from discord_webhook import DiscordEmbed

import psycopg2
import asyncio
import aiohttp
from datetime import datetime

from aiovk.sessions import TokenSession
from aiovk.api import API as VKAPI

import traceback
import sys

from rsc.config import sets, psql_sets, vk_sets
from rsc.errors import subExists, WallClosed

def get_prefix(client, message):
    with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
        with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(f"SELECT prefix FROM server WHERE id = {message.guild.id}")
            prefix = cur.fetchone()['prefix']
        dbcon.close

    if prefix == None: 
        return '.'
    else: 
        return prefix

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

async def setup_wall(ctx, action, messages, channel, wall, walli, embed):
    messages.append(await ctx.send(f'Is this the wall you requested?\nReact with ✅ or ❌', embed=embed))

    for emoji in ['✅', '❌']:
        await messages[0].add_reaction(emoji)

    try:
        r, u = await ctx.bot.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message == messages[0] and r.emoji in ['✅', '❌'], timeout=120.0)
    except asyncio.TimeoutError:
        await ctx.channel.delete_messages(messages)
        messages = []
        await ctx.send('❌ Cancelled (timeout)')
    else:
        if r.emoji == '✅':
            await ctx.channel.delete_messages(messages)
            messages = []

            if wall == "g":
                name = walli['name']
                if not walli['is_closed'] == 0 and walli['is_member'] == 0:
                    raise WallClosed
            elif wall == "u":
                name = f'{walli["first_name"]} {walli["last_name"]}'
                if walli['can_access_closed'] == False:
                    print(walli)
                    raise WallClosed
            
            if action == 'add':

                with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
                    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        cur.execute(f"SELECT EXISTS(SELECT 1 FROM subscription WHERE vk_id = {walli['id']} AND vk_type = \'{wall}\' AND channel_id = {channel.id})")
                        if cur.fetchone()['exists'] == False:

                            # if wall == 'g':
                            #     if walli['is_admin'] == 1:
                            #         if walli['admin_level'] == 3: 
                            #             messages.append(await ctx.send(f'You are the administrator of **{name}**. You can enable \"long-poll\" reposting.\nThis means bla bla bla WIP'))
                            #             # vkapi.groups.setLongPollSettings(enabled=1, wall_post_new=1, v='5.130')
                            #             # long_poll = True
                            #             long_poll = False
                            #         else: long_poll = False
                            #     else: long_poll = False
                            # long_poll = False

                            cur.execute("SELECT EXISTS(SELECT 1 FROM channel WHERE id = %s)", (channel.id,))
                            if cur.fetchone()['exists'] == False:
                                webhook = await channel.create_webhook(name="WallPost VK")
                                cur.execute("INSERT INTO channel (id, webhook_url, server_id) VALUES(%s, %s, %s)", (channel.id, webhook.url, ctx.guild.id))

                            cur.execute("INSERT INTO subscription (vk_id, last_post_id, vk_type, long_poll, channel_id) VALUES(%s, %s, %s, %s, %s)", (walli['id'], 0, wall, False, channel.id))
                        else: raise subExists
                dbcon.close()
                
                await ctx.send(f'✅ Successfully subscribed {channel.mention} to **{name}** wall!')

            if action == 'del':
                with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
                    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        cur.execute(f"DELETE FROM subscription WHERE channel_id = {channel.id} AND vk_id = {walli['id']} AND vk_type = \'{wall}\'")

                        cur.execute("SELECT EXISTS(SELECT 1 FROM subscription WHERE channel_id = %s)", (channel.id,))
                        if cur.fetchone()['exists'] == False:
                            cur.execute("SELECT webhook_url FROM channel WHERE id = %s", (channel.id,))
                            async with aiohttp.ClientSession() as session:
                                await discord.Webhook.from_url(url=cur.fetchone()['webhook_url'], adapter=discord.AsyncWebhookAdapter(session)).delete()
                            cur.execute("DELETE FROM channel WHERE id = %s", (channel.id,))
                dbcon.close()

                await ctx.send(f'✅ Successfully unsubscrubed {channel.mention} from **{name}** wall!')

        else:
            await ctx.channel.delete_messages(messages)
            messages = []
            await ctx.send('❌ Cancelled')

def set_error_embed(d):
    error_embed = discord.Embed(title=sets["errorTitle"], color=sets["errorColor"], description=d)
    return error_embed

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

async def get_vk_info():
    async with TokenSession(vk_sets["serviceKey"]) as ses:
        vkapi = VKAPI(ses)
        vk_info = await vkapi.groups.getById(group_id=22822305, v='5.130')
    return {'name': vk_info[0]['name'], 'photo': vk_info[0]['photo_200']}

def compile_post_embed(post, vk, wall1=None):
    items = post['items'][0]
    
    embed = DiscordEmbed(
        title = sets["embedTitle"],
        url = f'https://vk.com/wall{items["from_id"]}_{items["id"]}',
        description = items['text'],
        timestamp = datetime.utcfromtimestamp(items['date']).isoformat(),
        color = sets["embedColor"]
    )

    if wall1 == None:
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
        embed.set_author(
            name = wall1['name'],
            url = f'https://vk.com/club{wall1["id"]}',
            icon_url = wall1['photo_max']
        )
    
    if 'attachments' in items:                              
        for attachment in items['attachments']:             
            if 'photo' in attachment:                       
                is_there_a_photo = True                     
                hw = 0                                      
                image_url = ''                              
                for size in attachment['photo']['sizes']:   
                    if size['width']*size['height'] > hw:   
                        hw = size['width']*size['height']   
                        image_url = size['url']             
                embed.set_image(url = image_url)
                break
    
    embed.set_footer(text=vk['name'], icon_url=vk['photo'])

    if 'copy_history' in items: with_repost = items['copy_history'][0]
    else: with_repost = None

    return embed, with_repost

def print_traceback(error):
    print(str(error), str(error.original))
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)