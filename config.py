import os
settings = {
    #Discord
    'bot': 'Notifications',
    'prefix': '.',
    'id': 816672552918974524,
    'discordToken': os.environ.get("TOKEN"),

    #VK
    'wallId': 125004421,
    'vkToken': os.environ.get("ACCESS_TOKEN"),

    #Postgres
    'dbHost': 'ec2-99-80-200-225.eu-west-1.compute.amazonaws.com',
    'dbName': 'd7n3srkcbcit8j',
    'dbUser': 'ngaweuxvtrxyze',
    'dbPassword': os.environ.get("POSTGRES_PASSWORD")
}