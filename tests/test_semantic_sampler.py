"""Tests for the light code-semantic convention sampler."""

from pathlib import Path

from ruleforge.analyzer import analyze_project


def _python_project(tmp_path: Path, func_names: list[str], class_names: list[str]) -> Path:
    """A python project whose sampled sources carry the given identifiers."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    src = tmp_path / "src"
    src.mkdir()
    per_file = 4
    chunks = [func_names[i : i + per_file] for i in range(0, len(func_names), per_file)]
    for idx, chunk in enumerate(chunks):
        body = "\n".join(f"def {n}(a, b):\n    return a\n" for n in chunk)
        body += "\n".join(f"\nclass {c}:\n    pass\n" for c in class_names)
        (src / f"mod{idx}.py").write_text(body)
    return tmp_path


def test_snake_case_functions_and_pascal_classes_detected(tmp_path):
    root = _python_project(
        tmp_path,
        [f"do_thing_{i}" for i in range(10)],
        [f"Widget{i}" for i in range(9)],
    )
    profile = analyze_project(root)
    assert "snake_case for functions and variables" in profile.conventions
    assert "PascalCase for classes" in profile.conventions


def test_camel_case_functions_detected(tmp_path):
    root = _python_project(tmp_path, [f"doThing{i}" for i in range(10)], [])
    profile = analyze_project(root)
    assert "camelCase for functions and variables" in profile.conventions


def test_mixed_naming_stays_silent(tmp_path):
    names = [f"do_thing_{i}" for i in range(5)] + [f"doThing{i}" for i in range(5)]
    root = _python_project(tmp_path, names, [])
    profile = analyze_project(root)
    assert not any("case for functions and variables" in c for c in profile.conventions)


def test_too_few_identifiers_stays_silent(tmp_path):
    root = _python_project(tmp_path, ["do_thing"], [])
    profile = analyze_project(root)
    assert not any("snake_case" in c for c in profile.conventions)


def test_tests_in_tests_dir_detected(tmp_path):
    root = _python_project(tmp_path, [f"do_thing_{i}" for i in range(9)], [])
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_mod.py").write_text("def test_it():\n    pass\n")
    profile = analyze_project(root)
    assert "tests live in tests/ directories" in profile.conventions


def test_colocated_tests_detected(tmp_path):
    root = _python_project(tmp_path, [f"do_thing_{i}" for i in range(9)], [])
    (root / "src" / "mod_test.py").write_text("def test_it():\n    pass\n")
    profile = analyze_project(root)
    assert "tests are co-located with sources" in profile.conventions


def test_js_camel_case_and_colocated_tests_detected(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "x"}\n')
    src = tmp_path / "src"
    src.mkdir()
    body = "\n".join(
        f"function doThing{i}(a) {{ return a; }}\n" for i in range(6)
    ) + "\n".join(f"const makeIt{i} = (a) => a;\n" for i in range(4))
    (src / "main.ts").write_text(body)
    (src / "main.test.ts").write_text("test('x', () => {})\n")
    profile = analyze_project(tmp_path)
    assert "camelCase for functions and variables" in profile.conventions
    assert "tests are co-located with sources" in profile.conventions


def test_js_tests_dir_detected(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "x"}\n')
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.ts").write_text(
        "\n".join(f"function doThing{i}(a) {{ return a; }}\n" for i in range(9))
    )
    tests_dir = tmp_path / "__tests__"
    tests_dir.mkdir()
    (tests_dir / "main.test.ts").write_text("test('x', () => {})\n")
    profile = analyze_project(tmp_path)
    assert "tests live in __tests__ or tests/ directories" in profile.conventions
