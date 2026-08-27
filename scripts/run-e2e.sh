#!/usr/bin/env bash
# =============================================================================
# AncoraMind — E2E Startup Script
# =============================================================================
# Automates the full deployment sequence:
#   1. Check prerequisites
#   2. Start PostgreSQL (Docker)
#   3. Apply database migrations
#   4. Check .env configuration
#   5. Start ngrok (if not running)
#   6. Register Telegram webhook
#   7. Launch AncoraMind
#
# Usage:
#   bash scripts/run-e2e.sh           # full sequence
#   bash scripts/run-e2e.sh --check   # only check prerequisites
#   bash scripts/run-e2e.sh --reset   # also reset webhook before registering
#
# Prerequisites (must be done manually once):
#   - Create bot via @BotFather -> copy TELEGRAM_TOKEN
#   - Get LLM API key (OpenAI / OpenRouter / other)
#   - Copy .env.example -> .env and fill in values
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}ℹ${NC}  $*"; }
ok()    { echo -e "${GREEN}✓${NC}  $*"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $*"; }
error() { echo -e "${RED}✗${NC}  $*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ -f .env ]; then
  set -a; source .env; set +a
  info "Loaded .env"
else
  error ".env not found. Run: cp .env.example .env and fill in your values."
fi

CHECK_ONLY=false; RESET_WEBHOOK=false
for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=true ;;
    --reset) RESET_WEBHOOK=true ;;
  esac
done

# ── 1. Prerequisites ─────────────────────────────
echo ""; info "Checking prerequisites..."
check_cmd() { command -v "$1" >/dev/null 2>&1 || error "$1 not found. Install it first."; }
check_cmd python; check_cmd docker; check_cmd ngrok; check_cmd curl

[ -n "${TELEGRAM_TOKEN:-}" ] || error "TELEGRAM_TOKEN not set in .env"
[ -n "${LLM_PROVIDER:-}" ] || error "LLM_PROVIDER not set in .env"

case "$LLM_PROVIDER" in
  openai)      [ -n "${OPENAI_API_KEY:-}" ] || warn "OPENAI_API_KEY not set" ;;
  openrouter)  [ -n "${OPENROUTER_API_KEY:-}" ] || warn "OPENROUTER_API_KEY not set" ;;
  openai-like)
    [ -n "${LLM_BASE_URL:-}" ] || error "LLM_BASE_URL required when LLM_PROVIDER=openai-like"
    [ -n "${OPENAI_API_KEY:-}" ] || warn "OPENAI_API_KEY not set" ;;
  *) error "Unknown LLM_PROVIDER: $LLM_PROVIDER (use: openai, openrouter, openai-like)" ;;
esac
ok "Prerequisites OK — provider: $LLM_PROVIDER"

if [ "$CHECK_ONLY" = true ]; then info "Check-only mode. Exiting."; exit 0; fi

# ── 2. PostgreSQL ────────────────────────────────
echo ""; info "Starting PostgreSQL..."
if docker compose ps postgres 2>/dev/null | grep -q "running"; then
  ok "PostgreSQL already running"
else
  docker compose up postgres -d || error "Failed to start PostgreSQL"
  info "Waiting for PostgreSQL..."
  for i in $(seq 1 30); do
    docker compose exec -T postgres pg_isready -U ancora -d ancoramind >/dev/null 2>&1 && break
    sleep 1; [ "$i" -eq 30 ] && error "PostgreSQL not ready after 30s"
  done
  ok "PostgreSQL is ready"
fi

# ── 3. Migrations ───────────────────────────────
echo ""; info "Applying migrations..."
if docker compose exec -T postgres psql -U ancora -d ancoramind -c "SELECT 1 FROM ancora.notes LIMIT 1" >/dev/null 2>&1; then
  ok "Migrations already applied"
else
  docker compose exec -T postgres psql -U ancora -d ancoramind < migrations/init.sql || error "Failed to apply migrations"
  ok "Migrations applied"
fi

TABLE_COUNT=$(docker compose exec -T postgres psql -U ancora -d ancoramind -t -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='ancora'" | tr -d '[:space:]')
info "Domain tables in 'ancora' schema: $TABLE_COUNT"

# ── 4. ngrok ────────────────────────────────────
echo ""; info "Checking ngrok..."
NGROK_API="http://localhost:4040/api/tunnels"
NGROK_URL=""

if curl -s "$NGROK_API" 2>/dev/null | grep -q "tunnels"; then
  NGROK_URL=$(curl -s "$NGROK_API" 2>/dev/null \
    | python -c "import sys,json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || echo "")
  [ -n "$NGROK_URL" ] && ok "ngrok already running: $NGROK_URL"
fi

if [ -z "$NGROK_URL" ]; then
  info "Starting ngrok in background..."
  ngrok http 7777 > /dev/null 2>&1 &
  NGROK_PID=$!
  sleep 3
  NGROK_URL=$(curl -s "$NGROK_API" 2>/dev/null \
    | python -c "import sys,json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || echo "")
  [ -z "$NGROK_URL" ] && error "Failed to get ngrok URL. Start manually: ngrok http 7777"
  ok "ngrok started: $NGROK_URL"
fi

# ── 5. Register webhook ─────────────────────────
echo ""; info "Registering Telegram webhook..."
WEBHOOK_URL="${NGROK_URL}/telegram/webhook"

if [ "$RESET_WEBHOOK" = true ]; then
  info "Deleting existing webhook..."
  curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/deleteWebhook" >/dev/null
fi

WEBHOOK_RESULT=$(curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook?url=${WEBHOOK_URL}")
echo "$WEBHOOK_RESULT" | grep -q '"ok":true' && ok "Webhook registered: $WEBHOOK_URL" || error "Webhook failed: $WEBHOOK_RESULT"

# ── 6. Launch ───────────────────────────────────
echo ""
echo "=============================================="
echo "  AncoraMind is ready to launch!"
echo "=============================================="
echo "  Provider:  $LLM_PROVIDER"
echo "  Model:     ${LLM_MODEL:-gpt-5.4-mini}"
echo "  Webhook:   $WEBHOOK_URL"
echo "  Database:  PostgreSQL ($TABLE_COUNT domain tables)"
echo "=============================================="
echo ""
info "Starting AncoraMind (Ctrl+C to stop)..."; echo ""

if [ -d ".venv" ]; then
  if [ -f ".venv/bin/activate" ]; then source .venv/bin/activate
  elif [ -f ".venv/Scripts/activate" ]; then source .venv/Scripts/activate; fi
fi

python -m src.main