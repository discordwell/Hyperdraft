#!/usr/bin/env bash
# Test: deploy.sh build-from-ref staging is DETERMINISTIC — it ships the committed
# ref (`git archive`), never the live working tree / wrong branch / uncommitted WIP.
# Guards the DEPLOY_REF staging + fail-closed guard added to deploy.sh.
#
# Run:  bash tests/test_deploy_build_from_ref.sh [ref]   (default ref = HEAD)
set -uo pipefail
cd "$(dirname "$0")/.."
REF="${1:-HEAD}"
fail=0
pass() { echo "  PASS: $1"; }
bad()  { echo "  FAIL: $1"; fail=1; }

echo "=== deploy.sh build-from-ref test (ref=${REF}) ==="

# 1) deploy.sh carries the build-from-ref staging + fail-closed guard + param'd source
grep -q 'DEPLOY_REF'                 deploy.sh && pass "references DEPLOY_REF"            || bad "missing DEPLOY_REF"
grep -Eq 'git .*archive'             deploy.sh && pass "stages via git archive"          || bad "missing git archive staging"
grep -q 'staged tree does not match' deploy.sh && pass "has fail-closed staged guard"    || bad "missing fail-closed guard"
grep -q 'SYNC_SRC'                   deploy.sh && pass "rsync source is parameterized"   || bad "rsync source not parameterized"
grep -q 'DEPLOYED_SHA'               deploy.sh && pass "stamps DEPLOYED_SHA"             || bad "missing DEPLOYED_SHA stamp"

# 2) git archive of REF == exactly the committed content (sentinel must match the ref)
stage="$(mktemp -d)"
git archive "${REF}" | tar -x -C "${stage}"
if diff -q <(git show "${REF}:src/cards/set_registry.py") "${stage}/src/cards/set_registry.py" >/dev/null 2>&1; then
  pass "staged sentinel == committed ${REF}:src/cards/set_registry.py"
else
  bad "staged sentinel differs from committed ref (archive corrupt?)"
fi

# 3) determinism: an UNTRACKED working-tree file must NOT leak into the archive
probe=".deploy_buildref_probe.$$"
echo "uncommitted-working-tree-junk" > "${probe}"
if git archive "${REF}" | tar -t 2>/dev/null | grep -q "${probe}"; then
  bad "archive leaked an untracked working-tree file — NOT deterministic"
else
  pass "untracked working-tree file excluded from archive (deterministic)"
fi
rm -f "${probe}"
rm -rf "${stage}"

if [ "${fail}" = 0 ]; then echo "ALL DEPLOY BUILD-FROM-REF TESTS PASSED"; exit 0; else echo "DEPLOY BUILD-FROM-REF TESTS FAILED"; exit 1; fi
