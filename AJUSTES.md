# Ajustes pendientes / observaciones

## 2026-05-03

- Ajuste 1: Hacer visible y verificable la deteccion de titulo, abstract y keywords en el frontend. El parser los detecta en el backend para el PDF actual, pero `/upload` no estaba devolviendo esos textos, por lo que la UI no permitia confirmarlo.

- Ajuste 2: MethodologyReviewer debe revisar holisticamente todo el articulo y no depender de una seccion llamada metodologia; debe inferir lo que se hizo, la secuencia problema-modelo-experimento-validacion-conclusion y si la presentacion es adecuada.

- Ajuste 3: TitleAbstractKeywordsReviewer no debe caer en score 0 por error de parseo JSON de Phi-3 cuando el parser ya detecto titulo, abstract y keywords. Necesita prompt compacto y fallback deterministico.

- Ajuste 4: StructureReviewer no debe quedar en 0 por fallo de JSON de Phi-3; debe usar el mapa de secciones detectadas para producir una evaluacion deterministica minima de estructura y flujo.

- Ajuste 5: TitleAbstractKeywordsReviewer debe separar claramente comentarios de titulo, abstract y keywords. Si los tres campos fueron detectados, el puntaje no debe caer a valores extremadamente bajos por una salida descalibrada del modelo.

- Ajuste 6: StructureReviewer fallback no debe ser generico. Debe usar contenido real de introduccion, metodologia/framework, validacion/resultados, discusion y conclusiones para comentar flujo, orden y presentacion.

- Ajuste 7: Parser debe detectar ecuaciones numeradas en PDFs LaTeX con formato (1)...(51), incluyendo espacios internos y sin fallar por otros numeros entre parentesis del texto.

- Mejora 8: Implementada. Agregar historial de revisiones. Guarda por cada paper revisado: titulo detectado, nombre del archivo, fecha/hora, modo usado (fast/balanced/deep), modelo usado, puntaje final, decision editorial, duracion y ruta/enlace al reporte PDF generado. La UI muestra una vista de historico para descargar reportes anteriores sin repetir la revision.
