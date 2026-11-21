from tests.unit.fakes import OsaDistance


def test_osa_distance() -> None:
    d = OsaDistance()
    assert d.distance("hroario", "horario", 2) == 1
    assert d.distance("abc", "abc", 0) == 0
    assert d.distance("abc", "xyz", 1) is None
