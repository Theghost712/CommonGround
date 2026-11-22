from django.apps import AppConfig


class SafetyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.safety"
    verbose_name = "Safety (blocks, mutes, reports)"

    def ready(self):
        from . import services  # noqa: F401  (connects cache-invalidation signals)
