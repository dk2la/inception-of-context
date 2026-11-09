"""Sanity Checks: hard rules that refuse a Patch before anything touches the disk.

Each rule is a function (patch, target_dir) that returns a reason string, or None if the Patch is fine.
A Patch looks like {"summary": ..., "files": [{"path": ..., "op": "create|modify|delete", "content": ...}]}.
"""
import os


def outside_target(patch, target_dir):
    """Refuse absolute paths and paths with a '..' part (a backslash counts as a separator)."""
    for entry in patch["files"]:
        path = entry["path"].replace("\\", "/")
        if os.path.isabs(path) or ".." in path.split("/"):
            return f"path outside target project: {entry['path']}"
    return None


# outside_target must stay first: the rules after it read files from disk and trust the paths are inside.
RULES = [outside_target]


def check_patch(patch, target_dir):
    """Return the reason of the first rule that refuses the Patch, or None if it is allowed."""
    for rule in RULES:
        reason = rule(patch, target_dir)
        if reason:
            return reason
    return None
