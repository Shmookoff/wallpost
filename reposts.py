import psycopg2
from psycopg2.extras import DictCursor

import asyncio

from rsc.config import sets, psql_sets
from rsc.functions import get_vk_info, compile_post_embed, print_traceback, Server, Channel, Subscription

with psycopg2.connect(psql_sets["uri"]) as dbcon:
    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
        SELECT server.id, server.token, 
            json_agg(json_build_object(
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
        GROUP BY server.id, server.token;
        """)

        servers = cur.fetchall()
dbcon.close


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    vk = loop.run_until_complete(get_vk_info())
    _servers = []

    for server in servers: 
        _server = Server(server['id'], server['token'])
        _servers.append(_server)

        for channel in server['channels']:
            _channel = Channel(_server, channel['channel_id'], channel['webhook_url'])

            for subscription in channel['subscriptions']:
                Subscription(_channel, subscription, vk, loop)

    try: loop.run_forever()
    except KeyboardInterrupt: pass
    except Exception as e:
        print(e)
    finally: 
        for server in _servers:
            for channel in server.channels:
                for subscription in channel.subscriptions:
                    subscription.task.cancel()
        loop.stop()