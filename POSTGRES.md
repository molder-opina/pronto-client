# Scripts de PostgreSQL Local

Este directorio contiene scripts para controlar una instancia local de PostgreSQL separada del aplicativo.

## 📁 Scripts Disponibles

### Control de PostgreSQL

| Script                    | Descripción                                                      |
| ------------------------- | ---------------------------------------------------------------- |
| `bin/postgres-up.sh`      | Iniciar contenedor de PostgreSQL local                           |
| `bin/postgres-down.sh`    | Detener contenedor de PostgreSQL local (mantiene datos)          |
| `bin/postgres-rebuild.sh` | Reconstruir contenedor de PostgreSQL (opcional: `--remove-data`) |
| `bin/postgres-logs.sh`    | Ver logs de PostgreSQL en tiempo real                            |
| `bin/postgres-psql.sh`    | Conectar a la base de datos vía psql                             |

### Backups y Restore

| Script                              | Descripción                      |
| ----------------------------------- | -------------------------------- |
| `bin/postgres-backup.sh`            | Crear backup de la base de datos |
| `bin/postgres-restore.sh <archivo>` | Restaurar backup desde archivo   |

### Inicialización

| Script                 | Descripción                                        |
| ---------------------- | -------------------------------------------------- |
| `bin/init/postgres.sh` | Inicializar PostgreSQL con migraciones y seed data |

## 🚀 Inicio Rápido

### 1. Iniciar PostgreSQL Local

```bash
bash bin/postgres-up.sh
```

Esto iniciará PostgreSQL con:

- Host: `localhost:5432`
- Usuario: `pronto` (configurable vía `POSTGRES_USER`)
- Password: `pronto123` (configurable vía `POSTGRES_PASSWORD`)
- Base de datos: `pronto` (configurable vía `POSTGRES_DB`)

### 2. Inicializar Base de Datos

```bash
bash bin/init/postgres.sh
```

### 3. Activar PostgreSQL Local en Aplicaciones

Para que las aplicaciones usen PostgreSQL local en lugar de Supabase:

**Via docker-compose.yml:**

```bash
USE_LOCAL_POSTGRES=true docker compose up -d
```

**Via config/general.env:**

```bash
echo "USE_LOCAL_POSTGRES=true" >> config/general.env
```

## 📊 Comandos Útiles

### Conectar a PostgreSQL

**Desde el host:**

```bash
psql -h localhost -p 5432 -U pronto -d pronto
```

**Desde Docker:**

```bash
docker exec -it pronto-postgres psql -U pronto -d pronto
```

**Usando script:**

```bash
bash bin/postgres-psql.sh
```

### Ver Logs

```bash
bash bin/postgres-logs.sh
```

### Hacer Backup

```bash
bash bin/postgres-backup.sh
```

Los backups se guardan en `backups/postgres/` con formato: `pronto_backup_YYYYMMDD_HHMMSS.sql`

### Restaurar Backup

```bash
# Listar backups disponibles
bash bin/postgres-restore.sh

# Restaurar backup específico
bash bin/postgres-restore.sh backups/postgres/pronto_backup_20250115_120000.sql
```

## 🗄️ Gestión de Datos

### Reconstruir PostgreSQL

```bash
# Reconstruir manteniendo datos
bash bin/postgres-rebuild.sh

# Reconstruir eliminando todos los datos
bash bin/postgres-rebuild.sh --remove-data
```

### Detener PostgreSQL

```bash
bash bin/postgres-down.sh
```

Los datos se preservan en el volumen Docker `postgres_data`.

## 🔧 Configuración

Las siguientes variables de entorno controlan PostgreSQL local:

| Variable             | Default     | Descripción                                |
| -------------------- | ----------- | ------------------------------------------ |
| `POSTGRES_HOST`      | `postgres`  | Host de PostgreSQL (nombre del contenedor) |
| `POSTGRES_PORT`      | `5432`      | Puerto de PostgreSQL                       |
| `POSTGRES_USER`      | `pronto`    | Usuario de PostgreSQL                      |
| `POSTGRES_PASSWORD`  | `pronto123` | Contraseña de PostgreSQL                   |
| `POSTGRES_DB`        | `pronto`    | Nombre de la base de datos                 |
| `POSTGRES_HOST_PORT` | `5432`      | Puerto expuesto al host                    |
| `USE_LOCAL_POSTGRES` | `false`     | Usar PostgreSQL local en lugar de Supabase |

## 📁 Estructura de Archivos

```
pronto-app/
├── bin/
│   ├── postgres-up.sh          # Iniciar PostgreSQL
│   ├── postgres-down.sh        # Detener PostgreSQL
│   ├── postgres-rebuild.sh    # Reconstruir PostgreSQL
│   ├── postgres-logs.sh      # Ver logs
│   ├── postgres-psql.sh      # Conectar a psql
│   ├── postgres-backup.sh    # Hacer backup
│   └── postgres-restore.sh   # Restaurar backup
├── bin/init/
│   └── postgres.sh          # Inicializar base de datos
├── scripts/
│   └── init-db.sh          # Script de inicialización Docker
├── backups/postgres/        # Directorio de backups (creado automáticamente)
└── docker-compose.yml       # Definición de servicios Docker
```

## 🔄 PostgreSQL vs Supabase

El sistema soporta **ambas** bases de datos simultáneamente:

| Característica    | Supabase (Remoto)          | PostgreSQL (Local)         |
| ----------------- | -------------------------- | -------------------------- |
| Uso por defecto   | ✅ Sí                      | ❌ No                      |
| Requiere variable | -                          | `USE_LOCAL_POSTGRES=true`  |
| Conexión          | Via variables `SUPABASE_*` | Via variables `POSTGRES_*` |
| Almacenamiento    | Cloud (Supabase)           | Local (Docker volume)      |
| Latencia          | Media (internet)           | Mínima (localhost)         |
| Costo             | Plan gratuito disponible   | Gratis (Docker)            |
| Backup            | Automático                 | Manual (scripts)           |

### Migración de Supabase a Local

```bash
# 1. Iniciar PostgreSQL local
bash bin/postgres-up.sh

# 2. Activar uso de PostgreSQL local
export USE_LOCAL_POSTGRES=true

# 3. Reiniciar aplicaciones
docker compose restart client employee

# 4. Las tablas se crearán automáticamente (SQLAlchemy)
```

## 🛠️ Solución de Problemas

### PostgreSQL no inicia

```bash
# Ver logs
bash bin/postgres-logs.sh

# Verificar estado del contenedor
docker ps | grep pronto-postgres

# Reconstruir completamente
bash bin/postgres-rebuild.sh --remove-data
```

### Puerto 5432 ya en uso

```bash
# Verificar qué está usando el puerto
lsof -i :5432

# Cambiar puerto en config/general.env
echo "POSTGRES_HOST_PORT=5433" >> config/general.env

# Reiniciar PostgreSQL
bash bin/postgres-rebuild.sh
```

### Errores de conexión

```bash
# Verificar que PostgreSQL esté corriendo
docker ps | grep pronto-postgres

# Verificar que USE_LOCAL_POSTGRES esté activado
docker exec pronto-employee env | grep USE_LOCAL_POSTGRES

# Verificar variables de conexión
docker exec pronto-employee env | grep POSTGRES
```

## 📚 Recursos

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Docker PostgreSQL Image](https://hub.docker.com/_/postgres)
- [psql Cheat Sheet](https://gist.github.com/Kartones/dd3ff5ec5e231435eae)
