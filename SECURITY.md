# Seguridad, privacidad y licencias

## Alcance

Este repositorio procesa fixtures públicos derivados y, con consentimiento
explícito, puede enviar un state limitado a TypeSafe. El modo por defecto es
mock. El mock no es una evaluación de Jev.

## Antes de live

- Usa sólo los fixtures incluidos o datos para los que tengas autorización.
- El retail público no contiene stock, costo ni margen; no los agregues como
  overlay para simular inventario.
- El corpus de tickets declara ser generado y no contener PII. Aun así se
  aplica sanitización local de emails, teléfonos, DNI y tarjetas antes de live.
- La sanitización es una barrera básica, no anonimización. No subas datos
  internos, personales, de producción o PII.
- `--allow-remote` o `CATALOG_JUDGE_ALLOW_REMOTE=1` es obligatorio para live.
- El texto de entrada no se escribe en evidence JSON. Los exports de
  ejecución omiten texto por defecto.

## Logging y errores

`TYPESAFE_LOG_LEVEL=debug` se rechaza en live porque el SDK puede registrar
bodies. El wrapper no persiste bodies remotos, keys ni texto completo. 401,
429, timeout, conexión y contrato incompleto producen `error` y no aprobación
silenciosa.

## Licencias de datos

- El código de este repo: MIT.
- Mirror público de demanda de Favorita: se cita junto al dataset original de
  Kaggle; no se redistribuye el raw ni se sustituyen sus condiciones.
- Corpus público de tickets: CC BY-NC 4.0. El MIT del código no sustituye esta
  licencia.

Ver [`DATA_SOURCES.md`](DATA_SOURCES.md) para URLs, hashes y el procedimiento
de preparación. No incluyas secretos ni texto crudo de terceros en issues.
