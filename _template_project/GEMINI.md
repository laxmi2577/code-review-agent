# Antigravity Agent Core Directive & Token Preservation Engine

This workspace operates under strict **Spec-Driven & Token-Minimization Protocols**.
Every agent operating in this project MUST strictly follow these rules.

---

## ⚡ 1. Token Preservation Directives (CRITICAL)

1. **Check the Index First**: Before searching for files, classes, or functions, inspect `CODEBASE_MAP.md`. NEVER execute broad, recursive repo greps if the symbol is in the map.
2. **Surgical Line Slicing**: When viewing files, always use `StartLine` and `EndLine` parameters to read only the target section (e.g. 50–100 lines max). NEVER view an entire 500+ line file unless explicitly instructed.
3. **Chunk-Based Edits**: Always make targeted, single-chunk or multi-chunk edits with `replace_file_content` / `multi_replace_file_content`. NEVER replace the whole file.
4. **No Conversational Fluff**: Keep conversational output concise, structured, and direct. Avoid repeating file contents or conversational padding.
5. **One Atomic Step at a Time**: Execute only the task marked `[CURRENT FOCUS]` in `TASK_LIST.md`. Never try to complete multi-phase tasks in a single turn.

---

## 📝 2. Mandatory Documentation Auto-Updates

The agent MUST maintain the 3 core state files during every workflow:

### A. Updating `CHANGELOG.md` (Delta Memory)
After every file creation or modification, append an entry to `CHANGELOG.md`:
```markdown
### [YYYY-MM-DD HH:MM] - Task: <Task Title>
- **File**: `path/to/file.ext`
- **Lines/Symbols**: Functions `foo()`, `bar()`
- **Changes**: Brief 1-sentence summary of what changed and why.
```

### B. Updating `CODEBASE_MAP.md` (Symbol Registry)
Whenever a new file is created, or new functions/classes are added or removed, update the corresponding table in `CODEBASE_MAP.md` so future turns can find the symbol without grep.

### C. Updating `TASK_LIST.md` (Roadmap Tracker)
- Mark completed tasks with `[x]`.
- Move the `[CURRENT FOCUS]` tag to the immediate next pending task.

---

## 🏗️ 3. Development Workflow Standards

1. **Before Any Code is Written**:
   - Verify `PROJECT_OVERVIEW.md` and `ARCHITECTURE.md` are aligned with the request.
   - If starting a new feature, ensure it is broken into atomic tasks in `TASK_LIST.md`.
2. **Execution**:
   - Read the symbol location from `CODEBASE_MAP.md`.
   - Read only the target lines of the file.
   - Apply the edit.
   - Update `CHANGELOG.md` and `CODEBASE_MAP.md`.
   - Verify changes with relevant test/build commands if appropriate.
