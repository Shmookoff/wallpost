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
        if hasattr(ctx, 'channel_id'):
            return ctx.channel_id == sets["srvcChnId"]
        return ctx.channel.id == sets["srvcChnId"]
    return commands.check(predicate)


#Subscription

def compile_wall_embed(wall):
    embed = discord.Embed(color = sets["embedColor"])
    if wall['status'] != '':
        embed.add_field(
            name = 'Status',
            value = f'```{wall["status"]}```',
            inline = False
        )
    embed.add_field(
        name = 'Short address',
        value = f'`{wall["screen_name"]}`',
        inline = True
    )
    if 'name' in wall:
        embed.title = wall['name']
        embed.url = f'https://vk.com/public{wall["id"]}'
        embed.set_thumbnail(url=wall['photo_200'])
        embed.add_field(
            name = 'Members',
            value = f'`{wall["members_count"]}`',
            inline = True,
        )
        embed.set_footer(text='Group Wall', icon_url=vk['photo'])
    else:
        embed.title = f'{wall["first_name"]} {wall["last_name"]}'
        embed.url = f'https://vk.com/id{wall["id"]}'
        embed.set_thumbnail(url=wall['photo_max'])
        embed.add_field(
            name = 'Followers',
            value = f'`{wall["followers_count"] if "followers_count" in wall else "0"}`',
            inline = True
        )
        embed.set_footer(text='User Wall', icon_url=vk['photo'])
    embed.insert_field_at(
        index = 3,
        name = 'Verified',
        value = '✅' if wall['verified'] else '❎',
        inline = True
    )
    return embed

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
            for profile in post['profiles']:
                if profile['id'] == items['from_id']:
                    author = profile
                    break
            embed.set_author(
            name = f'{author["first_name"]} {author["last_name"]}',
            url = f'https://vk.com/id{author["id"]}',
            icon_url = author['photo_max']
            )
        else:
            for group in post['groups']:
                if group['id'] == -items['from_id']:
                    author = group
                    break
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
