"""Uji dashboard Streamlit dengan AppTest (menjalankan skrip app sungguhan)."""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402


def app(root):
    return AppTest.from_file(str(root / "streamlit_app.py"), default_timeout=120)


def test_starts_with_empty_state_then_demo(root):
    at = app(root).run()
    assert not at.exception, at.exception
    assert "Seberapa sering AI merekomendasikan Danau Toba?" in at.title[0].value
    assert not at.metric
    at.radio(key="mode").set_value("Contoh (demo)").run()
    assert not at.exception, at.exception
    labels = [m.label for m in at.metric]
    assert "SOV Danau Toba" in labels and "SOV Bali" in labels and "SOV Labuan Bajo" in labels
    assert any("SIMULASI" in w.value for w in at.warning)
    assert any("Setiap 100 sebutan Bali" in m.value for m in at.markdown)  # insight
    assert len(at.tabs) == 6


def test_focus_selection_recomputes(root):
    at = app(root).run()
    at.radio(key="mode").set_value("Contoh (demo)").run()
    at.selectbox(key="focus").set_value("bali").run()
    assert not at.exception, at.exception
    labels = [m.label for m in at.metric]
    assert "SOV Bali" in labels[0] and "Share of AI voice: Bali" in at.title[0].value


def test_run_new_audit_demo_provider(root):
    at = app(root).run()
    assert at.multiselect(key="providers").value == ["demo"]  # tanpa kunci API
    at.slider(key="max_q").set_value(3).run()
    at.button(key="run_btn").click().run()
    assert not at.exception, at.exception
    assert at.session_state["source"] == "run"
    assert len(at.session_state["df"]) == 1 * 3 * 2
    assert "SOV Danau Toba" in [m.label for m in at.metric]


def test_missing_key_disables_run(root):
    at = app(root).run()
    at.multiselect(key="providers").set_value(["anthropic"]).run()
    assert at.button(key="run_btn").disabled
    assert any("Kunci API belum ada" in w.value for w in at.sidebar.warning)


def test_clear_keys(root):
    at = app(root).run()
    at.multiselect(key="providers").set_value(["anthropic"]).run()
    at.text_input(key="key_anthropic").input("test-key-in-session").run()
    assert not at.button(key="run_btn").disabled
    at.button(key="clear_keys").click().run()
    assert "key_anthropic" not in at.session_state or not at.session_state["key_anthropic"]
