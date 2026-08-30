from pathlib import Path


APP_SOURCE = Path(__file__).resolve().parents[1] / "app.py"


def test_collapsed_sidebar_keeps_a_visible_expand_control():
    source = APP_SOURCE.read_text(encoding="utf-8")

    assert '[data-testid="stExpandSidebarButton"]' in source
    assert '[data-testid="stHeader"] {display:block!important' in source
    assert 'pointer-events:auto!important' in source
    assert '#MainMenu,[data-testid="stHeader"]' not in source
    assert '#MainMenu,[data-testid="stToolbar"]' not in source
    assert '[data-testid="stToolbarActions"]' in source


def test_sidebar_can_remain_collapsed_until_the_user_reopens_it():
    source = APP_SOURCE.read_text(encoding="utf-8")

    assert "restoreSidebar" not in source
    assert "sidebar.querySelector('[data-testid=\"stBaseButton-headerNoPadding\"]')" not in source
