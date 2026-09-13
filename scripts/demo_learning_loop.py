"""Render the recorded learning loop for a live demo.

Reads the studio server's learning endpoint and prints the three phases the
loop actually went through: discovery (a failed strategy corrected by a
second one), reuse (the promoted skill applied with no failed trial), and
quarantine (that same skill retracted after it failed full preview checks).

Every number printed comes from recorded evidence in the learning store.

    uv run python scripts/demo_learning_loop.py
"""
import json
import sys
import urllib.request

ENDPOINT = 'http://127.0.0.1:2721/api/learning'
BOLD, DIM, RED, GREEN, YELLOW, RESET = '\033[1m', '\033[2m', '\033[31m', '\033[32m', '\033[33m', '\033[0m'


def rule(title):
    print(f'\n{BOLD}{title}{RESET}\n' + '─' * 66)


def load():
    try:
        with urllib.request.urlopen(ENDPOINT, timeout=10) as response:
            return json.load(response)
    except OSError as error:
        sys.exit(f'Cannot reach {ENDPOINT} ({error}).\n'
                 'Start it with: uv run python -m cadforge.studio_server')


def main():
    state = load()
    skills, evidence = state['skills'], state['evidence']
    quarantines = state['quarantines']

    rule('1. DISCOVERY — a failed attempt is corrected and the fix is kept')
    discovery = next(e for e in evidence if len(e['trials']) > 1)
    print(f"request: {json.dumps(discovery['command'])}\n")
    for trial in discovery['trials']:
        failed = [c['name'] for c in trial['checks'] if not c['passed']]
        mark = f'{GREEN}PASS{RESET}' if trial['accepted'] else f'{RED}FAIL{RESET}'
        detail = f"{RED}blocked by: {', '.join(failed)}{RESET}" if failed else 'all geometry checks passed'
        print(f"  {mark}  {trial['strategy']:<34} {detail}")
    print(f"\n  {DIM}The measured kernel rejected the first strategy. The second was"
          f"\n  promoted only because recorded checks passed.{RESET}")

    rule('2. REUSE — the promoted skill removes the failed attempt entirely')
    first = sum(1 for e in evidence if len(e['trials']) > 1)
    later = sum(1 for e in evidence if len(e['trials']) == 1)
    print(f"  before learning : {first} operations, 2 trials each  (one wasted attempt every time)")
    print(f"  after learning  : {later} operations, 1 trial each   {GREEN}(no wasted attempts){RESET}")
    reused = [e for e in evidence if e.get('used_skill_id')]
    for e in reused:
        print(f"\n  evidence {e['id'][:10]} applied skill {BOLD}{e['used_skill_id'][:10]}{RESET} "
              f"in {len(e['trials'])} trial, accepted={e['accepted']}")

    rule('3. QUARANTINE — the same skill is retracted when it later fails')
    for q in quarantines:
        print(f"  skill {BOLD}{q['skill_id'][:10]}{RESET} -> {YELLOW}QUARANTINED{RESET}")
        print(f"  reason: {q['reason']}")
        if any(e.get('used_skill_id') == q['skill_id'] for e in evidence):
            print(f"  {DIM}This is the same skill reused above. Promotion is reversible:"
                  f"\n  a skill that stops verifying stops being eligible.{RESET}")

    rule('LEARNING STORE')
    eligible = [s for s in skills if s['eligible_for_reuse']]
    blocked = [s for s in skills if not s['eligible_for_reuse']]
    for s in skills:
        status = (f'{GREEN}eligible{RESET}' if s['eligible_for_reuse']
                  else f'{YELLOW}{s["current_status"]}{RESET}')
        print(f"  {s['operation']}/{s['axis']:<2} {s['strategy']:<32} "
              f"{len(s['evidence_ids'])} evidence records  {status}")
    print(f"\n  {len(eligible)} eligible, {len(blocked)} withdrawn, "
          f"{len(evidence)} immutable evidence records total.")
    print(f"  {DIM}No skill is trusted because a model claimed it worked.{RESET}\n")


if __name__ == '__main__':
    main()
