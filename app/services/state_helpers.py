"""Helpers shared by services that mutate persistent state."""

from typing import Any


# 函数 `next_numeric_id`：负责当前模块中的对应操作。
def next_numeric_id(items: list[dict[str, Any]], field: str) -> str:
    numbers = [int(item[field]) for item in items if str(item.get(field, "")).isdigit()]
    return str(max(numbers, default=0) + 1)


# 函数 `recompute_user_stats`：负责当前模块中的对应操作。
def recompute_user_stats(state: dict[str, list[dict[str, Any]]]) -> None:
    submissions = state["submissions"]
    for user in state["users"]:
        user_submissions = [
            submission
            for submission in submissions
            if submission.get("user_id") == user.get("user_id")
        ]
        solved = {
            submission.get("problem_id")
            for submission in user_submissions
            if submission.get("status") == "success"
            and submission.get("counts", 0) > 0
            and submission.get("score") == submission.get("counts")
        }
        user["submit_count"] = len(user_submissions)
        user["resolve_count"] = len(solved)
