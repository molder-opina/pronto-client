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

1. `pronto-client` NO es dueño de `"/api/*"` de negocio.
2. Autoridad única de API: `pronto-api` en `:6082` bajo `"/api/*"`.
3. En `pronto-client` solo se permite SSR/UI; endpoints de negocio/API aquí ⇒ **REJECTED**.
4. Prohibido implementar o documentar rutas `"/{scope}/api/*"`.
5. Si existe compatibilidad temporal en este servicio, debe marcarse `deprecated: true` y tener fecha de retiro.

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
