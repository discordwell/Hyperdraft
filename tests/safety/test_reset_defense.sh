#!/usr/bin/env bash
# tests/safety/test_reset_defense.sh
#
# End-to-end tests for the reset-defense safety nets:
#   scripts/safety/wip_autobackup.sh
#   scripts/safety/git-reset-guarded.sh
#
# Uses a disposable temp git repo so it never touches the real Hyperdraft
# tree, refs, or hooks. Returns exit 0 on success, non-zero on failure.
#
# Run: bash tests/safety/test_reset_defense.sh

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
WIP_SH="${REPO_ROOT}/scripts/safety/wip_autobackup.sh"
GUARD_SH="${REPO_ROOT}/scripts/safety/git-reset-guarded.sh"

if [[ ! -x "$WIP_SH" ]]; then
    echo "FAIL: $WIP_SH missing or not executable" >&2
    exit 1
fi
if [[ ! -x "$GUARD_SH" ]]; then
    echo "FAIL: $GUARD_SH missing or not executable" >&2
    exit 1
fi

TMP=$(mktemp -d -t reset_defense_test.XXXXXX)
cleanup() {
    # Kill any background processes we started
    if [[ -n "${DAEMON_PID:-}" ]]; then
        kill "$DAEMON_PID" 2>/dev/null || true
    fi
    rm -rf "$TMP"
}
trap cleanup EXIT

cd "$TMP" || exit 1
git init -q . || { echo "FAIL: git init"; exit 1; }
git config user.email test@test.local
git config user.name test
git config commit.gpgsign false 2>/dev/null || true

echo "seed" > seed.txt
git add seed.txt
git -c commit.gpgsign=false commit -q -m "seed" 2>/dev/null || git commit -q -m "seed"

FAIL=0
fail() { echo "FAIL: $*" >&2; FAIL=$((FAIL+1)); }
pass() { echo "  PASS: $*"; }

#############################################
# Test 1: wip_autobackup --once snapshots tracked changes
#############################################
echo "TEST 1: wip_autobackup snapshots tracked changes"
echo "edit 1" >> seed.txt
"$WIP_SH" --once --quiet >/dev/null 2>&1
n=$(git for-each-ref refs/wip/auto/ 2>/dev/null | wc -l | tr -d ' ')
if (( n == 1 )); then pass "1 snapshot created"
else fail "expected 1 snapshot, got $n"; fi

#############################################
# Test 2: wip_autobackup --once snapshots untracked files
#############################################
echo "TEST 2: wip_autobackup snapshots untracked files"
git stash 2>/dev/null || git checkout -- seed.txt   # clean tracked changes
echo "untracked file" > new_untracked.txt
"$WIP_SH" --once --quiet >/dev/null 2>&1
latest=$(git for-each-ref refs/wip/auto/ --sort='-creatordate' --format='%(refname)' | head -1)
if git ls-tree "$latest" 2>/dev/null | grep -q new_untracked.txt; then
    pass "untracked file captured"
else
    fail "untracked file NOT captured in $latest"
fi
rm -f new_untracked.txt

#############################################
# Test 3: wip_autobackup skips clean tree (no new ref)
#############################################
echo "TEST 3: wip_autobackup is a no-op on clean tree"
git stash drop 2>/dev/null || true
git reset --hard HEAD >/dev/null 2>&1
before=$(git for-each-ref refs/wip/auto/ 2>/dev/null | wc -l | tr -d ' ')
"$WIP_SH" --once --quiet >/dev/null 2>&1
after=$(git for-each-ref refs/wip/auto/ 2>/dev/null | wc -l | tr -d ' ')
if (( before == after )); then pass "no new snapshot on clean tree"
else fail "expected no new snapshot, before=$before after=$after"; fi

#############################################
# Test 4: wip_autobackup --keep prunes oldest
#############################################
echo "TEST 4: wip_autobackup prunes beyond --keep"
for i in 1 2 3 4 5; do
    echo "edit $i" >> seed.txt
    "$WIP_SH" --once --keep 3 --quiet >/dev/null 2>&1
    git add seed.txt && git -c commit.gpgsign=false commit -q -m "edit $i" 2>/dev/null
done
count=$(git for-each-ref refs/wip/auto/ 2>/dev/null | wc -l | tr -d ' ')
if (( count <= 3 )); then pass "kept $count <= 3"
else fail "expected <=3 snapshots, got $count"; fi

#############################################
# Test 5: wip_autobackup singleton (second invocation exits)
#############################################
echo "TEST 5: wip_autobackup singleton"
"$WIP_SH" --interval 30 --quiet >/dev/null 2>&1 &
DAEMON_PID=$!
# Give it a moment to write the pidfile
for i in 1 2 3 4 5; do
    if [[ -f "$(git rev-parse --git-common-dir)/wip_autobackup.pid" ]]; then break; fi
    sleep 0.5
done
pidfile="$(git rev-parse --git-common-dir)/wip_autobackup.pid"
if [[ ! -f "$pidfile" ]]; then
    fail "pidfile not created"
else
    output=$("$WIP_SH" --interval 30 --quiet 2>&1)
    # Since --quiet suppresses the "already running" log; check that 2nd invocation exited fast
    # by checking it returned (we ran it synchronously). Just ensure no second daemon started:
    procs=$(ps aux | grep -c "[w]ip_autobackup.sh --interval 30")
    if (( procs <= 1 )); then pass "singleton enforced (procs=$procs)"
    else fail "expected <=1 daemon, got $procs"; fi
fi
kill "$DAEMON_PID" 2>/dev/null || true
wait 2>/dev/null || true
DAEMON_PID=""
rm -f "$pidfile"

#############################################
# Test 6: git-reset-guarded passes --soft through without snapshot
#############################################
echo "TEST 6: git-reset-guarded passes --soft through"
echo "edit 6" >> seed.txt
git add seed.txt
git -c commit.gpgsign=false commit -q -m "edit 6"
before_manual=$(git for-each-ref refs/wip/manual/ 2>/dev/null | wc -l | tr -d ' ')
"$GUARD_SH" --soft HEAD~1 >/dev/null 2>&1
after_manual=$(git for-each-ref refs/wip/manual/ 2>/dev/null | wc -l | tr -d ' ')
if (( before_manual == after_manual )); then pass "no snapshot for --soft"
else fail "unexpected snapshot for --soft"; fi
# Restore for next test
git -c commit.gpgsign=false commit -q -m "edit 6 restored" 2>/dev/null || true

#############################################
# Test 7: git-reset-guarded snapshots dirty tracked changes before hard reset
#############################################
echo "TEST 7: git-reset-guarded preserves tracked changes through --hard"
echo "lost edit" >> seed.txt
sha_before=$(git rev-parse HEAD)
"$GUARD_SH" --hard HEAD >/dev/null 2>&1
# Verify the working tree was reset (the edit is gone)
if grep -q "lost edit" seed.txt; then
    fail "guard did not run the actual reset (lost edit still present)"
else
    pass "reset --hard ran"
fi
latest=$(git for-each-ref refs/wip/manual/ --sort='-creatordate' --format='%(refname)' | head -1)
if [[ -z "$latest" ]]; then
    fail "no manual snapshot created"
else
    if git show "$latest":seed.txt 2>/dev/null | grep -q "lost edit"; then
        pass "snapshot has the wiped edit (recovery possible via: git checkout $latest -- seed.txt)"
    else
        fail "snapshot did NOT capture the wiped edit"
    fi
fi

#############################################
# Test 8: git-reset-guarded captures untracked files before --hard
#############################################
echo "TEST 8: git-reset-guarded captures untracked files"
echo "untracked work" > untracked_work.tmp
"$GUARD_SH" --hard HEAD >/dev/null 2>&1
latest=$(git for-each-ref refs/wip/manual/ --sort='-creatordate' --format='%(refname)' | head -1)
if git ls-tree "$latest" 2>/dev/null | grep -q untracked_work.tmp; then
    pass "untracked file captured in pre-reset snapshot"
else
    fail "untracked file NOT captured"
fi
rm -f untracked_work.tmp

#############################################
# Summary
#############################################
echo ""
if (( FAIL == 0 )); then
    echo "ALL TESTS PASSED"
    exit 0
else
    echo "$FAIL FAILURE(S)"
    exit 1
fi
