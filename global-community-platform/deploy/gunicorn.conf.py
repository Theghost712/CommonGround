"""Production ASGI server: gunicorn managing uvicorn workers (HTTP + WebSockets).

Run from backend/:
    gunicorn -c ../deploy/gunicorn.conf.py config.asgi:application
"""
import multiprocessing
import os

bind = os.getenv("BIND", "127.0.0.1:8000")
worker_class = "uvicorn.workers.UvicornWorker"
# Async workers: one per core is a good start (each handles many connections).
workers = int(os.getenv("WEB_CONCURRENCY", multiprocessing.cpu_count()))
timeout = 60
graceful_timeout = 30
keepalive = 5
# Recycle workers periodically to contain slow memory growth.
max_requests = 5000
max_requests_jitter = 500
accesslog = "-"
errorlog = "-"
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1")
