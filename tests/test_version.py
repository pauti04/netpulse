import netpulse


def test_version_is_set() -> None:
    assert isinstance(netpulse.__version__, str)
    assert netpulse.__version__
