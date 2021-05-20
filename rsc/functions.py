import discord
from discord.ext import commands

import asyncio
import aiovk

from datetime import datetime

from rsc.config import sets, vk_sets


#Staff

async def get_vk_info():
    async with aiovk.TokenSession(vk_sets["serviceKey"]) as ses:
        vkapi = aiovk.API(ses)
        vk_info = await vkapi.groups.getById(group_id=22822305, v='5.130')
    return {'name': vk_info[0]['name'], 'photo': vk_info[0]['photo_200']}
vk = asyncio.get_event_loop().run_until_complete(get_vk_info())

def check_service_chn():
    def predicate(ctx):
        print(hasattr(ctx, 'channel_id'))
        print()
        if hasattr(ctx, 'channel_id'):
            return ctx.channel_id == sets["srvcChnId"]
        return ctx.channel.id == sets["srvcChnId"]
    return commands.check(predicate)


#Subscription

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
def compile_post_embed(post, wall1=None):
    if wall1 is None:
        items = post['items'][0]
        embed = discord.Embed(
            title = sets["embedTitle"],
            url = f'https://vk.com/wall{items["from_id"]}_{items["id"]}',
            description = items['text'],
            timestamp = datetime.utcfromtimestamp(items['date']),
            color = sets["embedColor"]
        )
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
        items = post
        embed = discord.Embed(
            title = sets["embedTitle"],
            url = f'https://vk.com/wall{items["from_id"]}_{items["id"]}',
            description = items['text'],
            timestamp = datetime.utcfromtimestamp(items['date']),
            color = sets["embedColor"]
        )
        embed.set_author(
            name = wall1[0]['name'],
            url = f'https://vk.com/club{wall1[0]["id"]}',
            icon_url = wall1[0]['photo_max']
        )
    
    has_photo = False
    if 'attachments' in items:
        for attachment in items['attachments']:
            if attachment['type'] == 'photo':
                has_photo = True
                hw = 0
                image_url = ''
                for size in attachment['photo']['sizes']:
                    if size['width']*size['height'] > hw:
                        hw = size['width']*size['height']
                        image_url = size['url']
                embed.set_image(url = image_url)
                break

    if 'copy_history' in items: 
        copy = items['copy_history'][0]

        if copy['text'] != '':
            embed.add_field(
                name = '↪️ Repost',
                value = f'[**Open repost**](https://vk.com/wall{copy["from_id"]}_{copy["id"]})\n>>> {copy["text"]}'
            )
        else:
            embed.add_field(
                name = '↪️ Repost',
                value = f'[**Open repost**](https://vk.com/wall{copy["from_id"]}_{copy["id"]})'
            )
        
        if not has_photo:
            if 'attachments' in copy:
                for attachment in copy['attachments']:
                    if attachment['type'] == 'photo':
                        hw = 0
                        image_url = ''
                        for size in attachment['photo']['sizes']:
                            if size['width']*size['height'] > hw:
                                hw = size['width']*size['height']
                                image_url = size['url']
                        embed.set_image(url = image_url)
                        break

    embed.set_footer(text=vk['name'], icon_url=vk['photo'])

    return embed


#Errors

def set_error_embed(d):
    return discord.Embed(title=sets["errorTitle"], color=sets["errorColor"], description=d)

def add_command_and_example(ctx, error_embed):
    if ctx.name == 'subs':
        if ctx.subcommand_name == 'add':
            command, example = '`/subs add [wall_id] (channel)`', f'/subs add apiclub {ctx.channel.mention}\n/subs add 1'
        elif ctx.subcommand_name == 'info':
            command, example = '`/subs info (channel)`', f'/subs info {ctx.channel.mention}\n/subs info'
        elif ctx.subcommand_name == 'del':
            command, example = '`/subs del [wall_id] (channel)`', f'/subs del apiclub {ctx.channel.mention}\n/subs del 1'

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
