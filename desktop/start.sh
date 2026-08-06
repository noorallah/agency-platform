#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Agency Platform — Flutter Desktop Launcher
# Usage:
#   ./start.sh              → clean + get + run (Windows desktop, default)
#   ./start.sh --no-clean   → skip flutter clean (faster restart)
#   ./start.sh --linux      → run on Linux desktop
#   ./start.sh --macos      → run on macOS desktop
#   ./start.sh --web        → run on web (Chrome)
#   ./start.sh --profile    → run in profile mode (performance tracing)
#   ./start.sh --release    → run in release mode
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }
step()    { echo -e "\n${BOLD}── $* ──────────────────────────${RESET}"; }

# ── Defaults ──────────────────────────────────────────────────────────────────
SKIP_CLEAN=false
TARGET="windows"
BUILD_MODE="debug"

# ── Parse arguments ───────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --no-clean)  SKIP_CLEAN=true ;;
    --linux)     TARGET="linux" ;;
    --macos)     TARGET="macos" ;;
    --web)       TARGET="web" ;;
    --windows)   TARGET="windows" ;;
    --profile)   BUILD_MODE="profile" ;;
    --release)   BUILD_MODE="release" ;;
    --help|-h)
      echo -e "${BOLD}Usage:${RESET} ./start.sh [OPTIONS]"
      echo ""
      echo "  --no-clean    Skip flutter clean (faster restart)"
      echo "  --windows     Run on Windows desktop (default)"
      echo "  --linux       Run on Linux desktop"
      echo "  --macos       Run on macOS desktop"
      echo "  --web         Run on web (Chrome)"
      echo "  --profile     Profile mode (performance tracing)"
      echo "  --release     Release mode"
      echo ""
      exit 0
      ;;
    *) warn "Unknown argument: $arg (ignored)" ;;
  esac
done

# ── Header ────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}${CYAN}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║   Agency Platform — Flutter Desktop          ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════╝${RESET}\n"
info "Target : ${TARGET}"
info "Mode   : ${BUILD_MODE}"
info "Clean  : $([ "$SKIP_CLEAN" = true ] && echo 'skipped' || echo 'yes')"

# ── Prerequisites ─────────────────────────────────────────────────────────────
step "Checking prerequisites"
command -v flutter >/dev/null 2>&1 || error "flutter not found. Install from https://flutter.dev"
success "Flutter found: $(flutter --version --machine 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get(\"frameworkVersion\", \"?\"))' 2>/dev/null || flutter --version 2>&1 | head -1)"

# ── Move to script directory ───────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
info "Working directory: $SCRIPT_DIR"

# ── Flutter clean ─────────────────────────────────────────────────────────────
if [ "$SKIP_CLEAN" = false ]; then
  step "Flutter clean"
  flutter clean
  success "Clean complete"
fi

# ── Flutter pub get ───────────────────────────────────────────────────────────
step "Getting dependencies"
flutter pub get
success "Dependencies resolved"

# ── Enable desktop if needed ──────────────────────────────────────────────────
if [[ "$TARGET" != "web" ]]; then
  step "Enabling $TARGET desktop support"
  flutter config --enable-${TARGET}-desktop 2>/dev/null || true
fi

# ── Run ───────────────────────────────────────────────────────────────────────
step "Starting app  →  flutter run -d $TARGET --$BUILD_MODE"
echo ""

case "$BUILD_MODE" in
  debug)   flutter run -d "$TARGET" ;;
  profile) flutter run -d "$TARGET" --profile ;;
  release) flutter run -d "$TARGET" --release ;;
esac
