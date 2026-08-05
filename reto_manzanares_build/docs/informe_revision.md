# Informe de revisión industrial

Fecha: 25 de junio de 2026

## Diagnóstico inicial

El prototipo original demostraba correctamente la idea multiagente, pero tenía
riesgos importantes para presentarse como solución empresarial:

- esquema SQLite sin migraciones, índices ni claves foráneas activas;
- borrado de todas las tareas pendientes en cada ejecución;
- score que premiaba artificialmente a prospectos con 999 días sin compra;
- clasificación limitada a una sola intención;
- auditoría con texto comercial completo y sin estado por ejecución;
- configuración relativa al directorio desde el que se ejecutara;
- LLM con timeout alto y sin validación suficiente de respuesta;
- datos demo capaces de reemplazar información sin protección explícita;
- ausencia de API, health check, backup operativo e importación validada;
- una prueba que no era descubierta por el comando estándar;
- documentación útil, pero todavía orientada a prototipo.

## Mejoras implementadas

### Datos y confiabilidad

- Migraciones automáticas desde el esquema original.
- Claves foráneas, WAL, timeout, índices y verificación de integridad.
- Identificador externo, fuente, consentimiento y marcas de tiempo.
- Importación CSV con `dry-run`, validación de rangos y reporte de rechazos.
- Backup consistente mediante la API de SQLite.
- Protección para impedir que datos demo reemplacen una base no vacía sin
  `--reset`.

### Lógica comercial

- Score 0 a 100 con seis componentes y razones visibles.
- Corrección del marcador `999` para prospectos.
- Inclusión de urgencia por siguiente acción vencida.
- Orquestación multi-intención.
- Cola idempotente: crea, actualiza o reemplaza tareas conservando historial.
- Registro de interacciones y cierre transaccional de tareas.

### Operación y seguridad

- API interna con token obligatorio fuera de localhost.
- Límite de tamaño, respuestas sin caché y cabeceras básicas.
- Health check de integridad, claves foráneas y versión.
- Auditoría por ejecución con hash de pregunta, duración, agentes y uso de LLM.
- LLM desactivado por defecto, timeout configurable y fallback determinístico.
- Logging legible o JSON.
- Contenedor no privilegiado, filesystem de solo lectura y health check.

### Calidad y documentación

- 15 pruebas automatizadas compatibles con Python 3.12.
- Validación de migración de una base heredada sin pérdida.
- README operativo, seguridad, arquitectura, diccionario de datos y criterios de
  aceptación.
- Memoria técnica ejecutiva de 10 páginas, recompilada y revisada visualmente.

## Validaciones ejecutadas

- Compilación de todos los módulos Python.
- 15 de 15 pruebas aprobadas.
- Migración real de la base existente a esquema versión 2.
- `PRAGMA integrity_check`: `ok`.
- Cero errores de claves foráneas.
- Consulta multi-intención con resultado determinístico.
- Segunda ejecución sin duplicación de ocho tareas.
- Backup restaurable con 8 contactos y 11 tareas históricas.
- PDF generado sin desbordes de contenido.

## Límites que permanecen

La versión es adecuada para un piloto controlado, no para producción corporativa
sin trabajo adicional. Se requieren identidad y roles corporativos, TLS y
cifrado administrado, observabilidad central, política formal de datos,
integraciones con sistemas fuente, pruebas de carga y PostgreSQL cuando exista
concurrencia significativa.

## Recomendación

Presentar la solución como un piloto empresarial auditable, con puertas de
decisión en las semanas 2, 6, 12 y 16. Evitar venderla como CRM final. La promesa
debe centrarse en validar impacto comercial, adopción y calidad de datos dentro
del presupuesto y plazo disponibles.
