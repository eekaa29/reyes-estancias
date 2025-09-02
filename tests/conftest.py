import pytest
from django.conf import settings

@pytest.fixture(autouse=True)
def _celery_eager_settings(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.SITE_BASE_URL = "http://127.0.0.1:8000"
    return settings
