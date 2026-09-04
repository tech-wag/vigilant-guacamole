"""Step 4: the fix agent's system prompt and per-file user message builder."""

FIX_SYSTEM_PROMPT = """You are a senior engineer fixing issues found during code \
review. You will be given one full source file and a list of specific issues found \
in it. Rewrite the ENTIRE file with those issues fixed, preserving all unrelated \
code, formatting, comments, and style exactly as-is. Respond with ONLY the complete \
corrected file content — no markdown code fences, no commentary, no explanation."""


def build_fix_user_message(path: str, original_content: str, findings: list[dict]) -> str:
    issues = "\n".join(
        f"- [{f['severity']}] {f['message']}" + (f" (suggestion: {f['suggestion']})" if f.get("suggestion") else "")
        for f in findings
    )
    return f"File: {path}\n\nIssues to fix:\n{issues}\n\nOriginal file content:\n{original_content}"
