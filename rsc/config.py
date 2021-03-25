import os

sets = {
    "embedTitle": "Open post",
    "embedColor": 2590709,

    "errorTitle": "ERROR",
    "errorColor": 16711680,
}

dc_sets = {
    "token": os.environ.get("TOKEN"),
}

vk_sets = {
    "appId": 7797033,
    "redirectUri": "https://posthound.herokuapp.com/oauth2/redirect",
    "secureKey": os.environ.get("VK_SECURE_KEY"),
    "serviceKey": os.environ.get("VK_SERVICE_KEY"),
}

psql_sets = {
    "host": "ec2-99-80-200-225.eu-west-1.compute.amazonaws.com",
    "name": "d7n3srkcbcit8j",
    "user": "ngaweuxvtrxyze",
    "password": os.environ.get("POSTGRES_PASSWORD"),
}