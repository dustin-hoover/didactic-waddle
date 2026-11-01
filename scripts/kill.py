#!/usr/bin/env python3
"""kill.py — the one command that halts all new trading activity.

Per ACTION_PLAN §0.3: one command flips the kill state. When engaged, EVERY
proposal path in the autopilot returns a hold before it considers a trade (see
Autopilot._killed / decide), so no new risk is taken until it is cleared.

Two independent layers, by design — the HTML/JS is never the only boundary:

  1. LOCAL kill (this script): writes/removes a sentinel file (default: ./KILL).
     The autopilot checks for it (and for the env var TB_KILL) on every decide().
     This is instant and needs no network — your first line of defense.

  2. ON-CHAIN pause (Phase 0.2, not yet wired): the real hard stop lives in the
     smart-account policy module (Safe + Zodiac Roles on EVM, Squads on Solana).
     Revoking the session key / pausing the Roles modifier stops signing even if
     every off-chain check were bypassed. Until 0.2 lands, this script PRINTS the
     exact manual step and exits non-zero for `on`, so it can never give a false
     sense that the on-chain stop is armed when it is not.

Usage:
    python3 scripts/kill.py on       # engage the kill switch
    python3 scripts/kill.py off      # clear it (new activity allowed again)
    python3 scripts/kill.py status   # report current state

Env:
    TB_KILL_FILE   path to the sentinel file (default: KILL in the cwd)
    TB_KILL        if set truthy in the runner's env, kill is ALSO engaged
                   (belt-and-suspenders; this script does not change env vars)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

DEFAULT_KILL_FILE = os.environ.get("TB_KILL_FILE", "KILL")

# Phase 0.2 will replace this stub with a real on-chain pause call.
_ONCHAIN_READY = False


def _truthy(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "on", "yes")


def is_killed(kill_file: str = DEFAULT_KILL_FILE) -> bool:
    """True if the local kill is engaged (sentinel file present OR TB_KILL set).
    Mirrors Autopilot._killed so the CLI and the engine never disagree."""
    if _truthy(os.environ.get("TB_KILL", "")):
        return True
    try:
        return os.path.exists(kill_file)
    except OSError:
        return False


def engage(kill_file: str = DEFAULT_KILL_FILE) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    with open(kill_file, "w") as fh:
        fh.write(f"KILL engaged {stamp}\n"
                 "All new trading activity is halted. Remove this file "
                 "(python3 scripts/kill.py off) to resume.\n")


def clear(kill_file: str = DEFAULT_KILL_FILE) -> bool:
    """Remove the sentinel. Returns True if a file was actually removed."""
    try:
        os.remove(kill_file)
        return True
    except FileNotFoundError:
        return False


def _onchain_note(action: str) -> int:
    """Report the on-chain layer. Returns a process exit code.

    While 0.2 is unbuilt we refuse to claim the on-chain stop is armed: `on`
    exits non-zero with the manual instruction so an operator is never misled."""
    if _ONCHAIN_READY:  # pragma: no cover - wired in Phase 0.2
        return 0
    if action == "on":
        print("  ON-CHAIN: NOT wired yet (Phase 0.2). The local kill is engaged,")
        print("            but to be fully safe ALSO pause signing on-chain now:")
        print("            - EVM: pause the Zodiac Roles modifier / revoke the session key")
        print("            - Solana: disable the Squads spending authority")
        print("            (there are no hot keys today, so local kill already blocks")
        print("             every proposal; this is the belt-and-suspenders step.)")
        return 3
    print("  ON-CHAIN: pause module not wired yet (Phase 0.2) — nothing to clear.")
    return 0


def main(argv: list[str]) -> int:
    kill_file = DEFAULT_KILL_FILE
    action = (argv[1] if len(argv) > 1 else "status").lower()

    if action in ("on", "engage", "kill"):
        engage(kill_file)
        print(f"KILL ENGAGED — sentinel written to {kill_file!r}.")
        print("  LOCAL:    every autopilot proposal path will now hold.")
        return _onchain_note("on")

    if action in ("off", "clear", "resume"):
        removed = clear(kill_file)
        print(f"KILL CLEARED — {'removed ' + repr(kill_file) if removed else 'no sentinel file was present'}.")
        if _truthy(os.environ.get("TB_KILL", "")):
            print("  WARNING: env TB_KILL is still set — kill remains ENGAGED via env.")
            print("           Unset it in the runner to fully resume.")
        print("  LOCAL:    new activity allowed again (unless TB_KILL is set).")
        return _onchain_note("off")

    if action in ("status", "state", ""):
        killed = is_killed(kill_file)
        print(f"KILL STATUS: {'ENGAGED' if killed else 'clear'}")
        print(f"  sentinel file {kill_file!r}: {'present' if os.path.exists(kill_file) else 'absent'}")
        print(f"  env TB_KILL: {'set (' + os.environ['TB_KILL'] + ')' if os.environ.get('TB_KILL') else 'unset'}")
        print(f"  on-chain pause: {'armed' if _ONCHAIN_READY else 'NOT wired (Phase 0.2)'}")
        return 0

    print(__doc__)
    print(f"\nUnknown action {action!r}. Use: on | off | status", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
