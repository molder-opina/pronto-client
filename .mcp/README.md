# Chrome MCP Configuration

## Overview

This directory contains the configuration for Chrome MCP (Model Context Protocol) server, enabling browser automation and AI model integration.

## Installation

```bash
# The Chrome MCP package is already installed as a dependency
npm install @eddym06/custom-chrome-mcp --save
```

## Configuration

### 1. Set up API Keys

Copy the example environment file and configure your API keys:

```bash
cp .mcp/.env.example .mcp/.env
# Edit .mcp/.env with your API keys
```

Available providers:

- **OpenAI** (`OPENAI_API_KEY`) - GPT-4, GPT-3.5
- **Anthropic** (`ANTHROPIC_API_KEY`) - Claude
- **MiniMax** (`MINIMAX_API_KEY`) - Chinese LLM
- **GLM** (`GLM_API_KEY`) - Zhipu AI / ChatGLM
- **DeepSeek** (`DEEPSEEK_API_KEY`) - DeepSeek V3

### 2. Start the MCP Server

```bash
# Basic start
.mcp/start-chrome-mcp.sh

# With custom Chrome path
CHROME_PATH=/usr/bin/chromium .mcp/start-chrome-mcp.sh

# Headless mode
HEADLESS=true .mcp/start-chrome-mcp.sh
```

## Usage with Claude Code

To use with Claude Code CLI:

```bash
# Start MCP server in background
.mcp/start-chrome-mcp.sh &

# Use with Claude
claude --mcp-server chrome "navigate to https://example.com"
```

## Available Tools

The Chrome MCP server provides 91+ tools including:

- `navigate` - Navigate to a URL
- `click` - Click elements
- `type` - Type text
- `screenshot` - Take screenshots
- `evaluate` - Execute JavaScript
- `network_capture` - Capture network requests
- `har_record` - Record HAR files
- `accessibility_test` - Test accessibility

## Environment Variables

| Variable            | Description                 | Default                               |
| ------------------- | --------------------------- | ------------------------------------- |
| `CHROME_PATH`       | Path to Chrome executable   | `/Applications/Google Chrome.app/...` |
| `HEADLESS`          | Run Chrome in headless mode | `false`                               |
| `DEBUG`             | Enable debug mode           | `false`                               |
| `MCP_PORT`          | MCP server port             | `3000`                                |
| `OPENAI_API_KEY`    | OpenAI API key              | -                                     |
| `ANTHROPIC_API_KEY` | Anthropic API key           | -                                     |
| `MINIMAX_API_KEY`   | MiniMax API key             | -                                     |
| `GLM_API_KEY`       | GLM API key                 | -                                     |
| `DEEPSEEK_API_KEY`  | DeepSeek API key            | -                                     |

## Troubleshooting

### Chrome not found

```bash
# Find Chrome path
which google-chrome  # Linux
ls /Applications/Google\ Chrome.app/Contents/MacOS/  # macOS

# Set manually
CHROME_PATH=/full/path/to/chrome .mcp/start-chrome-mcp.sh
```

### Port already in use

```bash
MCP_PORT=3001 .mcp/start-chrome-mcp.sh
```

### Connection refused

Ensure Chrome MCP is running and the port matches your configuration.
