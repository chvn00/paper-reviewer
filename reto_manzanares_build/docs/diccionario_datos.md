# Diccionario de datos mínimo

## contacts

| Campo | Propósito |
|---|---|
| `external_id` | Identificador estable de la fuente empresarial |
| `name` | Nombre comercial del contacto |
| `phone`, `email` | Canales autorizados de contacto |
| `segment` | Segmento comercial acordado |
| `status` | `active`, `inactive` o `prospect` |
| `monthly_value` | Valor mensual histórico o potencial, según regla acordada |
| `days_since_purchase` | Recencia de compra; para prospectos debe ser 0 |
| `purchase_frequency` | Frecuencia histórica normalizada |
| `interest_score` | Señal observable entre 0 y 100 |
| `assigned_advisor` | Responsable de la gestión |
| `consent_status` | Estado de autorización definido por gobierno de datos |
| `data_source` | Origen del registro |

## opportunities

Registra etapa, valor estimado, probabilidad, siguiente acción y fecha. La
probabilidad debe estar entre 0 y 1 y debe calibrarse con cierres reales.

## interactions

Registra canal, resultado, notas y fecha. No debe usarse para almacenar datos
sensibles innecesarios ni credenciales.

## tasks

Registra prioridad, acción, vencimiento, estado, razón y ejecución que originó la
tarea. Las recomendaciones sustituidas se conservan con estado `superseded`.

## system_runs y audit_log

Proporcionan trazabilidad técnica por ejecución. La pregunta se representa por
un hash, reduciendo la exposición de información en logs.
