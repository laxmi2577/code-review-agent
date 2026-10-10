from src.core.diff_parser import (
    detect_language,
    map_diff_to_functions,
    parse_unified_diff,
)
from src.models.enums import ChangeType, Language
from src.models.schemas import FunctionNode

SAMPLE_DIFF = """diff --git a/src/services/payment.py b/src/services/payment.py
index 1234567..89abcdef 100644
--- a/src/services/payment.py
+++ b/src/services/payment.py
@@ -10,6 +10,8 @@ def process_transaction(amount: float):
     validate_balance(amount)
+    log_audit_event(amount)
+    charge_card(amount)
     return True
"""

SAMPLE_MULTI_FILE_DIFF = """diff --git a/src/user.py b/src/user.py
new file mode 100644
--- /dev/null
+++ b/src/user.py
@@ -0,0 +1,5 @@
+def get_user(user_id):
+    return {"id": user_id}
diff --git a/src/old.ts b/src/old.ts
deleted file mode 100644
--- a/src/old.ts
+++ /dev/null
@@ -1,3 +0,0 @@
-export function deprecated(): void {
-}
"""


def test_detect_language():
    assert detect_language("src/main.py") == Language.PYTHON
    assert detect_language("web/App.tsx") == Language.TYPESCRIPT
    assert detect_language("script.js") == Language.JAVASCRIPT
    assert detect_language("main.go") == Language.GO
    assert detect_language("Service.java") == Language.JAVA
    assert detect_language("lib.rs") == Language.RUST
    assert detect_language("README.md") is None


def test_parse_unified_diff_single_hunk():
    hunks = parse_unified_diff(SAMPLE_DIFF)
    assert len(hunks) == 1
    hunk = hunks[0]
    assert hunk.file_path == "src/services/payment.py"
    assert hunk.language == Language.PYTHON
    assert hunk.change_type == ChangeType.MODIFIED
    assert hunk.old_start == 10
    assert hunk.new_start == 10
    assert hunk.new_end == 17  # 10 + 8 - 1 = 17
    assert "log_audit_event" in hunk.diff_content


def test_parse_unified_diff_multi_file():
    hunks = parse_unified_diff(SAMPLE_MULTI_FILE_DIFF)
    assert len(hunks) == 2

    # Added file
    added_hunk = hunks[0]
    assert added_hunk.file_path == "src/user.py"
    assert added_hunk.change_type == ChangeType.ADDED
    assert added_hunk.language == Language.PYTHON

    # Deleted file
    del_hunk = hunks[1]
    assert del_hunk.file_path == "src/old.ts"
    assert del_hunk.change_type == ChangeType.DELETED
    assert del_hunk.language == Language.TYPESCRIPT


def test_map_diff_to_functions():
    hunks = parse_unified_diff(SAMPLE_DIFF)
    assert len(hunks) == 1

    fn_inside = FunctionNode(
        file_path="src/services/payment.py",
        function_name="process_transaction",
        language=Language.PYTHON,
        start_line=8,
        end_line=20,
        code_snippet="def process_transaction...",
    )
    fn_outside = FunctionNode(
        file_path="src/services/payment.py",
        function_name="unrelated_helper",
        language=Language.PYTHON,
        start_line=50,
        end_line=60,
        code_snippet="def unrelated_helper...",
    )

    funcs_by_file = {
        "src/services/payment.py": [fn_inside, fn_outside]
    }

    mapped_hunks = map_diff_to_functions(hunks, funcs_by_file)
    assert len(mapped_hunks[0].affected_functions) == 1
    assert mapped_hunks[0].affected_functions[0].function_name == "process_transaction"
