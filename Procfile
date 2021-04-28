bot: python -m app.bot
web: gunicorn --worker-class quart.worker.GunicornWorker app.server:app 