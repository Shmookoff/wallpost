import os
settings = {
    #Discord
    'bot': 'Posthound',
    'discordToken': os.environ.get("TOKEN"),

    #VK
    'vkAppId': 7797033,
    'vkSecureKey': os.environ.get("VK_SECURE_KEY"),
    'vkServiceKey': os.environ.get("VK_SERVICE_KEY"),
    'vkRedirectUri': 'https://posthound.herokuapp.com/oauth2/redirect',

    #Postgres
    'dbHost': 'ec2-99-80-200-225.eu-west-1.compute.amazonaws.com',
    'dbName': 'd7n3srkcbcit8j',
    'dbUser': 'ngaweuxvtrxyze',
    'dbPassword': os.environ.get("POSTGRES_PASSWORD")
}