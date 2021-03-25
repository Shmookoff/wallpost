import os
import multiprocessing
from multiprocessing import Process, log_to_stderr

def bot():
    os.system('py -m app.bot')
def server():
    os.system('py -m app.server')

bot_process = multiprocessing.Process(target=bot)
server_process = multiprocessing.Process(target=server)


if __name__ == '__main__':
    bot_process.start()
    server_process.start()