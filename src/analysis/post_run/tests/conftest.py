from datetime import datetime, timedelta

import pandas as pd
import pytest

from src.analysis.post_run.scenario_common import POD_COLUMN

T0 = datetime(2026, 7, 30, 5, 15, 0)


@pytest.fixture
def deliveries():
    """Build a deliveries frame from (msg_id, ordinal, seconds_after_T0, delayMs) rows."""

    def build(rows):
        return pd.DataFrame(
            [
                {
                    "msgId": m,
                    POD_COLUMN: f"pod-{o}",
                    "ordinal": o,
                    "sent": T0 + timedelta(seconds=s),
                    "delayMs": d,
                }
                for m, o, s, d in rows
            ]
        )

    return build


@pytest.fixture
def fanout():
    """One message delivered to several pods at the same publish time."""

    def build(msg, nodes, second, delay=5):
        return [(msg, o, second, delay) for o in nodes]

    return build
