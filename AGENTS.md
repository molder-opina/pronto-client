Estas reglas complementan `AGENTS.md` raíz; no lo reemplazan.

## Reglas UI: normalización /api

Normalización UI (en este orden):
Reemplazar interpolaciones JS: ${...} → {var}
Convertir placeholders URL-encoded: %7B...%7D (case-insensitive) → {var}
Remover querystring: cortar en ?
Normalizar slashes: //+ → /
Asegurar leading /
Remover trailing / (salvo root /)

---

## API Canonica (/api) en pronto-client

1. Este servicio atiende `"/api/*"` solo para el host `clients.<dominio>`.
2. Prohibido implementar o documentar rutas `"/{scope}/api/*"` (scope aplica solo a web SSR en pronto-employees).
3. Aliases de compatibilidad:
   - Solo se agregan si `pronto-api-parity-check clients` reporta missing.
   - Deben delegar al handler canonico (no duplicar logica).
   - Si aplica, documentar alias como `deprecated: true` en OpenAPI.

## PRONTO_ROUTES_ONLY=1

1. `create_app()` debe soportar `PRONTO_ROUTES_ONLY=1`.
2. En `PRONTO_ROUTES_ONLY=1`, se permite solo registro de rutas/blueprints.
3. Prohibido side-effects en routes-only:
   - No DB init/schema validate
   - No Redis
   - No syncs/env/secrets
   - No schedulers/webhooks
   - No escritura a filesystem

## Gates

1. Se debe ejecutar `./pronto-scripts/bin/pronto-api-parity-check clients` cuando se cambie UI o endpoints.
