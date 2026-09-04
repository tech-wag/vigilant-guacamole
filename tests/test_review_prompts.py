from types import SimpleNamespace

from app.prompts.review_prompts import build_diff_context


def _fake_file(filename, patch, status="modified", additions=1, deletions=0):
    return SimpleNamespace(filename=filename, patch=patch, status=status, additions=additions, deletions=deletions)


def test_build_diff_context_includes_filename_and_patch():
    files = [_fake_file("app/main.py", "@@ -1,1 +1,1 @@\n-a\n+b\n")]
    context = build_diff_context(files)
    assert "app/main.py" in context
    assert "@@ -1,1 +1,1 @@" in context


def test_build_diff_context_skips_files_with_no_patch():
    files = [
        _fake_file("image.png", None),
        _fake_file("app/main.py", "@@ -1,1 +1,1 @@\n-a\n+b\n"),
    ]
    context = build_diff_context(files)
    assert "image.png" not in context
    assert "app/main.py" in context


def test_build_diff_context_empty_when_nothing_reviewable():
    context = build_diff_context([_fake_file("image.png", None)])
    assert "no reviewable" in context.lower()
