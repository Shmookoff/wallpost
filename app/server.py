from flask import Flask, redirect, request
import requests
import psycopg2
import psycopg2.extras
import json
from cryptography.fernet import Fernet
from rsc.config import vk_sets, psql_sets

app = Flask(__name__)

@app.route('/')
def index():
    return 'WallPost'

@app.route('/oauth2/login')
def login():
    server_id = f"\"{request.args.get('server_id')}\""
    key_uuid = f"\"{request.args.get('key_uuid')}\""
    return redirect(f'https://oauth.vk.com/authorize?client_id={vk_sets["appId"]}&display=page&redirect_uri={vk_sets["redirectUri"]}&scope=friends,groups,offline&response_type=code&state={{"server_id": {server_id}, "key_uuid": {key_uuid}}}&v=5.130', code=302)

@app.route('/oauth2/redirect')
def get_code():
    code = request.args.get('code')
    try: response = requests.post(f'https://oauth.vk.com/access_token?client_id={vk_sets["appId"]}&client_secret={vk_sets["secureKey"]}&redirect_uri={vk_sets["redirectUri"]}&code={code}')
    except Exception as error: print(f'\n!!! ERROR !!!\n{error}\n!!! ERROR !!!\n')
    else:
        data = json.loads(request.args.get('state'))
        response = response.json()
        with psycopg2.connect(host=psql_sets["host"], dbname=psql_sets["name"], user=psql_sets["user"], password=psql_sets["password"]) as dbcon:
            with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT key FROM server WHERE key_uuid = %s", (data['key_uuid'],))
                key = cur.fetchone()['key']
                cur.execute("UPDATE server SET token = %s WHERE id = %s", (response['access_token'], Fernet(key).decrypt(data['server_id'].encode()).decode()))
        dbcon.close
        return 'OK!'
    
@app.route('/oauth2/getToken')
def get_token(code: str):
    pass

if __name__ == '__main__':
    app.run(debug=True) 