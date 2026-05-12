"""
tests/test_diff_filter.py
-------------------------
Tests for core/diff_generator.filter_diff.
"""
from core.diff_generator import filter_diff

SAMPLE_DIFF = """\
diff --git a/src/foo.py b/src/foo.py
index abc..def 100644
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,2 +1,3 @@
 x = 1
+y = 2
 z = 3
diff --git a/tests/test_foo.py b/tests/test_foo.py
index 111..222 100644
--- a/tests/test_foo.py
+++ b/tests/test_foo.py
@@ -1 +1,3 @@
 def test_x(): pass
+def test_y(): pass
diff --git a/src/bar.py b/src/bar.py
index 333..444 100644
--- a/src/bar.py
+++ b/src/bar.py
@@ -1 +1,2 @@
 a = 1
+b = 2
"""


def test_filter_excludes_specified_file():
    result = filter_diff(SAMPLE_DIFF, {"tests/test_foo.py"})
    assert "tests/test_foo.py" not in result
    assert "src/foo.py" in result
    assert "src/bar.py" in result


def test_filter_empty_exclude_set_returns_original():
    result = filter_diff(SAMPLE_DIFF, set())
    assert result == SAMPLE_DIFF


def test_filter_empty_diff_returns_empty():
    assert filter_diff("", {"tests/test_foo.py"}) == ""


def test_filter_exclude_all_files():
    result = filter_diff(
        SAMPLE_DIFF,
        {"src/foo.py", "tests/test_foo.py", "src/bar.py"},
    )
    assert result.strip() == ""


def test_filter_preserves_unrelated_blocks():
    result = filter_diff(SAMPLE_DIFF, {"src/foo.py"})
    assert "src/bar.py" in result
    assert "tests/test_foo.py" in result
    assert "src/foo.py" not in result
