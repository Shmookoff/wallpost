import os
import asyncio


sets = {
    "embedTitle": "Open post",
    "embedColor": 2590709,

    "errorTitle": "ERROR",
    "errorColor": 16711680,

    "ipcSecretKey": os.environ.get("IPC_SECRET"),
    "dcToken": os.environ.get("DC_SECRET"),
    "psqlUri": os.environ.get("DATABASE_URL"),
}


branch = os.environ.get("HEROKU")
if branch == "MAIN":
    sets["url"] = "https://wallpostvk.herokuapp.com"
    
    sets["srvcChnId"] = 823545137082531861
    sets['logChnId'] = 836705410630287451
    sets["version"] = 'MAIN'
else:
    if branch == "DEV":
        sets["url"] = 'https://dev894539-wallpostvk.herokuapp.com'
    elif branch is None:
        sets["url"] = "http://localhost:5000"
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    sets["srvcChnId"] = 843838814153343027
    sets['logChnId'] = 843838843262337024
    sets["version"] = 'DEV'


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