#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [[ ! -d venv ]]; then
    echo "venv не знайдено. Запусти спочатку: ./setup.sh"
    exit 1
fi

source venv/bin/activate

if [[ $# -eq 0 ]]; then
    echo "Використання: ./run.sh <артикул> [опції]"
    echo ""
    echo "Приклади:"
    echo "  ./run.sh 1K0407151BC"
    echo "  ./run.sh 1K0407151BC --headed"
    echo "  ./run.sh 1K0407151BC --json results.json --concurrency 5"
    echo "  ./run.sh 1K0407151BC --search-limit 15 -v"
    echo ""
    echo "Опції:"
    echo "  --headed             Запустити браузер з GUI"
    echo "  --json FILE          Зберегти результат у JSON-файл"
    echo "  --proxy URL          HTTP(S)-проксі"
    echo "  --concurrency N      Паралельних магазинів (за замовч. 3)"
    echo "  --search-limit N     Скільки магазинів шукати (за замовч. 8)"
    echo "  --no-block           Не блокувати ресурси"
    echo "  -v, --verbose        Детальний лог"
    exit 0
fi

exec python scraper.py "$@"