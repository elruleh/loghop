import argparse
import dataclasses

from loghop.cli_commands._helpers import require_project_config, validate_length
from loghop.redact import redact_text
from loghop.store import save_config
from loghop.store._registry import touch_project
from loghop.store._render import render_memory
from loghop.terminal import Terminal


def handle_goal(args: argparse.Namespace, term: Terminal) -> int:
    root, paths, config = require_project_config()
    if args.clear:
        config = dataclasses.replace(config, goal="")
        save_config(paths, config)
        render_memory(paths, config)
        touch_project(root)
        term.success("Goal cleared")
        term.capture_result({"goal": ""})
        return 0
    if args.text is None:
        goal = config.goal
        display_goal = redact_text(goal)
        term.section("goal", (("current", display_goal or "(not set)"),))
        term.capture_result({"goal": display_goal})
        return 0
    goal = validate_length(args.text, "goal")
    config = dataclasses.replace(config, goal=goal)
    save_config(paths, config)
    render_memory(paths, config)
    touch_project(root)
    display_goal = redact_text(goal)
    term.success(f"Set goal: {display_goal}")
    term.capture_result({"goal": display_goal})
    return 0
