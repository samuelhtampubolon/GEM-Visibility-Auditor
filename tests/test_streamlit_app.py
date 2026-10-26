"""Uji dashboard Streamlit dengan AppTest (menjalankan skrip app sungguhan)."""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402


def app(root):
    return AppTest.from_file(str(root / "streamlit_app.py"), default_timeout=120)


def test_demo_view_renders(root):
    at = app(root).run()
    assert not at.exception, at.exception
    labels = [m.label for m in at.metric]
    assert "SOV Danau Toba" in labels and "SOV Bali" in labels and "SOV Labuan Bajo" in labels
    assert any("SIMULASI" in w.value for w in at.warning)
    assert len(at.tabs) == 6


def test_run_new_audit_demo_provider(root):
    at = app(root).run()
    at.radio(key="mode").set_value("Jalankan audit baru").run()
    assert not at.exception, at.exception
    assert at.multiselect(key="providers").value == ["demo"]  # tanpa kunci API
    at.slider(key="max_q").set_value(3).run()
    at.button(key="run_btn").click().run()
    assert not at.exception, at.exception
    assert at.session_state["source"] == "run"
    assert len(at.session_state["df"]) == 1 * 3 * 2
    assert "SOV Danau Toba" in [m.label for m in at.metric]


def test_missing_key_disables_run(root):
    at = app(root).run()
    at.radio(key="mode").set_value("Jalankan audit baru").run()
    at.multiselect(key="providers").set_value(["anthropic"]).run()
    assert at.button(key="run_btn").disabled
    assert any("Kunci API belum ada" in w.value for w in at.sidebar.warning)
