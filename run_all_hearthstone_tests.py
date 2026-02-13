"""
Run all Hearthstone tests and report results.
"""

import subprocess
import sys


def run_test_file(filename, description):
    """Run a test file and return pass/fail counts."""
    print(f"\n{'='*70}")
    print(f"Running: {description}")
    print(f"{'='*70}")

    result = subprocess.run(
        [sys.executable, filename],
        capture_output=True,
        text=True
    )

    output = result.stdout + result.stderr

    # Print output
    print(output)

    # Extract results
    if "RESULTS:" in output:
        results_line = [line for line in output.split('\n') if 'RESULTS:' in line][-1]
        return results_line

    return "Unknown results"


def main():
    """Run all test suites."""
    tests = [
        ("test_hearthstone_real_cards.py", "Basic Hearthstone Mechanics (9 tests)"),
        ("test_hearthstone_advanced.py", "Advanced Mechanics (9 tests)"),
        ("test_hearthstone_new_cards.py", "New Cards (3 tests)"),
        ("test_hearthstone_sba.py", "State-Based Actions (5 tests)"),
        ("test_hearthstone_fatigue.py", "Fatigue Mechanics (4 tests)"),
        ("test_hero_power_effects.py", "Hero Powers - Basic (3 tests)"),
        ("test_all_hero_powers.py", "Hero Powers - All (4 tests, 1 skipped)"),
        ("test_weapon_mechanics.py", "Weapon Mechanics (4 tests)"),
        ("test_keyword_mechanics.py", "Keyword Mechanics (5 tests)"),
        ("test_complex_interactions.py", "Complex Interactions (5 tests)"),
    ]

    print("="*70)
    print("HEARTHSTONE COMPREHENSIVE TEST SUITE")
    print("="*70)

    all_results = []

    for filename, description in tests:
        result = run_test_file(filename, description)
        all_results.append((description, result))

    # Print summary
    print("\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)

    total_passed = 0
    total_failed = 0
    total_skipped = 0

    for desc, result in all_results:
        print(f"{desc}")
        print(f"  {result}")

        # Parse numbers
        if "passed" in result:
            import re
            match = re.search(r'(\d+) passed', result)
            if match:
                total_passed += int(match.group(1))

            match = re.search(r'(\d+) failed', result)
            if match:
                total_failed += int(match.group(1))

            match = re.search(r'(\d+) skipped', result)
            if match:
                total_skipped += int(match.group(1))

    print("\n" + "="*70)
    print(f"TOTAL: {total_passed} passed, {total_failed} failed, {total_skipped} skipped")
    print("="*70)


if __name__ == "__main__":
    main()
