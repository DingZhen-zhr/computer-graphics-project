import pytest

from cad_agent.sandbox.guard import check_code, clean_env


@pytest.mark.parametrize("code,word", [
    ("import os", "import"),
    ("from os import path", "import"),
    ("x = open('a')", "open"),
    ("x = eval('1')", "eval"),
    ("exec('x = 1')", "exec"),
    ("x = compile('1', 'a', 'eval')", "compile"),
    ("x = y.__class__", "__class__"),
    ("x = __import__('os')", "__import__"),
    ("x = __builtins__", "__builtins__"),
    ("x = getattr(scad, 'make_box_rsolid')", "getattr"),
    ("x = globals()", "globals"),
    ("breakpoint()", "breakpoint"),
    ("x = input()", "input"),
])
def test_guard_rejects(code, word):
    assert any(word in p for p in check_code(code))


def test_guard_syntax_error_has_line():
    assert "第 2 行" in check_code("x = 1\nx = (")[0]


def test_guard_problems_have_line_numbers():
    problems = check_code("a = 1\nb = 2\nc = eval('1')")
    assert len(problems) == 1 and problems[0].startswith("第 3 行")


def test_guard_reports_every_problem():
    assert len(check_code("import os\nx = open('a')\ny = z.__dict__")) == 3


def test_guard_rejects_return_and_yield_at_top_level():
    assert any("return" in p for p in check_code("x = 1\nreturn x"))
    assert any("yield" in p for p in check_code("yield 1"))


def test_guard_accepts_modeling():
    assert check_code("base = scad.make_box_rsolid(width=w, height=1.0, depth=1.0)") == []
    code = (
        "_tools = [scad.make_cylinder_rsolid(radius=r, height=t + 2, bottom_face_center=(i * 10, 0, -1)) for i in range(n)]\n"
        "holes = scad.cut_rsolid(base, _tools)\n"
        "def _helper(a):\n    return a + 1\n"
    )
    assert check_code(code) == []
    assert check_code("x = ql.faces().where(ql.prop('geom.type', '==', 'PLANE')).exactly(1)") == []
    assert check_code("x = math.sin(math.radians(a))") == []


def test_guard_allows_return_inside_function():
    assert check_code("def _f(a):\n    return a\nx = _f(1)") == []


def test_clean_env():
    assert clean_env({"DEEPSEEK_API_KEY": "x", "PATH": "p", "my_token": "t"}, ["DEEPSEEK_API_KEY"]) == {"PATH": "p"}


def test_clean_env_removes_secret_looking_names_and_is_case_insensitive():
    env = {"A_SECRET": "1", "db_password": "2", "Api_Key": "3", "TOKENS": "4", "CUSTOM_NAME": "5", "SystemRoot": "C:\\Windows"}
    assert clean_env(env, ["custom_name"]) == {"SystemRoot": "C:\\Windows"}


def test_clean_env_does_not_modify_input():
    env = {"KEY": "1", "PATH": "p"}
    clean_env(env, [])
    assert env == {"KEY": "1", "PATH": "p"}
