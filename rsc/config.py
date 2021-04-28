import os
from urllib.parse import urlparse

sets = {
    "embedTitle": "Open post",
    "embedColor": 2590709,

    "errorTitle": "ERROR",
    "errorColor": 16711680,
}

dc_sets = {
    "token": os.environ.get("TOKEN"),
    "ipcSecretKey": os.environ.get("IPC_SECRET_KEY")
}

vk_sets = {
    "appId": 7797033,
    "redirectUri": "https://wallpostvk.herokuapp.com/oauth2/redirect",
    "secureKey": os.environ.get("VK_SECURE_KEY"),
    "serviceKey": os.environ.get("VK_SERVICE_KEY"),
}

psql_sets = {
    "uri": os.environ.get("DATABASE_URL")
}