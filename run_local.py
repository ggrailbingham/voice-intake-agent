"""
run_local.py
------------
Local CLI runner for testing the intake agent without Twilio.
Simulates a phone call in your terminal.

Usage:
    python run_local.py

Set your Anthropic API key first:
    export ANTHROPIC_API_KEY=your_key_here
"""

import os
import json
from agent import IntakeSession


def run_cli_session():
    print("\n" + "="*60)
    print("  HEALTHBRIDGE INSURANCE — INTAKE AGENT (LOCAL TEST)")
    print("="*60)
    print("Type your responses as if you're the customer.")
    print("Type 'status' to see current field state.")
    print("Type 'quit' to exit.\n")

    session = IntakeSession()

    # Get opening line
    print("AGENT: ", end="", flush=True)
    opening = session.get_opening_line()
    print(opening)
    print()

    # Conversation loop
    while not session.complete:
        try:
            user_input = input("YOU: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Session ended by user]")
            break

        if not user_input:
            continue

        if user_input.lower() == "quit":
            print("[Session ended]")
            break

        if user_input.lower() == "status":
            status = session.get_status()
            print("\n[DEBUG STATUS]")
            print(json.dumps(status, indent=2))
            print()
            continue

        print("\nAGENT: ", end="", flush=True)
        response = session.process_turn(user_input)

        # Strip the INTAKE_COMPLETE line from displayed output
        display_response = response
        if "INTAKE_COMPLETE:" in response:
            display_response = response.split("INTAKE_COMPLETE:")[0].strip()

        print(display_response)
        print()

    if session.complete:
        print("\n" + "="*60)
        print("  INTAKE COMPLETE — FINAL RECORD")
        print("="*60)
        print(json.dumps(session.final_record, indent=2))
        print("\n[In production, call would now transfer to human advisor]")


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
        print("Run: export ANTHROPIC_API_KEY=your_key_here")
        exit(1)

    run_cli_session()
