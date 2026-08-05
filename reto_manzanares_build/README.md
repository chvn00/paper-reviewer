# MANZANARES Growth Agent

Núcleo comercial auditable para transformar el contact center de la UEN Carnes
Manzanares en un canal medible, trazable y orientado al crecimiento.

La versión 2.0 convierte el prototipo inicial en una base sólida para un piloto
empresarial. Mantiene una operación simple y económica, pero incorpora controles
de datos, seguridad, trazabilidad, pruebas, backups y despliegue reproducible.

## Resultado de negocio

El sistema ayuda al equipo a:

- consolidar clientes, prospectos, oportunidades e interacciones;
- identificar la brecha entre ventas activas, pipeline y meta;
- priorizar contactos con un score explicable de 0 a 100;
- generar una cola diaria sin duplicar ni destruir tareas históricas;
- ejecutar pilotos de reactivación, prospección y recompra;
- medir calidad de datos, tareas vencidas, actividad y avance comercial;
- producir briefings determinísticos aun cuando el LLM no esté disponible.

La meta de pasar de 40 a 80 millones COP equivale a un crecimiento de 100 %. La
ficha también menciona un incremento de 50 %, por lo cual la meta contractual
debe aclararse durante el levantamiento.

## Arquitectura

```text
CLI / API interna
       |
Coordinador de intención
       |
       +-- Diagnóstico
       +-- Segmentación
       +-- Priorización explicable
       +-- Seguimiento idempotente
       +-- Reactivación
       +-- Growth experimental
       |
CRM SQLite versionado + auditoría + health checks + backups
       |
Síntesis determinística / Ollama local opcional
```

SQLite es apropiado para una prueba controlada de baja concurrencia. La capa de
acceso a datos concentra la lógica necesaria para migrar posteriormente a
PostgreSQL o a un CRM corporativo sin reescribir las reglas comerciales.

## Inicio rápido

Requiere Python 3.11 o superior. El runtime no necesita paquetes externos.

```bash
cd "/Users/cesarvalencia/Desktop/reto manzanares"
cp .env.example .env
python3 app.py inicializar
python3 app.py salud
python3 app.py tablero
```

Para reiniciar exclusivamente el entorno de demostración:

```bash
python3 app.py demo --reset
```

El modificador `--reset` elimina los datos actuales y por eso nunca debe usarse
con información real.

## Conversación libre

En macOS, haga doble clic en `Abrir Manzanares.command`. También puede iniciarla
desde Terminal:

```bash
python3 app.py conversar
```

La aplicación permanece abierta para recibir preguntas. Use `/tablero`,
`/salud`, `/ayuda` o `/salir`. Al final de cada respuesta generada por Ollama
se muestran los tokens de entrada, tokens de salida, velocidad en tokens por
segundo y tiempo total reportados por el modelo local.

## Operación

```bash
# Briefing legible
python3 app.py consultar "Dame prioridades y brecha comercial"

# Resultado estructurado para integración
python3 app.py consultar "Dame prioridades" --json

# Cola diaria
python3 app.py tareas --estado pending

# Registro de una gestión y cierre opcional de tarea
python3 app.py registrar-interaccion 1 \
  --canal telefono \
  --resultado contactado \
  --notas "Solicita propuesta" \
  --tarea 3

# Validación previa e importación CSV
python3 app.py importar-contactos data/contactos_ejemplo.csv --dry-run
python3 app.py importar-contactos data/contactos_ejemplo.csv

# Backup consistente
python3 app.py backup
```

## API interna

La API escucha en `127.0.0.1:8080` por defecto:

```bash
python3 app.py servir
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/api/v1/dashboard
```

Rutas disponibles:

| Método | Ruta | Función |
|---|---|---|
| `GET` | `/health` | Integridad, versión de esquema y disponibilidad |
| `GET` | `/api/v1/dashboard` | KPIs operativos y comerciales |
| `GET` | `/api/v1/tasks?status=pending` | Cola de trabajo |
| `POST` | `/api/v1/query` | Orquestación y briefing |
| `POST` | `/api/v1/interactions` | Registro de gestión comercial |

Si `API_HOST` se cambia para escuchar fuera de localhost, `API_TOKEN` se vuelve
obligatorio. Las solicitudes deben enviar `Authorization: Bearer <token>`.

La API está diseñada para ubicarse detrás del proxy, TLS e identidad corporativa;
no reemplaza esos componentes.

## Score comercial explicable

| Dimensión | Peso máximo |
|---|---:|
| Potencial económico | 30 |
| Interés observado | 25 |
| Tipo de relación | 15 |
| Urgencia o siguiente acción | 15 |
| Frecuencia histórica | 10 |
| Calidad mínima del registro | 5 |

El score entrega componentes y razones legibles. Los prospectos ya no reciben un
beneficio artificial por usar `999` como marcador de “sin compra”. Los pesos son
hipótesis iniciales y deben recalibrarse con conversión real.

## Datos y migraciones

La inicialización:

- detecta y migra automáticamente la base de la versión inicial;
- activa claves foráneas, WAL, timeout de bloqueo e índices;
- conserva tareas reemplazadas como historial;
- registra cada ejecución, duración, agentes completados y uso de LLM;
- verifica integridad y versión con `python3 app.py salud`.

El importador CSV valida campos, rangos y estados. Use siempre `--dry-run` antes
de importar información empresarial.

## Ollama opcional

La lógica comercial no depende de IA generativa. Para habilitar únicamente una
mejora de redacción local:

```bash
ollama serve
ollama pull gemma3:12b
```

Después configure `LLM_PROVIDER=ollama`. Si Ollama falla o excede el timeout, el
sistema conserva el resumen determinístico y reporta la degradación.

## Pruebas y calidad

```bash
make check
```

La suite cubre configuración segura, migraciones, integridad, protección de datos
demo, importación CSV, idempotencia de tareas, interacciones, scoring,
orquestación, auditoría, autenticación y health checks.

## Contenedores

```bash
export API_TOKEN='reemplace-este-valor'
docker compose up --build
```

El contenedor usa usuario no privilegiado, filesystem de solo lectura, health
check y volúmenes separados para datos y backups.

## Límites honestos del piloto

Antes de una salida productiva deben completarse identidad corporativa y roles,
cifrado administrado, gobierno de datos, observabilidad central, pruebas de
restauración, integración con inventario/facturación y migración a PostgreSQL si
la carga o concurrencia lo requiere.

Consulte [SECURITY.md](SECURITY.md), [arquitectura y operación](docs/arquitectura_operacion.md)
y [criterios de aceptación](docs/criterios_aceptacion.md).
