import argparse

from loghop.cli_commands._handoff_launch import launch_handoff_session
from loghop.terminal import Terminal


def handle_resume(args: argparse.Namespace, term: Terminal) -> int:
    return launch_handoff_session(args, term, mode="resume", command="resume")
