from flask import Flask, redirect, request
import requests
import psycopg2
import psycopg2.extras
from cryptography.fernet import Fernet
from config import settings

app = Flask(__name__)
data = []

@app.route('/')
def index():
    return 'Posthound'

@app.route('/oauth2/login')
def login():
    server_id, key_uuid = request.args.get('server_id'), request.args.get('key_uuid')
    return redirect(f'https://oauth.vk.com/authorize?client_id={settings["vkAppId"]}&display=page&redirect_uri={settings["vkRedirectUri"]}&scope=friends,groups,offline&response_type=code&state={{"server_id":{server_id}, "key_uuid":{key_uuid}}}&v=5.130', code=302)

@app.route('/oauth2/redirect')
def get_code():
    code = request.args.get('code')
    try: response = requests.post(f'https://oauth.vk.com/access_token?client_id={settings["vkAppId"]}&client_secret={settings["vkSecureKey"]}&redirect_uri={settings["vkRedirectUri"]}&code={code}')
    except Exception as error: print(f'\n!!! ERROR !!!\n{error}\n!!! ERROR !!!\n')
    else:
        data = request.args.get('state')
        response = response.json()
        with psycopg2.connect(host=settings['dbHost'], dbname=settings['dbName'], user=settings['dbUser'], password=settings['dbPassword']) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT key FROM server WHERE key_uuid = %s", (data['key_uuid']))
                key = cur.fetchone()['key']
                cur.execute("UPDATE server SET vk_id = %s, token = %s WHERE id = %s", (response['user_id'], response['access_token'], Fernet(key).decrypt(data['server_id']).decode()))
        dbcon.close
        return 'OK!'
    
@app.route('/oauth2/getToken')
def get_token(code: str):
    pass

if __name__ == '__main__':
    app.run(debug=True) 