from rag import _terms


def test_terms_ignore_whitespace_between_chinese_characters() -> None:
    assert _terms("大学 物理") == ["大学", "学物", "物理"]
    assert _terms("大学\n物理") == ["大学", "学物", "物理"]
