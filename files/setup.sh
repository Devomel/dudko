#!/usr/bin/env bash
# Налаштування віртуального середовища для price_scraper (Linux/macOS)
set -e

cd "$(dirname "$0")"

echo "→ Створюю venv у ./venv"
python3 -m venv venv

echo "→ Активую venv"
# shellcheck disable=SC1091
source venv/bin/activate

echo "→ Оновлюю pip"
pip install --upgrade pip

echo "→ Встановлюю Python-залежності"
pip install -r requirements.txt

echo "→ Встановлюю Chromium для Playwright (це може зайняти кілька хвилин)"
playwright install chromium

# На Linux потрібні системні бібліотеки для браузера. На macOS не потрібні.
if [[ "$OSTYPE" == "linux"* ]]; then
    echo "→ Встановлюю системні залежності для Chromium (потрібен sudo)"
    playwright install-deps chromium || echo "  (не вийшло встановити автоматично — див. README)"
fi

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  ✓ Все готово!"
echo ""
echo "  Активуй venv:    source venv/bin/activate"
echo "  Запусти скрапер: python scraper.py 1K0407151BC"
echo "  З вікном:        python scraper.py 1K0407151BC --headed"
echo "════════════════════════════════════════════════════════════════════"
