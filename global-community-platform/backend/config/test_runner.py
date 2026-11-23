import shutil
import tempfile
import unittest

from django.core.cache import cache

from django.test.runner import DiscoverRunner
from django.test.utils import override_settings
from rest_framework.throttling import SimpleRateThrottle


class CacheClearingResult(unittest.TextTestResult):
    """Each test starts with an empty cache: rolled-back rows fire no signals, so
    cached block/mute sets (and throttle counters) must not leak between tests."""

    def startTest(self, test):
        cache.clear()
        super().startTest(test)


class TempMediaTestRunner(DiscoverRunner):
    """Run tests with MEDIA_ROOT in a throwaway directory and no login rate limit.

    Without the temp MEDIA_ROOT, tests that save FileFields write into the real
    backend/media/ folder and leave orphaned uploads behind after every run.
    The suite logs in far more than 10 times a minute, so the "auth" throttle is
    off by default; throttle tests patch THROTTLE_RATES to switch it back on.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        # Django's test client keeps DB connections open after each request (it
        # disconnects close_old_connections), so with psycopg's pool every test
        # thread would hold a pooled connection forever and the pool runs dry.
        # Production returns them after each request; tests use plain connections.
        from django.db import connections

        for alias in connections:
            connections[alias].settings_dict.get("OPTIONS", {}).pop("pool", None)
        self._media_root = tempfile.mkdtemp(prefix="commonground-test-media-")
        self._media_override = override_settings(MEDIA_ROOT=self._media_root, VIDEO_TRANSCODE="off", SCHEDULER_ENABLED=False)
        self._media_override.enable()
        self._throttle_rates = SimpleRateThrottle.THROTTLE_RATES
        SimpleRateThrottle.THROTTLE_RATES = {**self._throttle_rates, "auth": None, "uploads": None, "account_email": None, "calls": None}

    def teardown_databases(self, old_config, **kwargs):
        # WebSocket tests run database code in worker threads (database_sync_to_async).
        # Those threads' connections are never closed, and PostgreSQL refuses to drop
        # a database that still has sessions: the run passed but exited with an error.
        # End those leftover sessions (this test database only) before dropping it.
        from django.db import connections

        for alias in connections:
            connection = connections[alias]
            if connection.vendor != "postgresql":
                continue
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                )
        super().teardown_databases(old_config, **kwargs)

    def get_resultclass(self):
        return super().get_resultclass() or CacheClearingResult

    def teardown_test_environment(self, **kwargs):
        SimpleRateThrottle.THROTTLE_RATES = self._throttle_rates
        self._media_override.disable()
        shutil.rmtree(self._media_root, ignore_errors=True)
        super().teardown_test_environment(**kwargs)
