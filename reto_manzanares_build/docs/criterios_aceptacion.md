# Criterios de aceptación del piloto

## Datos

- Al menos 95 % de los registros priorizados tiene teléfono, segmento y asesor.
- Cada contacto posee identificador externo estable.
- Los estados y valores inválidos son rechazados durante la importación.
- La empresa aprueba diccionario, finalidad, retención y responsables de datos.

## Operación

- La cola diaria se genera sin duplicar tareas pendientes.
- Una nueva recomendación reemplaza la anterior sin borrar el historial.
- Cada interacción puede cerrar una tarea y actualizar la fecha de contacto.
- El health check informa integridad correcta y versión de esquema vigente.
- Existe evidencia de restauración exitosa desde un backup.

## Analítica

- Cada prioridad muestra score, componentes y razones.
- La línea base y la meta contractual están validadas por la empresa.
- Pipeline, conversión e ingreso atribuible tienen definiciones acordadas.
- Los pilotos incluyen grupo de control o comparación válida cuando aplique.

## Seguridad

- La API expuesta exige autenticación y opera detrás de TLS corporativo.
- Los secretos no están en el repositorio.
- Los accesos, roles y bajas de usuarios siguen el proceso corporativo.
- Los datos de prueba están enmascarados o son sintéticos.

## Éxito comercial

Los porcentajes finales deben acordarse después del levantamiento. Como marco:

- aumento verificable de cobertura efectiva;
- reducción de oportunidades sin siguiente acción;
- mejora de conversión frente a línea base o control;
- ingreso incremental medible en reactivación y recompra;
- adopción sostenida por parte de asesores y líder comercial.

La cifra de 40 a 80 millones COP representa duplicación, no un aumento de 50 %.
El comité del piloto debe aprobar una sola definición antes de iniciar la
medición contractual.
