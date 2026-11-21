"""HWP 셀은 '안 여백 지정'(list_attr 0x10000)일 때만 자기 여백을 쓰고, 아니면 표 안 여백을 쓴다."""
from app.services.hwp_analyzer import effective_cell_margins

TABLE = {"inner_margins": [510, 510, 140, 140]}


def test_cell_without_own_margin_flag_uses_table_inner_margins():
    cell = {"list_attr": 0x20, "margins": [0, 0, 0, 0]}
    assert effective_cell_margins(cell, TABLE) == [510, 510, 140, 140]


def test_cell_with_own_margin_flag_keeps_its_margins_even_zero():
    assert effective_cell_margins({"list_attr": 0x10020, "margins": [100, 200, 30, 40]}, TABLE) == [100, 200, 30, 40]
    assert effective_cell_margins({"list_attr": 0x10020, "margins": [0, 0, 0, 0]}, TABLE) == [0, 0, 0, 0]


def test_missing_table_inner_margins_falls_back_to_cell_values():
    assert effective_cell_margins({"list_attr": 0x20, "margins": [1, 2, 3, 4]}, {}) == [1, 2, 3, 4]
