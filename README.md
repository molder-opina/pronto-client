# Pronto Client

Customer-facing web application for Pronto restaurant system.

## Requirements

- Python 3.11+
- pronto-shared library
- pronto-static assets

## Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r src/pronto_clients/requirements.txt
```

## Development

```bash
cd src/pronto_clients
flask run --port 5000
```

## Docker

```bash
# Build
docker compose build client

# Run (requires static and infra services)
docker compose --profile apps up client
```

## Project Structure

```
pronto-client/
└── src/
    └── pronto_clients/
        ├── app.py           # Flask application
        ├── routes/          # Route blueprints
        ├── services/        # Business logic
        ├── templates/       # Jinja2 templates
        ├── utils/           # Utility functions
        ├── requirements.txt
        ├── Dockerfile
        └── wsgi.py
```

## Features

- Digital menu browsing
- Cart and order placement
- Order tracking
- Payment processing
- Customer profile management

## Dependencies

- `pronto-shared>=1.0.0` - Shared models and services
- `gunicorn>=21.2.0` - WSGI server

## Environment Variables

See `.env.example` in the root directory for required configuration.
