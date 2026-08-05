# Arquitectura y modelo de operación

## Decisión de diseño

La solución se plantea como un núcleo de piloto empresarial: pequeño, portable y
auditable. No intenta sustituir un CRM corporativo en 16 semanas. Su propósito es
validar el proceso, los datos, las reglas de priorización y el impacto comercial
antes de comprometer una plataforma de mayor costo.

## Componentes

1. **Canales de entrada.** CLI para demostración y operación controlada; API HTTP
   interna para integración.
2. **Coordinador.** Clasifica la solicitud y activa únicamente los agentes
   necesarios.
3. **Agentes determinísticos.** Calculan diagnóstico, segmentación, score, tareas,
   reactivación y experimentos desde datos registrados.
4. **Redactor.** Produce un briefing determinístico. Ollama puede mejorar la
   redacción, pero no es fuente de cifras ni condición de disponibilidad.
5. **Persistencia.** SQLite con esquema versionado, claves foráneas, WAL, índices,
   auditoría y backups consistentes.

## Flujo operativo diario

1. Validar el health check y revisar tareas vencidas.
2. Sincronizar fuentes autorizadas mediante importación validada.
3. Generar la cola priorizada.
4. Ejecutar contactos y registrar resultado, objeción y siguiente acción.
5. Cerrar tareas relacionadas.
6. Revisar tablero al final de la jornada.
7. Ejecutar backup según la política acordada.

## Continuidad y recuperación

- Ejecutar `python3 app.py backup` diariamente durante el piloto.
- Copiar los backups a almacenamiento corporativo cifrado.
- Probar restauración al menos una vez por sprint.
- Definir RPO y RTO con el área de tecnología antes de operar datos reales.
- No sincronizar manualmente el archivo SQLite mientras está abierto; usar el
  comando de backup.

## Escalamiento

La migración a PostgreSQL se recomienda cuando aparezca cualquiera de estas
condiciones:

- múltiples procesos de escritura concurrente;
- integración en tiempo real con varios sistemas;
- alta disponibilidad o recuperación multi-zona;
- volumen o retención que exceda la operación cómoda de un archivo local;
- políticas corporativas que prohíban bases embebidas.

En esa fase deben separarse repositorio, servicio de aplicación, base de datos,
cola de trabajos y observabilidad. Las reglas de scoring y agentes pueden
mantenerse como dominio independiente.

## Observabilidad mínima

El piloto registra:

- identificador único por ejecución;
- intención y número de agentes solicitados/completados;
- duración total;
- uso o degradación del LLM;
- aportes y errores por agente sin guardar la pregunta en texto plano;
- integridad, versión de esquema y errores de claves foráneas.

Para producción, estos eventos deben enviarse al sistema corporativo de logs y
alertas, con métricas de latencia, error, volumen y saturación.

## Gobierno de datos

Antes de cargar datos reales deben definirse propietario, custodio, finalidad,
base de autorización, campos mínimos, clasificación, retención y eliminación.
Los ambientes de desarrollo y demostración deben usar datos sintéticos o
enmascarados.
