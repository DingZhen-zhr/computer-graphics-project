import importlib.metadata


def test_simplecadapi_version_is_pinned() -> None:
    assert importlib.metadata.version("simplecadapi") == "2.2.7"
