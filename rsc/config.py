import os
import json
import asyncio
import platform
from dotenv import load_dotenv


load_dotenv()
envar = json.loads(os.environ.get("WALLPOST"))

sets = {
    "embedTitle": "Open post",
    "embedColor": 2590709,

    "errorTitle": "ERROR",
    "errorColor": 16711680,

    "srvcSrv": 817700627605749781,

    "ipcSecretKey": envar["ipc"],
    "dcToken": envar["dc"],
}

branch = envar.get("branch")
if branch == "MAIN":
    sets["url"] = "https://wallpostvk.herokuapp.com"
    
    sets["psqlUri"] = os.environ.get("DATABASE_URL")
    sets["srvcChnId"] = 823545137082531861
    sets['logChnId'] = 836705410630287451
    sets["version"] = 'MAIN'
else:
    if branch == "DEV":
        sets["url"] = 'https://dev894539-wallpostvk.herokuapp.com'
    elif branch is None:
        sets["url"] = "http://localhost:5000"
    
    sets["psqlUri"] = envar["db"]
    sets["srvcChnId"] = 843838814153343027
    sets['logChnId'] = 843838843262337024
    sets["version"] = 'DEV'

vk_sets = {
    "appId": 7797033,
    "redirectUri": f"{sets['url']}/oauth2/redirect",
    "secureKey": envar["vk"]["secure"],
    "serviceKey": envar["vk"]["service"],
}

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())