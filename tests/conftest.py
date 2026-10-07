import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data import load_clients, load_profiles, load_shares  # noqa: E402
from core.tagger import keyword_tag  # noqa: E402


@pytest.fixture(scope="session")
def clients():
    return load_clients()


@pytest.fixture(scope="session")
def client_by_name(clients):
    return {c.name: c for c in clients}


@pytest.fixture(scope="session")
def profiles():
    return {p.id: p for p in load_profiles()}


@pytest.fixture(scope="session")
def shares():
    return load_shares()


@pytest.fixture(scope="session")
def tagged(shares):
    return {s.share_id: keyword_tag(s.feedback_text) for s in shares if s.outcome == "rejected"}
