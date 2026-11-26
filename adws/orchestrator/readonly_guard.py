#!/usr/bin/env python3
"""PreToolUse hook: keeps read-only subagents (adw-reviewer, adw-investigator) to read-only Bash commands.

Claude Code runs it with the hook input on stdin ({"tool_name", "tool_input": {"command"}, "agent_type", ...}).
Exit 2 blocks the call and tells the agent why; exit 0 lets it through.

  readonly_guard.py --always                      every Bash call is checked (an agent-scoped hook)
  readonly_guard.py --agents adw-reviewer,...     only calls made inside those subagents (a session hook)

Standard library only: it runs once per tool call and must start fast.
"""

from __future__ import annotations

import json
import re
import shlex
import sys

READ_ONLY = {"cat", "head", "tail", "wc", "ls", "grep", "egrep", "fgrep", "rg", "sort", "uniq", "cut", "tr", "jq",
             "diff", "tree", "file", "stat", "pwd", "echo", "printf", "basename", "dirname", "realpath", "which",
             "cd", "true", "test", "[", "nl", "column", "less", "more", "du", "date", "comm", "fold"}
GIT_READ_ONLY = {"diff", "log", "show", "status", "blame", "ls-files", "ls-tree", "grep", "rev-parse", "merge-base",
                 "cat-file", "shortlog", "describe", "rev-list", "name-rev", "whatchanged", "branch", "tag", "remote"}
SAFE_REDIRECT = re.compile(r"\s*(?:\d?>\s*/dev/null|\d?>&\d|<\s*/dev/null)")


def check(command: str) -> str | None:
    """Why the command isn't read-only, or None when it is."""
    if "`" in command or "$(" in command or "<(" in command or ">(" in command:
        return "command substitution is not allowed here"
    stripped = SAFE_REDIRECT.sub(" ", command)
    if re.search(r">|<<", stripped):
        return "writing to files (> or >>) is not allowed here"
    for segment in re.split(r"&&|\|\||[;|\n&]", stripped):
        segment = segment.strip()
        if not segment:
            continue
        try:
            words = shlex.split(segment)
        except ValueError:
            return "unparseable command"
        while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):     # VAR=value prefixes
            words = words[1:]
        if not words:
            continue
        head, args = words[0].rsplit("/", 1)[-1], words[1:]
        if head == "git":
            sub = next((a for a in args if not a.startswith("-")), "")
            if sub not in GIT_READ_ONLY:
                return f"git {sub or ''} is not read-only".replace("  ", " ")
            if sub in ("branch", "tag", "remote") and any(a in ("-d", "-D", "-m", "-M", "--delete", "add", "remove",
                                                                  "rm", "set-url", "rename", "-f") for a in args):
                return f"git {sub} with that option changes the repository"
            if any(a.startswith("--output") for a in args):
                return "git --output writes a file"
            continue
        if head == "sed":
            if any(a == "-i" or a.startswith("-i") or a.startswith("--in-place") for a in args):
                return "sed -i edits files"
            continue
        if head == "find":
            if any(a in ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls") for a in args):
                return "find with -delete/-exec is not allowed here"
            continue
        if head == "awk":
            if any("system" in a or ">" in a for a in args):
                return "awk with system() or output redirection is not allowed here"
            continue
        if head == "sort" and any(a.startswith("-o") or a.startswith("--output") for a in args):
            return "sort -o writes a file"
        if head == "npx" and args[:1] == ["tsc"] and "--noEmit" in args:
            continue
        if head not in READ_ONLY:
            return f"`{head}` is not on the read-only list"
    return None


def main(argv: list[str]) -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if event.get("tool_name") != "Bash":
        return 0
    if "--agents" in argv:
        i = argv.index("--agents")
        agents = set((argv[i + 1] if i + 1 < len(argv) else "").split(","))
        if (event.get("agent_type") or "") not in agents:
            return 0
    command = str((event.get("tool_input") or {}).get("command") or "")
    problem = check(command)
    if problem:
        print(f"Blocked: you are a read-only agent ({problem}). Use Read/Grep/Glob, or read-only commands such as "
              "git diff/log/show/status, ls, cat, head, grep, find (no -exec).", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
