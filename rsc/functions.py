import discord
from discord.ext import commands

import psycopg2
import vk
import asyncio
import aiohttp

from rsc.config import sets, psql_sets, vk_sets
from rsc.errors import subExists

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

def authenticate(token):
    session = vk.AuthSession(access_token=token)
    vkapi = vk.API(session)
    return vkapi

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

async def setup(ctx, client, action, messages, channel, wall, walli, embed):
    messages.append(await ctx.send(f'Is this the wall you requested?\nReact with ✅ or ❌', embed=embed))

    for emoji in ['✅', '❌']:
        await messages[0].add_reaction(emoji)

    try:
        r, u = await client.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message == messages[0] and r.emoji in ['✅', '❌'], timeout=120.0)
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
            elif wall == "u":
                name = f'{walli["first_name"]} {walli["last_name"]}'
            
            if action == 'add':
                with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
                    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        cur.execute(f"SELECT EXISTS(SELECT 1 FROM subscription WHERE vk_id = {walli['id']} AND vk_type = \'{wall}\' AND channel_id = {channel.id})")
                        if cur.fetchone()['exists'] == False:
                            webhook = await channel.create_webhook(name=name)
                            cur.execute(f"INSERT INTO channel (id, server_id) VALUES({channel.id}, {ctx.guild.id}) ON CONFLICT DO NOTHING")
                            cur.execute(f"INSERT INTO subscription (vk_id, vk_type, webhook_url, channel_id) VALUES({walli['id']}, \'{wall}\', \'{webhook.url}\', {channel.id})")
                        else: raise subExists
                dbcon.close()
                
                await ctx.send(f'✅ Successfully subscribed {channel.mention} to **{name}** wall!')

            if action == 'del':
                with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
                    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        cur.execute(f"SELECT webhook_url FROM subscription WHERE channel_id = {channel.id} AND vk_id = {walli['id']} AND vk_type = \'{wall}\'")
                        async with aiohttp.ClientSession() as session:
                            await discord.Webhook.from_url(url=cur.fetchone()['webhook_url'], adapter=discord.AsyncWebhookAdapter(session)).delete()
                        cur.execute(f"DELETE FROM subscription WHERE channel_id = {channel.id} AND vk_id = {walli['id']} AND vk_type = \'{wall}\'")
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

def get_vk_info():
    vkapi = authenticate(vk_sets["serviceKey"])
    vk_info = vkapi.groups.getById(group_id=22822305, v='5.130')
    vk = {'name': vk_info[0]['name'], 'photo': vk_info[0]['photo_200']}
    return vk
