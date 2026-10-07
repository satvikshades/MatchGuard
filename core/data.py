"""Load the mock data files into pydantic models."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List

from .models import Client, Profile, ShareRecord

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def load_clients(data_dir: Path = DATA_DIR) -> List[Client]:
    return [Client(**c) for c in json.loads((data_dir / "clients.json").read_text())]


def load_profiles(data_dir: Path = DATA_DIR) -> List[Profile]:
    return [Profile(**p) for p in json.loads((data_dir / "profiles.json").read_text())]


def load_shares(data_dir: Path = DATA_DIR) -> List[ShareRecord]:
    with open(data_dir / "share_history.csv", newline="") as f:
        return [ShareRecord(**{**r, "feedback_text": r.get("feedback_text") or ""}) for r in csv.DictReader(f)]


def load_taxonomy(data_dir: Path = DATA_DIR) -> Dict[str, dict]:
    return json.loads((data_dir / "reason_taxonomy.json").read_text())
