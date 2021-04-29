import os

if "HEROKU" in os.environ:
    url = "https://wallpostvk.herokuapp.com/"
else:
    url = "http://localhost:5000/"

sets = {
    "embedTitle": "Open post",
    "embedColor": 2590709,

    "errorTitle": "ERROR",
    "errorColor": 16711680,

    "url": url,
    "ipcSecretKey": os.environ.get("IPC_SECRET_KEY"),
    "psqlUri": os.environ.get("DATABASE_URL"),
    "dcToken": os.environ.get("TOKEN"),
}

vk_sets = {
    "appId": 7797033,
    "redirectUri": f"{url}oauth2/redirect",
    "secureKey": os.environ.get("VK_SECURE_KEY"),
    "serviceKey": os.environ.get("VK_SERVICE_KEY"),
}