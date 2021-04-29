from quart import Quart, redirect, request
from discord.ext import ipc
import requests
import psycopg2
import json
from rsc.config import vk_sets, sets

def create_app():
    ipc_client = ipc.Client(secret_key = sets['ipcSecretKey'])
    app = Quart(__name__)
    return app

    @app.route('/')
    async def index():
        return 'WallPost'

    @app.route('/oauth2/login')
    async def login():
        temp_key = f"{request.args.get('key')}"
        return redirect(f'https://oauth.vk.com/authorize?client_id={vk_sets["appId"]}&display=page&redirect_uri={vk_sets["redirectUri"]}&scope=friends,groups,offline&response_type=code&state={temp_key}&v=5.130', code=302)

    @app.route('/oauth2/redirect')
    async def auth_redirect():
        code = request.args.get('code')
        response = requests.post(f'https://oauth.vk.com/access_token?client_id={vk_sets["appId"]}&client_secret={vk_sets["secureKey"]}&redirect_uri={vk_sets["redirectUri"]}&code={code}').json()

        response = await ipc_client.request(
            "authentication", key = request.args.get('state'), token = response['access_token']
        )

        return response

if __name__ == '__main__':
    app = create_app()
    app.run(debug=False) 