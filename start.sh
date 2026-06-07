#!/usr/bin/env bash
# Запуск/зупинка системи AutoParts Monitor (Linux / macOS)
#
# Використання:
#   ./start.sh          — запуск всього
#   ./start.sh --stop   — зупинка всього
#   ./start.sh --logs   — показати логи у реальному часі

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
NVM_NODE="$HOME/.nvm/versions/node/v22.22.3/bin"
VENV="$ROOT/.venv"
PIDS_FILE="$ROOT/.pids"
DATA_DIR="$ROOT/data"
LOG_API="$DATA_DIR/api.log"
LOG_FRONT="$DATA_DIR/frontend.log"

# ── .env ─────────────────────────────────────────────────────────────────────
if [[ -f "$ROOT/files/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$ROOT/files/.env"
    set +a
fi

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
info() { echo -e "${CYAN}→${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*" >&2; }
hdr()  { echo -e "\n${BOLD}$*${NC}"; }

# ── --stop ────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--stop" ]]; then
    hdr "Зупинка AutoParts Monitor..."
    if [[ -f "$PIDS_FILE" ]]; then
        while IFS= read -r pid; do
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null && ok "Зупинено PID $pid" || warn "PID $pid вже завершився"
            fi
        done < "$PIDS_FILE"
        rm -f "$PIDS_FILE"
    else
        warn "Файл PID не знайдено — сервіси вже зупинені або запущені інакше"
    fi
    info "Зупинка PostgreSQL..."
    docker stop dudko_scrapper_db 2>/dev/null && ok "PostgreSQL зупинено" || warn "Контейнер не знайдено"
    ok "Готово."
    exit 0
fi

# ── --logs ────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--logs" ]]; then
    mkdir -p "$DATA_DIR"
    touch "$LOG_API" "$LOG_FRONT"
    echo -e "${CYAN}=== API ===${NC} ($LOG_API)    ${GREEN}=== Frontend ===${NC} ($LOG_FRONT)"
    tail -f "$LOG_API" "$LOG_FRONT"
    exit 0
fi

# ── Зупинка при Ctrl+C ────────────────────────────────────────────────────────
cleanup() {
    echo ""
    info "Зупинка (Ctrl+C)..."
    "$0" --stop
}
trap cleanup INT TERM

mkdir -p "$DATA_DIR"
> "$PIDS_FILE"

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}   AutoParts Monitor — запуск системи${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"

# ── 1. Перевірка залежностей ──────────────────────────────────────────────────
hdr "1. Перевірка залежностей"

command -v docker &>/dev/null || { err "Docker не встановлено"; exit 1; }
# Підтримка docker compose v2 та docker-compose v1
if docker compose version &>/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose &>/dev/null; then
    DC="docker-compose"
else
    err "docker compose / docker-compose не знайдено"; exit 1
fi
command -v python3 &>/dev/null || { err "python3 не знайдено"; exit 1; }
ok "docker ($DC), python3 знайдено"

if [[ -x "$NVM_NODE/node" ]]; then
    export PATH="$NVM_NODE:$PATH"
    ok "Node.js $("$NVM_NODE/node" --version) (nvm v22)"
else
    warn "nvm Node 22 не знайдено — використовую системний: $(node --version 2>/dev/null || echo 'не знайдено')"
fi

# ── 2. Python venv ────────────────────────────────────────────────────────────
hdr "2. Python venv"
if [[ ! -f "$VENV/bin/python" ]]; then
    info "Створення venv..."
    python3 -m venv "$VENV"
fi

if ! "$VENV/bin/python" -c "import fastapi" 2>/dev/null; then
    info "Встановлення Python залежностей (може зайняти хвилину)..."
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -r "$ROOT/files/requirements.txt"
    "$VENV/bin/pip" install --quiet -r "$ROOT/api/requirements.txt"
    ok "Залежності встановлено"
else
    ok "venv готовий"
fi

# ── 3. Node.js залежності ─────────────────────────────────────────────────────
hdr "3. Node.js залежності"
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
    info "npm install (може зайняти хвилину)..."
    npm --prefix "$ROOT/frontend" install --silent
    ok "node_modules встановлено"
else
    ok "node_modules вже є"
fi

# ── 4. PostgreSQL ─────────────────────────────────────────────────────────────
hdr "4. PostgreSQL"

# Перевіряємо чи контейнер вже запущений
if docker inspect dudko_scrapper_db &>/dev/null; then
    if [[ "$(docker inspect -f '{{.State.Running}}' dudko_scrapper_db 2>/dev/null)" == "true" ]]; then
        ok "Контейнер вже запущений"
    else
        docker start dudko_scrapper_db &>/dev/null && ok "Контейнер запущено" || true
    fi
else
    info "Запуск PostgreSQL через docker run..."
    # Пробуємо через compose, якщо впало — використовуємо docker run
    if ! $DC -f "$ROOT/docker-compose.yml" up -d db 2>/dev/null; then
        warn "docker-compose не спрацював, запуск через docker run..."
        # Перевіряємо чи є volume
        docker volume inspect dudko-scrapper_pgdata &>/dev/null \
            || docker volume create dudko-scrapper_pgdata &>/dev/null
        docker run -d \
            --name dudko_scrapper_db \
            -e POSTGRES_DB=scrapper \
            -e POSTGRES_USER=scrapper \
            -e POSTGRES_PASSWORD=scrapper \
            -p 5433:5432 \
            -v dudko-scrapper_pgdata:/var/lib/postgresql/data \
            -v "$ROOT/db/schema.sql:/docker-entrypoint-initdb.d/01_schema.sql:ro" \
            -v "$ROOT/db/seed_products.sql:/docker-entrypoint-initdb.d/02_seed.sql:ro" \
            -v "$ROOT/db/seed_sales.sql:/docker-entrypoint-initdb.d/03_sales.sql:ro" \
            --restart unless-stopped \
            postgres:16-alpine
    fi
fi

info "Очікування готовності БД..."
for i in $(seq 1 40); do
    if docker exec dudko_scrapper_db pg_isready -U scrapper -d scrapper -q 2>/dev/null; then
        break
    fi
    [[ $i -eq 40 ]] && { err "БД не відповіла за 40 секунд"; exit 1; }
    sleep 1
done
ok "PostgreSQL готовий (localhost:5433)"

# ── 5. FastAPI ────────────────────────────────────────────────────────────────
hdr "5. FastAPI"
OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
"$VENV/bin/uvicorn" main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --app-dir "$ROOT/api" \
    > "$LOG_API" 2>&1 &
API_PID=$!
echo "$API_PID" >> "$PIDS_FILE"

info "Очікування готовності API..."
for i in $(seq 1 25); do
    curl -sf http://localhost:8000/health &>/dev/null && break
    kill -0 "$API_PID" 2>/dev/null || { err "API впав. Лог:"; tail -20 "$LOG_API" >&2; exit 1; }
    sleep 1
done
ok "FastAPI готовий (PID $API_PID)"

# ── 6. Next.js ────────────────────────────────────────────────────────────────
hdr "6. Next.js"
NEXT_PUBLIC_API_URL="http://localhost:8000" \
    npm --prefix "$ROOT/frontend" run dev \
    > "$LOG_FRONT" 2>&1 &
FRONT_PID=$!
echo "$FRONT_PID" >> "$PIDS_FILE"

info "Очікування готовності фронту..."
for i in $(seq 1 40); do
    curl -sf http://localhost:3000 &>/dev/null && break
    kill -0 "$FRONT_PID" 2>/dev/null || { err "Фронт впав. Лог:"; tail -20 "$LOG_FRONT" >&2; exit 1; }
    sleep 1
done
ok "Next.js готовий (PID $FRONT_PID)"

# ── Готово ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}${BOLD}✓ Система запущена!${NC}"
echo ""
echo -e "  ${CYAN}Фронтенд:${NC}  http://localhost:3000"
echo -e "  ${CYAN}API:${NC}       http://localhost:8000"
echo -e "  ${CYAN}API Docs:${NC}  http://localhost:8000/docs"
echo -e "  ${CYAN}БД:${NC}        localhost:5433"
echo ""
echo -e "  Логи:   ${YELLOW}./start.sh --logs${NC}"
echo -e "  Стоп:   ${YELLOW}./start.sh --stop${NC}  або  ${YELLOW}Ctrl+C${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo ""

wait
