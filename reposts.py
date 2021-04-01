import psycopg2
from psycopg2.extras import DictCursor

import asyncio

from aiovk.sessions import TokenSession
from aiovk.api import API as VKAPI
from aiovk.pools import AsyncVkExecuteRequestPool
from aiovk.longpoll import BotsLongPoll

from discord_webhook import DiscordWebhook

from colorama import Fore, Style

from rsc.config import sets, psql_sets
from rsc.functions import get_vk_info, compile_post_embed, print_traceback

with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
        SELECT server.token, 
        json_agg(json_build_object(
            'channel_id', subscription.channel_id,
            'webhook_url', channel.webhook_url, 
            'vk_id', subscription.vk_id, 
            'vk_type', subscription.vk_type, 
            'long_poll', subscription.long_poll, 
            'last_post_id', subscription.last_post_id,
            'token', subscription.token)) AS data
        FROM subscription LEFT JOIN channel ON channel.id = channel_id LEFT JOIN server ON server.id = server_id
        GROUP BY server.token
        """)
        subs = cur.fetchall()
dbcon.close

async def add_server(server):
    tasks = []
    vk = await get_vk_info()
    for info in server['data']:
        if info['long_poll'] == False:
            # print(server)
            tasks.append(loop.create_task(repost(info, server, vk)))
            print(f'Started {Fore.GREEN}CHANNEL {Fore.BLUE}{info["channel_id"]} {Fore.GREEN}WEBHOOK {Fore.BLUE}{info["webhook_url"][33:51]}\
    {Fore.GREEN}WALL {Fore.BLUE}{info["vk_type"]}{info["vk_id"]} {Fore.GREEN}LONGPOLL {Fore.BLUE}{info["long_poll"]}{Style.RESET_ALL}')
        else:
            print(info)
            # pass
            # tasks.append(loop.create_task(longpoll(info, vk)))
    await asyncio.wait(tasks)

async def repost(info, server, vk):
    if info['vk_type'] == 'g':
        info['vk_id'] = -info['vk_id']
    if info['vk_id'] == 215256291:
        me = True
    else: me = False
    while True:
        async with TokenSession(server['token']) as ses:
            vkapi = VKAPI(ses)
            wall = await vkapi.wall.get(owner_id=info['vk_id'], extended=1, count=1, fields='photo_max', v='5.130')
        print(me)
        if len(wall['items']) > 0:
            if 'is_pinned' in wall['items'][0]:
                if wall['items'][0]['is_pinned'] == 1:
                    async with TokenSession(server['token']) as ses:
                        vkapi = VKAPI(ses)
                        wall = await vkapi.wall.get(owner_id=info['vk_id'], extended=1, offset=1, count=1, fields='photo_max', v='5.130')
                    print(me)
            if len(wall['items']) > 0:
                if info['last_post_id'] != wall['items'][0]['id']:
                    webhook = DiscordWebhook(url=info['webhook_url'])
                    
                    post_embed, with_repost = compile_post_embed(post=wall, vk=vk)
                    webhook.add_embed(post_embed)

                    if with_repost != None:
                        async with TokenSession(server['token']) as ses:
                            vkapi = VKAPI(ses)
                            repost_embed, _ = compile_post_embed(await vkapi.wall.getById(posts=f"{with_repost['owner_id']}_{with_repost['id']}", 
                            extended=1, copy_history_depth=1, fields='photo_max', v='5.130'), vk)
                        webhook.add_embed(repost_embed)
                        # copy = items['copy_history'][0]
                        # rpost_url = f'https://vk.com/wall{copy["from_id"]}_{copy["id"]}'
                        # rpost_text = copy['text']
                        # embed.add_embed_field(
                        #     name = '↪️ Repost',
                        #     value = f'[**Open repost**]({rpost_url})\n>>> {rpost_text}'
                        # )

                    response = webhook.execute()

                    with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
                        with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                            cur.execute("UPDATE subscription SET last_post_id = %s WHERE channel_id = %s AND vk_id = @ %s AND vk_type = %s", (wall["items"][0]["id"], info['channel_id'], info['vk_id'], info['vk_type']))
                    dbcon.close()
                    info['last_post_id'] = wall['items'][0]['id']

                    print(f'Reposted {Fore.GREEN}POST {Fore.BLUE}{wall["items"][0]["id"]}    {Fore.GREEN}CHANNEL {Fore.BLUE}{info["channel_id"]} {Fore.GREEN}WEBHOOK {Fore.BLUE}{info["webhook_url"][33:51]}\
    {Fore.GREEN}WALL {Fore.BLUE}{info["vk_type"]}{abs(info["vk_id"])} {Fore.GREEN}LONGPOLL {Fore.BLUE}{info["long_poll"]}{Style.RESET_ALL}')
        await asyncio.sleep(60)


async def longpoll(info, vk):
    print(1)
    async with TokenSession(info['token']) as ses:
        print(2)
        long_poll = BotsLongPoll(ses, group_id=info['vk_id'])
        # print(await long_poll.wait())
        async for event in long_poll.iter():
            if event['type'] == 'wall_post_new':
                # async with TokenSession(server['token']) as ses:
                #     vkapi = VKAPI(ses)
                    # post_embed = compile_post_embed(event['object'], vk, await vkapi.groups.getById(group_id=info['vk_id'], fields='photo_max'))
                print(event)

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    for server in subs:
        try: loop.run_until_complete(add_server(server))
        except KeyboardInterrupt: pass
        finally: loop.close