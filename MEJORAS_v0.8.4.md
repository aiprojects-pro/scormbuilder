# SCORM Builder v0.8.4

Actualizacion de produccion entregada el 9 de junio de 2026.

## Cambios

- **#78 - Carga batch ordenada por numero de tema.** Los DOCX se ordenan por
  el numero extraido del nombre antes de procesarlos y conservan ese numero al
  combinarse. Esto evita temas duplicados o titulos cruzados cuando los
  archivos se seleccionan en un orden distinto al alfabetico.
- **#79 - Exportacion Aiken y GIFT.** Aiken deja de generar lineas `COMMENT:`,
  incompatibles con la importacion estandar de Moodle. El editor permite
  generar GIFT cuando se necesita retroalimentacion por respuesta.
- **Descarga de bancos GIFT.** La biblioteca y el ZIP de bancos incluyen ahora
  las carpetas `gift/` y `gift_extendido/`, identificando el formato de cada
  fichero.

## Validacion comunicada con la entrega

La entrega reporta 130 de 130 comprobaciones correctas:

- Auditoria general v0.8.4: 82/82.
- Carga batch ordenada: 23/23.
- Aiken y GIFT: 25/25.

El paquete recibido fue verificado antes de integrarlo:

```text
Archivo: scormbuilder-main-PARCHEADO.zip
SHA-256: 2d9bd553f05a057474b32e93278d9a39ab33bb9f25a9a6857c570fb285203027
```

Los scripts de auditoria mencionados en la comunicacion de entrega no forman
parte del ZIP. Las pruebas disponibles en el repositorio deben ejecutarse
antes de publicar esta version.
