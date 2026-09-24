# Rúbrica de curación `ticket-rubric-v2`

Esta rúbrica define el gold **y** el texto que va a Jev. La misma frase
vale para etiquetar y para `instructions`/`criteria`. `expected_route` no
se etiqueta a mano: el código la compone con `compose_expected_route`
(`routing.py` + umbrales congelados).

Protocolo v5. No se usa para re-medir el confirmation v4.

## Área (`expected_area`)

Dueño primario del problema, uno solo.

| Valor | Qué es | No es |
|---|---|---|
| `tecnologia` | App, sistema, dispositivo, integración o error técnico | Entrega tardía de un producto que funciona (`logistica`) |
| `logistica` | Entrega, pedido, stock, transporte o almacén | Pregunta de cobro/factura de ese pedido (`pagos`) |
| `ventas` | Precio, cotización, promoción o compra | Qué significa un cargo en la factura (`pagos` / `atencion_cliente`) |
| `pagos` | Cargo, factura, pago, reembolso o medio de pago | Queja de entrega que menciona el precio (`logistica`) |
| `seguridad` | Acceso, credenciales, fraude, privacidad o datos | Login genérico sin acceso indebido ni fraude (`tecnologia`) |
| `rrhh` | Personas, contratación o proceso de RR. HH. | Pedir que un humano revise el ticket |
| `atencion_cliente` | Relación de servicio, seguimiento o explicación general **con dueño identificable** | Tema que no encaja en ninguna área (`otro`) |
| `otro` | El tema **no es** ninguna área de arriba (vacío, fuera de dominio, sin dueño) | Fallback por baja confianza |

## Intent (`expected_intent`)

| Valor | Qué es | No es |
|---|---|---|
| `consulta` | Pide información o una explicación | Pide que hagan algo (`solicitud`) |
| `incidencia` | Reporta un fallo o un comportamiento incorrecto | Insatisfacción sin fallo (`reclamo`) |
| `reclamo` | Algo **ya salió mal** y lo reporta o pide que lo arreglen | Pedido nuevo sin problema previo (`solicitud`) |
| `solicitud` | Pide una acción nueva sin fallar nada todavía | “Arreglen X que está roto” (`incidencia` o `reclamo`) |
| `retroalimentacion` | Opinión, sugerencia o mejora | Sugerencia forzada por un fallo (`incidencia`) |
| `otro` | No encaja arriba o el texto no tiene intención | Fallback por duda |

Borde reembolso: “solicito la devolución del cobro duplicado” = `reclamo`
(hay un problema previo). “Quiero pedir un reembolso, ¿cuál es el paso?”
sin cargo erróneo = `solicitud`.

## Urgencia (`expected_urgency`)

Clasifica la **situación descrita**, no la emoción. No se calculan plazos.

- `low`: puede esperar; no hay consecuencia inmediata.
- `medium`: conviene pronto, no bloquea un servicio.
- `high`: impacto importante hoy o en la ventana operativa.
- `critical`: seguridad, fraude o caída que no puede esperar.

`critical` solo con señal concreta de seguridad/fraude/caída. Palabras
fuertes sin bloqueo se quedan en `medium`.

## Humano (`expected_human`)

`true` si el mensaje está **ambiguo**, **contradictorio**, o exige una
**excepción de especialista** que un flujo automático no debe cerrar.

`false` si el caso es clasificable y la acción estándar está clara.
“¿Qué documentación necesito para X?” con X claro es `false`.
“La factura no coincide” con desglose pedido es `false` (acción estándar).
Instrucciones opuestas, titular vs tercero, o “no sé qué pedí” es `true`.

Contrato v6: Jev responde esta dimensión con tres preguntas atómicas
(`is_ambiguous`, `is_contradictory`, `needs_specialist`) y el código
compone con OR. El gold sigue siendo esta única columna: las filas
curadas antes de v6 se materializan como `needs_specialist =
expected_human` (`is_ambiguous`/`is_contradictory` = 0.0), de modo que
`compose_expected_route` no altera su `expected_route` congelado.

## Seguridad legal (`expected_security_legal`)

`true` solo con acceso indebido, credenciales, fraude, datos sensibles,
privacidad u obligación legal concreta. La palabra “seguridad” no basta.

## Reembolso (`expected_refund`)

`true` si pide devolver dinero, cambiar, reemplazar o un equivalente.
Preguntar “¿qué opciones tengo?” es `false`.

## Actionability (`expected_actionability`)

- `no_action`: solo un sentimiento, o texto vacío. No hay tarea.
- `clarification`: hay una tarea pero **falta el objeto** (cuál pedido,
  cuál ítem, cuál cuenta) o el paso concreto.
- `standard_action`: se identifica la tarea y el objeto, aunque el párrafo
  sea corto.
- `immediate_action`: acción inmediata con riesgo o impacto que no espera.

Una solicitud genérica autocontenida (cotización, compatibilidad, siguiente
paso de un reembolso ya pedido) es `standard_action`, no `clarification`.

## Repro técnico (`expected_technical_repro`)

`true` si hay problema técnico **y** pasos, disparador, mensaje de error
o evidencia. “La app no funciona” es `false`.

## Ruta (`expected_route`)

No se etiqueta. `compose_expected_route` aplica:

- `review` si `expected_human`, seguridad, urgencia `high`/`critical`,
  `actionability=no_action`, área/intent `otro`, o repro técnico bajo en
  ticket `tecnologia` de impacto alto.
- `clarification` **no** veta: se deriva y se deja constancia.
- `refund` cambia destino a pagos; no veta solo.

`accept` = clasificación aceptada para derivar, no “caso resuelto”.
