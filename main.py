import discord
import vk
import psycopg2
import psycopg2.extras
from datetime import datetime
from discord.ext import commands, tasks
from config import settings

client = commands.Bot(command_prefix=settings['prefix'])

session = vk.AuthSession(access_token=settings['vkToken'], app_id='7779645')
vkapi = vk.API(session)

title = 'Открыть запись'
color = 2590709

@client.event
async def on_ready():
    await client.change_presence(status=discord.Status.idle, activity=discord.Game('Найтрейвен хахаха'))
    channel = client.get_channel(776262430174216212)
    repost.start(channel)
    print('Ready!')

@client.command()
async def hello(ctx):
    await ctx.send(f'Hello world!')

@tasks.loop(seconds=60)
async def repost(channel):
    post = vkapi.wall.get(owner_id=-(settings['wallId']), extended=False, count=1, v='5.130')
    dbcon = psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword'])

    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT value FROM data WHERE id = 1;")
        last_post = cur.fetchone()['value']
    if last_post != post['items'][0]['id']:
        items = post['items'][0]
        group = post['groups'][0]
        from_id = -(items['from_id'])
        post_id = items['id']
        # group_id = group['id']

        #Запись
        post_url = f'https://vk.com/wall-{from_id}_{post_id}'
        post_text = items['text']
        post_date = items['date']

        #Автор
        author_name = group['name']
        author_url = f'https://vk.com/public{from_id}'
        author_photo = group['photo_200']

        #ВК
        vk_group = vkapi.groups.getById(group_id=22822305, v='5.130')
        vk_name = vk_group[0]['name']
        vk_photo = vk_group[0]['photo_200']

        #Изображение
        is_there_a_photo = False
        if 'attachments' in items:                              #Если есть вложения
            for attachment in items['attachments']:             #Для каждого вложения
                if 'photo' in attachment:                       #Если вложение является изображением
                    is_there_a_photo = True                     #Вложения имеют изображение
                    hw = 0                                      #Размер изображения
                    image_url = ''                              #И так понятно
                    for size in attachment['photo']['sizes']:   #Для каждого размера изображения 
                        if size['width']*size['height'] > hw:   #Если размер изображения больше предыдущего
                            hw = size['width']*size['height']   #Присвоить размер текущему размеру
                            image_url = size['url']             #Присвоить ссылку на текущее изображение
                    break
        
        embed = discord.Embed(
            title = title,
            url = post_url,
            description = post_text,
            timestamp = datetime.fromtimestamp(post_date),
            colour = color
        )
        embed.set_author(
            name = author_name,
            url = author_url,
            icon_url = author_photo
        )
        embed.set_footer(
            text = vk_name,
            icon_url = vk_photo
        )
        
        if is_there_a_photo:
            embed.set_image(url = image_url)
        
        if 'copy_history' in items:
            copy = items['copy_history'][0]
            rfrom_id = -(copy['from_id'])
            rpost_id = copy['id']
            # rpost = vkapi.groups.getById(group_id=rfrom_id, v='5.130')

            rpost_url = f'https://vk.com/wall-{rfrom_id}_{rpost_id}'
            rpost_text = copy['text']
            # rpost_date = copy['date']
        
            # rauthor_name = rpost[0]['name']
            # rauthor_photo = rpost[0]['photo_200']
            # rauthor_url = f'https://vk.com/public{rfrom_id}'

            embed.add_field(
                name = '↪️ Репост',
                value = f'[**Открыть запись**]({rpost_url})\n>>> {rpost_text}'
            )

        await channel.send(embed=embed)

        with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(f"UPDATE data SET value = {post_id} WHERE id = 1;")
        dbcon.commit()
        dbcon.close()
        
        print(f'Post {post_url} reposted!')
    else:
        dbcon.commit() 
        dbcon.close()

client.run(settings['discordToken'])