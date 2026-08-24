#!/usr/bin/env bash
# Обновление кода на Replit до состояния GitHub (main).
# Локальные правки и автокоммиты реплита будут отброшены.
set -e
git fetch origin
git reset --hard origin/main
echo
echo "=== Код обновлён до: $(git log --oneline -1) ==="
echo "Теперь: Stop -> Run"
