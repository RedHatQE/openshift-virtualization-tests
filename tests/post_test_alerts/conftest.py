import datetime

import pytest


@pytest.fixture()
def elapsed_seconds_since_suite_start(request):
    start_time = request.config._test_execution_start_time
    return max(int((datetime.datetime.now(tz=datetime.UTC) - start_time).total_seconds()), 1)
