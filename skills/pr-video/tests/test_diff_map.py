"""A unified diff becomes files, hunks and numbered rows that a code card can show."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import diff_map as dm

DIFF = """\
diff --git a/src/worker.py b/src/worker.py
index 1111111..2222222 100644
--- a/src/worker.py
+++ b/src/worker.py
@@ -10,4 +10,6 @@ def upload(path):
     client = connect()
-    client.put(path)
+    for attempt in range(3):
+        if client.put(path):
+            break
     return client
@@ -40,2 +42,2 @@ def close():
-    pass
+    client.close()

diff --git a/src/new_mod.py b/src/new_mod.py
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/src/new_mod.py
@@ -0,0 +1,2 @@
+RETRIES = 3
+BACKOFF_S = 0.5
diff --git a/old.txt b/old.txt
deleted file mode 100644
index 4444444..0000000
--- a/old.txt
+++ /dev/null
@@ -1,2 +0,0 @@
-gone
-too
\\ No newline at end of file
diff --git a/a/name.py b/b/name.py
similarity index 100%
rename from a/name.py
rename to b/name.py
diff --git a/logo.png b/logo.png
new file mode 100644
index 0000000..5555555
Binary files /dev/null and b/logo.png differ
diff --git a/uv.lock b/uv.lock
index 6666666..7777777 100644
--- a/uv.lock
+++ b/uv.lock
@@ -1 +1 @@
-old
+new
diff --git a/tests/test_worker.py b/tests/test_worker.py
index 8888888..9999999 100644
--- a/tests/test_worker.py
+++ b/tests/test_worker.py
@@ -1 +1,2 @@
 import worker
+assert worker
"""


@pytest.fixture(scope="module")
def files():
    return {f["path"]: f for f in dm.parse(DIFF)}


def test_every_file_is_found_with_its_status(files):
    assert {p: f["status"] for p, f in files.items()} == {
        "src/worker.py": "modified", "src/new_mod.py": "added", "old.txt": "deleted",
        "b/name.py": "renamed", "logo.png": "added", "uv.lock": "modified",
        "tests/test_worker.py": "modified",
    }


def test_a_rename_keeps_its_old_path(files):
    assert files["b/name.py"]["old_path"] == "a/name.py"
    assert files["b/name.py"]["hunks"] == []


def test_counts_added_and_removed_lines(files):
    assert (files["src/worker.py"]["added"], files["src/worker.py"]["removed"]) == (4, 2)
    assert (files["old.txt"]["added"], files["old.txt"]["removed"]) == (0, 2)


def test_rows_carry_old_and_new_line_numbers(files):
    rows = files["src/worker.py"]["hunks"][0]["rows"]
    assert rows[0] == {"kind": " ", "old": 10, "new": 10, "text": "    client = connect()"}
    assert rows[1] == {"kind": "-", "old": 11, "new": None, "text": "    client.put(path)"}
    assert rows[2] == {"kind": "+", "old": None, "new": 11, "text": "    for attempt in range(3):"}
    assert rows[-1] == {"kind": " ", "old": 12, "new": 14, "text": "    return client"}


def test_the_no_newline_marker_is_not_a_row(files):
    assert [r["text"] for r in files["old.txt"]["hunks"][0]["rows"]] == ["gone", "too"]


def test_hunk_header_keeps_the_enclosing_function(files):
    hunk = files["src/worker.py"]["hunks"][0]
    assert (hunk["old_start"], hunk["new_start"], hunk["context"]) == (10, 10, "def upload(path):")


def test_lockfiles_and_tests_are_flagged(files):
    assert files["uv.lock"]["kind"] == "generated"
    assert files["tests/test_worker.py"]["kind"] == "test"
    assert files["src/worker.py"]["kind"] == "code"


def test_totals_split_code_from_tests_and_generated():
    totals = dm.totals(dm.parse(DIFF))
    assert totals["files"] == 7
    assert totals["code"] == {"added": 6, "removed": 4}  # worker, new_mod, old.txt; renames and binaries count 0
    assert totals["test"] == {"added": 1, "removed": 0}
    assert totals["generated"] == {"added": 1, "removed": 1}


def test_card_rows_default_to_the_whole_hunk(files):
    hunk = files["src/worker.py"]["hunks"][0]
    assert dm.card_rows(hunk) == hunk["rows"]


def test_card_rows_slice_by_new_line_numbers_and_keep_deletions_in_place(files):
    hunk = files["src/worker.py"]["hunks"][0]
    picked = dm.card_rows(hunk, [11, 12])
    assert [(r["kind"], r["text"].strip()) for r in picked] == [
        ("-", "client.put(path)"), ("+", "for attempt in range(3):"), ("+", "if client.put(path):")]


def test_card_rows_of_a_deleted_file_use_old_numbers(files):
    hunk = files["old.txt"]["hunks"][0]
    assert [r["text"] for r in dm.card_rows(hunk, [2, 2], deleted=True)] == ["too"]


def test_find_file_names_the_close_paths_when_one_is_missing():
    with pytest.raises(KeyError, match="src/worker.py"):
        dm.find_file(dm.parse(DIFF), "src/workers.py")


def test_a_diff_with_spaces_in_a_path_reads_the_plus_line():
    text = ("diff --git a/my dir/x.py b/my dir/x.py\n--- a/my dir/x.py\n+++ b/my dir/x.py\n"
            "@@ -1 +1 @@\n-a\n+b\n")
    assert [f["path"] for f in dm.parse(text)] == ["my dir/x.py"]


def test_an_empty_diff_has_no_files():
    assert dm.parse("") == []


QUOTED = """\
diff --git "a/caf\\303\\251.txt" "b/caf\\303\\251.txt"
index 1111111..2222222 100644
--- "a/caf\\303\\251.txt"
+++ "b/caf\\303\\251.txt"
@@ -1 +1 @@
-old
+new
diff --git a/my file.txt b/my file.txt
index 1111111..2222222 100644
--- a/my file.txt\t
+++ b/my file.txt\t
@@ -1 +1 @@
-old
+new
diff --git "a/tab\\there.txt" "b/new \\"name\\".txt"
similarity index 100%
rename from "tab\\there.txt"
rename to "new \\"name\\".txt"
"""


def test_quoted_and_spaced_paths_come_out_as_the_real_names():
    files = dm.parse(QUOTED)
    assert [f["path"] for f in files] == ["café.txt", "my file.txt", 'new "name".txt']
    assert files[2]["old_path"] == "tab\there.txt"


BINARIES = """\
diff --git a/docs/old.png b/docs/old.png
deleted file mode 100644
index 1111111..0000000
Binary files a/docs/old.png and /dev/null differ
diff --git a/docs/new.png b/docs/new.png
new file mode 100644
index 0000000..2222222
Binary files /dev/null and b/docs/new.png differ
diff --git a/docs/same.png b/docs/same.png
index 3333333..4444444 100644
Binary files a/docs/same.png and b/docs/same.png differ
diff --git a/docs/a.png b/docs/b.png
similarity index 90%
rename from docs/a.png
rename to docs/b.png
index 5555555..6666666 100644
Binary files a/docs/a.png and b/docs/b.png differ
"""


def test_a_binary_file_keeps_its_status_and_is_marked_binary():
    files = {f["path"]: f for f in dm.parse(BINARIES)}
    assert {p: f["status"] for p, f in files.items()} == {
        "docs/old.png": "deleted", "docs/new.png": "added", "docs/same.png": "modified", "docs/b.png": "renamed"}
    assert all(f["binary"] for f in files.values())
    assert files["docs/b.png"]["old_path"] == "docs/a.png"


def test_a_text_file_is_not_binary(files):
    assert files["src/worker.py"]["binary"] is False
