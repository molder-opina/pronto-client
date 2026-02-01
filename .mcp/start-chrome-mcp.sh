#!/usr/bin/env bash
# Chrome MCP Server Launcher
# Conecta Chrome con MCP para automatización y uso con modelos AI

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_CONFIG_DIR="${SCRIPT_DIR}/.mcp"

# Configuración de Chrome
CHROME_PATH="${CHROME_PATH:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
HEADLESS="${HEADLESS:-false}"
DEBUG="${DEBUG:-false}"

# Configuración de Modelos AI (API keys)
OPENAI_API_KEY="${OPENAI_API_KEY:-}"
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
MINIMAX_API_KEY="${MINIMAX_API_KEY:-}"
GLM_API_KEY="${GLM_API_KEY:-}"
DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"

# Puerto para el servidor MCP
MCP_PORT="${MCP_PORT:-3000}"

echo "=========================================="
echo "  Chrome MCP Server Launcher"
echo "=========================================="
echo ""
echo "Configuración:"
echo "  Chrome: ${CHROME_PATH}"
echo "  Headless: ${HEADLESS}"
echo "  Debug: ${DEBUG}"
echo "  Puerto MCP: ${MCP_PORT}"
echo ""
echo "Modelos AI disponibles:"
echo "  - OpenAI: $([ -n "$OPENAI_API_KEY" ] && echo "✅ Configurado" || echo "❌ No configurado")"
echo "  - Anthropic: $([ -n "$ANTHROPIC_API_KEY" ] && echo "✅ Configurado" || echo "❌ No configurado")"
echo "  - MiniMax: $([ -n "$MINIMAX_API_KEY" ] && echo "✅ Configurado" || echo "❌ No configurado")"
echo "  - GLM: $([ -n "$GLM_API_KEY" ] && echo "✅ Configurado" || echo "❌ No configurado")"
echo "  - DeepSeek: $([ -n "$DEEPSEEK_API_KEY" ] && echo "✅ Configurado" || echo "❌ No configurado")"
echo ""

# Verificar que Chrome existe
if [ ! -f "$CHROME_PATH" ]; then
    echo "⚠️  Chrome no encontrado en: ${CHROME_PATH}"
    echo "   Buscando Chrome alternativo..."
    if command -v google-chrome &> /dev/null; then
        CHROME_PATH="google-chrome"
        echo "   Usando: ${CHROME_PATH}"
    elif command -v chromium &> /dev/null; then
        CHROME_PATH="chromium"
        echo "   Usando: ${CHROME_PATH}"
    else
        echo "❌ Error: Chrome no encontrado. Instala Chrome o configura CHROME_PATH"
        exit 1
    fi
fi

# Verificar que npx está disponible
if ! command -v npx &> /dev/null; then
    echo "❌ Error: npx no está disponible. Instala Node.js"
    exit 1
fi

echo "🚀 Iniciando Chrome MCP Server..."
echo ""

# Exportar variables de entorno para el servidor MCP
export CHROME_PATH
export HEADLESS
export DEBUG
export MCP_PORT

# Verificar si hay API keys configuradas
if [ -n "$OPENAI_API_KEY" ]; then
    export OPENAI_API_KEY
fi
if [ -n "$ANTHROPIC_API_KEY" ]; then
    export ANTHROPIC_API_KEY
fi
if [ -n "$MINIMAX_API_KEY" ]; then
    export MINIMAX_API_KEY
fi
if [ -n "$GLM_API_KEY" ]; then
    export GLM_API_KEY
fi
if [ -n "$DEEPSEEK_API_KEY" ]; then
    export DEEPSEEK_API_KEY
fi

# Iniciar el servidor MCP
exec npx -y "@eddym06/custom-chrome-mcp" \
    --chrome-path="$CHROME_PATH" \
    --headless="$HEADLESS" \
    --port="$MCP_PORT"
