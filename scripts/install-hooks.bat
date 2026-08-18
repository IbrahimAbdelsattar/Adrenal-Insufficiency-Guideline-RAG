@echo off
REM Point git at the tracked hooks directory so scripts/hooks/pre-push runs on
REM every push. Safe to re-run; affects only this clone.
git config core.hooksPath scripts/hooks
echo Git hooks installed: core.hooksPath=scripts/hooks
echo Every 'git push' now runs scripts/validate-ci.sh first.
echo Bypass in an emergency with: git push --no-verify
