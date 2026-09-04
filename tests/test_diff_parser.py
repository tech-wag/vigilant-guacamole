from app.github_client.diff_parser import parse_patch

SAMPLE_PATCH = (
    "@@ -1,4 +1,6 @@\n"
    " import os\n"
    "+import sqlite3\n"
    " \n"
    " def get_user(user_id):\n"
    "-    return db.query(\"SELECT * FROM users\")\n"
    "+    query = f\"SELECT * FROM users WHERE id = {user_id}\"\n"
    "+    return db.execute(query)\n"
)


def test_parses_single_hunk_header():
    hunks = parse_patch(SAMPLE_PATCH)
    assert len(hunks) == 1
    hunk = hunks[0]
    assert hunk.old_start == 1 and hunk.old_lines == 4
    assert hunk.new_start == 1 and hunk.new_lines == 6


def test_classifies_add_remove_context_lines():
    hunks = parse_patch(SAMPLE_PATCH)
    types = [line.type for line in hunks[0].lines]
    assert types == ["context", "add", "context", "context", "remove", "add", "add"]


def test_line_numbers_track_old_and_new_independently():
    hunks = parse_patch(SAMPLE_PATCH)
    lines = {line.content: line for line in hunks[0].lines}

    added_import = lines["import sqlite3"]
    assert added_import.old_lineno is None
    assert added_import.new_lineno == 2

    removed_query = lines['    return db.query("SELECT * FROM users")']
    assert removed_query.new_lineno is None
    assert removed_query.old_lineno == 4


def test_multiple_hunks_in_one_patch():
    patch = (
        "@@ -1,2 +1,2 @@\n"
        "-old top\n"
        "+new top\n"
        "@@ -10,2 +10,3 @@\n"
        " context\n"
        "+new bottom\n"
    )
    hunks = parse_patch(patch)
    assert len(hunks) == 2
    assert hunks[0].old_start == 1
    assert hunks[1].old_start == 10


def test_empty_patch_returns_no_hunks():
    assert parse_patch("") == []


def test_no_newline_marker_is_ignored_not_misclassified():
    patch = "@@ -1,1 +1,1 @@\n-foo\n+bar\n\\ No newline at end of file\n"
    hunks = parse_patch(patch)
    assert len(hunks[0].lines) == 2
    assert [line.type for line in hunks[0].lines] == ["remove", "add"]
