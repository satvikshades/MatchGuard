"""Walks the README demo script through the real Streamlit app (headless, offline)."""
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("MATCHGUARD_OFFLINE", "1")
    monkeypatch.chdir(ROOT)
    backups = {}
    for name in ("learned_preferences.json", "override_log.csv"):
        f = DATA / name
        if f.exists():
            backups[name] = tmp_path / name
            shutil.copy(f, backups[name])
    (DATA / "learned_preferences.json").write_text('{"confirmed": {}, "dismissed": {}}')
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.run()
    yield at
    for name in ("learned_preferences.json", "override_log.csv"):
        f = DATA / name
        if name in backups:
            shutil.copy(backups[name], f)
        elif f.exists():
            f.unlink()


def button(at, label):
    return next(b for b in at.button if b.label == label)


def metric(at, label):
    return next(m for m in at.metric if m.label == label)


def all_text(at):
    return " ".join([m.value for m in at.markdown] + [w.value for w in at.warning] + [e.value for e in at.error]
                    + [s.value for s in at.success] + [i.value for i in at.info])


def test_demo_script(app):
    at = app
    assert not at.exception
    assert any("Running in offline mode (keyword tagger)" in w.value for w in at.sidebar.warning)

    # 1. Tab 4: avoidable rejection rate + simulation
    assert metric(at, "Rejections that broke a stated preference").value == "34.9%"
    assert metric(at, "Acceptance rate").value == "30.8%"
    assert metric(at, "Projected acceptance").value == "38.6%"
    assert metric(at, "Accepted profiles also blocked").value == "3"

    # 2. Tab 1: Priya - exclusions and the top 15
    assert at.sidebar.selectbox[0].value == "Priya"
    excluded_before = metric(at, "Profiles excluded").value
    assert excluded_before.endswith("of 200")
    send_boxes = [c for c in at.checkbox if c.key.startswith("chk_C01_")]
    assert len(send_boxes) == 15
    send_boxes[0].check().run()
    assert metric(at, "On send list").value == "1"

    # 3. Tab 2: add a smoker, see it blocked, override it
    manual = at.selectbox(key="manual_C01")
    smoker = next(o for o in manual.options if o.endswith("⚠ Smokes"))
    pid = smoker.split(" · ")[0]
    manual.select_index(manual.options.index(smoker)).run()
    button(at, "Add").click().run()
    assert "BLOCKED" in all_text(at) and "Smokes - client deal-breaker" in all_text(at)
    assert button(at, "Log override").disabled
    at.text_input(key=f"ovr_C01|{pid}").input("too short").run()
    assert button(at, "Log override").disabled  # < 15 chars
    at.text_input(key=f"ovr_C01|{pid}").input("Client said on the call she would meet him anyway").run()
    button(at, "Log override").click().run()
    assert "OVERRIDDEN" in all_text(at)
    log = (DATA / "override_log.csv").read_text()
    assert pid in log and "Smokes - client deal-breaker" in log

    # Pitch drafter for the PASS profile
    button(at, "Draft pitches for PASS profiles").click().run()
    drafts = [t for t in at.text_area if t.key and t.key.startswith("pitch_C01|")]
    assert len(drafts) == 1 and len(drafts[0].value.splitlines()) == 2
    first = drafts[0].value
    button(at, "Regenerate").click().run()
    assert not at.exception
    assert any("Draft ready to copy" in s.value for s in at.success)
    assert [t for t in at.text_area if t.key == drafts[0].key][0].value != first

    # 4. Tab 3: tag history, confirm Priya's learned deal-breaker, drinkers now excluded in Tab 1
    button(at, "Tag all historical feedback (83 rejections)").click().run()
    text = all_text(at)
    assert "Priya has rejected 2 profiles for drinking." in text
    button(at, "Client confirmed").click().run()
    assert not at.exception
    assert "Priya - drinking" in all_text(at)
    excluded_after = metric(at, "Profiles excluded").value
    assert int(excluded_after.split()[0]) > int(excluded_before.split()[0])
    assert "Drinks (socially) - learned deal-breaker" in " ".join(
        str(d.value.to_dict()) for d in at.dataframe)

    # 5. Tab 3: Rohan's reversal and Ananya's vague flag
    text = all_text(at)
    assert "Rohan rejected “career-focused / income” but accepted a similar profile on" in text
    assert "Do not auto-filter; discuss with client." in text
    assert "Ananya's rejections are mostly vague" in text
    assert "Client confirmed" not in [b.label for b in at.button if "Rohan" in (b.key or "")]

    # Reset leaves no learned rules behind
    button(at, "Reset learned deal-breakers").click().run()
    assert metric(at, "Profiles excluded").value == excluded_before
