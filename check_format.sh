#!/usr/bin/env bash
set -euo pipefail

run_check() {
    local name="$1"; shift
    local output
    output="$("$@" 2>&1)" || true

    echo "=== Checking $name ==="
    # Filter out known success messages; if anything remains, check failed.
    if echo "$output" | grep -Ev "No issues detected|All done|Skipped [0-9]+ files|[0-9]+ file(s)? would be left unchanged|No Python files are present to be formatted" | grep -q '.'; then
        echo "$output"
        echo "❌ $name found issues"
        return 1
    else
        return 0
    fi
}

autoflake_failed=0
isort_failed=0
black_failed=0

# autoflake always returns 0 when using --check-diff, so we have to manually check it with --check first.
echo "=== Checking unused imports (autoflake) ==="
output_autoflake="$(autoflake --remove-all-unused-imports --recursive --check . 2>&1)" || true
filtered_autoflake="$(echo "$output_autoflake" | grep -Ev "No issues detected|All done" || true)"

if [[ -n "$filtered_autoflake" ]]; then
    echo "❌ autoflake would remove unused imports:"
    autoflake --remove-all-unused-imports --recursive --check-diff . 2>&1 | grep -Ev "No issues detected|All done" || true
    autoflake_failed=1
fi

run_check "import order (isort)" \
    isort --profile black -l 100 --check-only --diff . || isort_failed=1

run_check "code formatting (black)" \
    black -l 100 --check --diff . || black_failed=1

failed=$((autoflake_failed + isort_failed + black_failed))


echo
echo "=== Summary ==="
echo "autoflake: $([[ $autoflake_failed -eq 0 ]] && echo ✅ || echo ❌)"
echo "isort:     $([[ $isort_failed -eq 0 ]] && echo ✅ || echo ❌)"
echo "black:     $([[ $black_failed -eq 0 ]] && echo ✅ || echo ❌)"


exit $failed
