import os
import asyncio


sets = {
    "embedTitle": "Open post",
    "embedColor": 2590709,

    "errorTitle": "ERROR",
    "errorColor": 16711680,

    "ipcSecretKey": os.environ.get("IPC_SECRET_KEY"),
    "psqlUri": os.environ.get("DATABASE_URL"),
    "dcToken": os.environ.get("TOKEN"),
}

if "HEROKU" in os.environ:
    branch = os.environ.get("HEROKU")
    if branch == "MAIN":
        sets["url"] = "https://wallpostvk.herokuapp.com"
    elif branch == "DEV":
        sets["url"] = 'https://dev894539-wallpostvk.herokuapp.com'
else:
    sets["url"] = "http://localhost:5000"

vk_sets = {
    "appId": 7797033,
    "redirectUri": f"{sets['url']}/oauth2/redirect",
    "secureKey": os.environ.get("VK_SECURE_KEY"),
    "serviceKey": os.environ.get("VK_SERVICE_KEY"),
}

# db = create_async_engine(sets['psqlUri'])
# meta = MetaData(db)
# srv = Table('server', meta, autoload=True)
# chn = Table('channel', meta, autoload=True)
# sub = Table('subscription', meta, autoload=True)

if not ("HEROKU" in os.environ):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())