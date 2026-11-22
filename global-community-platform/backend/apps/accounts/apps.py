import atexit

from django.apps import AppConfig


def close_connection_pools():
    """Close psycopg connection pools before the interpreter shuts down.

    Otherwise the pool's worker threads are joined during finalisation and every
    management command (cron jobs included) ends with a PythonFinalizationError
    traceback on stderr, even though it succeeded.
    """
    from django.db import connections

    for connection in connections.all(initialized_only=True):
        close_pool = getattr(connection, "close_pool", None)
        if close_pool is not None:
            try:
                close_pool()
            except Exception:
                pass


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        atexit.register(close_connection_pools)
