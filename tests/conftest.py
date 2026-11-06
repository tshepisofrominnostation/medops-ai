"""Keep test runs out of the repository's real data files.

`app.notify` appends every simulated alert to `data/alerts.log`, which is a tracked
file. Without this, running the suite dirties the working tree with dry-run entries and
a reviewer sees log noise in the diff instead of the change. Redirect both the alert log
and the ticket store to a temp directory for the whole session; tests that need their
own store still override it themselves.
"""
import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_repo_data(tmp_path_factory):
    import app.notify as notify
    import app.persistence as persistence

    sandbox = tmp_path_factory.mktemp("medops-test-data")
    notify.ALERT_LOG = sandbox / "alerts.log"
    persistence.DB_PATH = sandbox / "tickets.json"
    yield sandbox
