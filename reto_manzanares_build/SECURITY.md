# Seguridad y tratamiento de información

Esta versión es un núcleo de piloto, no una autorización automática para tratar
datos personales en producción.

## Controles incorporados

- API limitada a `localhost` por defecto.
- Token obligatorio al exponer la API en otra interfaz.
- Límite de tamaño para solicitudes HTTP.
- Respuestas sin caché y cabeceras de endurecimiento básicas.
- Auditoría por ejecución sin almacenar la pregunta en texto plano.
- Integridad referencial, migraciones versionadas y health check de SQLite.
- Ejecución de contenedor con usuario no privilegiado y sistema de archivos de
  solo lectura.
- LLM desactivado por defecto; la operación determinística continúa disponible.

## Controles requeridos antes de producción

- Integrar identidad corporativa, autorización por rol y rotación de secretos.
- Cifrar discos, copias de seguridad y tráfico mediante infraestructura
  administrada por la empresa.
- Definir consentimiento, finalidad, retención, eliminación y atención de
  derechos de los titulares según la normativa y políticas aplicables.
- Enmascarar datos en ambientes de prueba y separar datos demo de datos reales.
- Centralizar logs, alertas, backups y pruebas periódicas de restauración.
- Realizar análisis de vulnerabilidades y prueba de penetración.
- Migrar a PostgreSQL administrado cuando la concurrencia o criticidad supere el
  alcance de un piloto local.

No deben almacenarse contraseñas, tokens ni credenciales reales dentro del
repositorio o de archivos de ejemplo.
