"""Construye el lote de confirmation v5 (50 textos nuevos, rúbrica v2).

No reutiliza las 100 filas de v4. `expected_route` lo compone el código.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from catalog_judge.tickets import compose_expected_route, ticket_text  # noqa: E402

OUT = ROOT / "tickets" / "data" / "tickets_v5_50.csv"

# (subject, body, area, intent, urgency, human, security, refund, actionability, repro)
CASES: list[tuple[str, str, str, str, str, bool, bool, bool, str, bool]] = [
    ("Cobro duplicado en la factura", "La factura muestra dos cargos idénticos y solicito la devolución del cobro repetido.", "pagos", "reclamo", "high", False, False, True, "standard_action", False),
    ("No entiendo un concepto de la factura", "Necesito una explicación de una línea del comprobante antes de pagarlo.", "pagos", "consulta", "low", False, False, False, "standard_action", False),
    ("Actualizar datos de facturación", "Solicito corregir el dato administrativo de la próxima factura antes de emitirla.", "pagos", "solicitud", "low", False, False, False, "standard_action", False),
    ("La cantidad facturada no coincide", "El importe no coincide con el detalle de la compra y pido una revisión del desglose.", "pagos", "incidencia", "medium", False, False, False, "standard_action", False),
    ("Ayuda con un pedido", "Ayúdenme con mi pedido, no indico cuál ni qué ocurrió.", "logistica", "solicitud", "low", True, False, False, "clarification", False),
    ("Paquete detenido en almacén", "El paquete lleva una semana en el almacén y no avanza a reparto.", "logistica", "incidencia", "high", False, False, False, "standard_action", False),
    ("Cambio de dirección de entrega", "Quiero cambiar la dirección de un envío que aún no sale.", "logistica", "solicitud", "medium", False, False, False, "standard_action", False),
    ("Faltó un componente en la entrega", "Llegó el pedido incompleto y solicito que completen la entrega del componente faltante.", "logistica", "reclamo", "high", False, False, False, "standard_action", False),
    ("La app se cierra al exportar", "Al pulsar exportar la aplicación se cierra. Ocurre siempre en el tercer paso y muestra error 500.", "tecnologia", "incidencia", "medium", False, False, False, "standard_action", True),
    ("La aplicación no funciona", "La app no funciona.", "tecnologia", "incidencia", "low", False, False, False, "standard_action", False),
    ("Error al iniciar sesión", "El inicio de sesión falla con un mensaje genérico, sin acceso indebido ni fraude.", "tecnologia", "incidencia", "medium", False, False, False, "standard_action", False),
    ("Acceso no autorizado a la cuenta", "Detecté un acceso no autorizado y necesito una revisión de seguridad hoy.", "seguridad", "incidencia", "critical", True, True, False, "immediate_action", False),
    ("Alguien usó mis credenciales", "Alguien usó mis credenciales sin permiso y pidió un cambio de clave.", "seguridad", "reclamo", "critical", True, True, False, "immediate_action", False),
    ("Enlace para restablecer contraseña", "¿Pueden enviarme el enlace para restablecer la contraseña de la cuenta?", "tecnologia", "solicitud", "medium", False, False, False, "standard_action", False),
    ("El precio no coincide con la propuesta", "El precio cotizado no coincide con la propuesta comercial que acepté.", "ventas", "reclamo", "medium", False, False, False, "standard_action", False),
    ("Pido una cotización nueva", "Pido una cotización para una compra nueva de tres unidades del mismo ítem.", "ventas", "solicitud", "low", False, False, False, "standard_action", False),
    ("¿Es compatible esta configuración?", "Antes de conectar, ¿esta configuración es compatible con el servicio contratado?", "tecnologia", "consulta", "low", False, False, False, "standard_action", False),
    ("Sugiero un modo oscuro", "Sugiero agregar un modo oscuro en la interfaz, no hay un fallo.", "tecnologia", "retroalimentacion", "low", False, False, False, "standard_action", False),
    ("Estado de un caso anterior", "Quiero el estado de mi caso anterior de atención, el de la semana pasada.", "atencion_cliente", "consulta", "low", False, False, False, "standard_action", False),
    ("Consulta sobre contratación", "Tengo una pregunta sobre el proceso de contratación del área de personas.", "rrhh", "consulta", "low", False, False, False, "standard_action", False),
    ("No sé qué producto contraté", "Escribo para pedir ayuda pero no recuerdo qué producto ni qué cuenta es.", "atencion_cliente", "consulta", "low", True, False, False, "clarification", False),
    ("Instrucciones opuestas en el mismo mensaje", "Cancelen el pedido y al mismo tiempo envíenlo hoy a la misma dirección, no sé cuál instrucción rige.", "logistica", "solicitud", "high", True, False, False, "clarification", False),
    ("Reembolso ya aceptado: siguiente paso", "La devolución ya fue aceptada; ¿cuál es el siguiente paso del reembolso?", "pagos", "solicitud", "medium", False, False, True, "standard_action", False),
    ("¿Qué opciones tengo?", "No estoy conforme con el resultado y pregunto qué opciones hay, sin pedir aún un reembolso.", "atencion_cliente", "consulta", "low", False, False, False, "standard_action", False),
    ("Gracias por la atención", "Gracias, todo estuvo bien.", "atencion_cliente", "retroalimentacion", "low", False, False, False, "no_action", False),
    ("Cargo que no reconozco", "Aparece un cargo adicional que no reconozco y solicito revisión del cobro.", "pagos", "reclamo", "high", False, False, True, "standard_action", False),
    ("Entrega que bloquea un compromiso hoy", "La entrega de hoy no llegó y bloquea un compromiso con un cliente en la tarde.", "logistica", "incidencia", "high", False, False, False, "immediate_action", False),
    ("Mensaje vacío de soporte", "…", "otro", "otro", "low", True, False, False, "no_action", False),
    ("Pedido de un tema que no es soporte", "Quiero la receta de un postre, no es un caso de producto ni de cuenta.", "otro", "consulta", "low", True, False, False, "clarification", False),
    ("Integración que no responde", "La integración con el sistema externo no responde desde esta mañana, sin mensaje de error.", "tecnologia", "incidencia", "high", False, False, False, "standard_action", False),
    ("Exportar en tres pasos: error 500", "En el paso 3 de exportar aparece error 500. Lo repetí dos veces con el mismo resultado.", "tecnologia", "incidencia", "medium", False, False, False, "standard_action", True),
    ("Cambio de medio de pago", "Quiero cambiar el medio de pago de la próxima cuota, aún no vence.", "pagos", "solicitud", "low", False, False, False, "standard_action", False),
    ("Promoción que no se aplicó", "La promoción vigente no se aplicó al precio de la compra ya cerrada.", "ventas", "reclamo", "medium", False, False, False, "standard_action", False),
    ("Alta de un servicio nuevo", "Quiero dar de alta un servicio adicional que aún no tengo contratado.", "ventas", "solicitud", "low", False, False, False, "standard_action", False),
    ("Qué documentación necesito para el alta", "Qué documentación necesito para dar de alta el servicio que ya seleccioné.", "atencion_cliente", "consulta", "low", False, False, False, "standard_action", False),
    ("Paquete entregado a otra persona", "El paquete lo recibió otra persona y pido localizar el envío.", "logistica", "incidencia", "high", False, False, False, "standard_action", False),
    ("Solicito reemplazo del artículo dañado", "El artículo llegó dañado y solicito el reemplazo por uno equivalente.", "logistica", "reclamo", "high", False, False, True, "standard_action", False),
    ("Fraude en un cargo", "Hay un cargo que parece fraude: no lo reconocí y pido bloquear el medio de pago hoy.", "seguridad", "reclamo", "critical", True, True, True, "immediate_action", False),
    ("Consulta de privacidad de datos", "Quiero saber qué datos personales guardan de mi cuenta, es una pregunta de privacidad.", "seguridad", "consulta", "medium", True, True, False, "standard_action", False),
    ("Sugerencia de filtro en el listado", "Sugiero un filtro por fecha en el listado, el actual funciona bien.", "tecnologia", "retroalimentacion", "low", False, False, False, "standard_action", False),
    ("Horario de atención", "¿Cuál es el horario de atención del canal de soporte?", "atencion_cliente", "consulta", "low", False, False, False, "standard_action", False),
    ("Boleta duplicada tras anular", "Anulé un documento y se emitió otro igual; pido corrección del duplicado.", "pagos", "incidencia", "medium", False, False, False, "standard_action", False),
    ("No encuentro el número de pedido", "Quiero seguimiento pero no tengo el número de pedido ni la fecha.", "logistica", "solicitud", "low", True, False, False, "clarification", False),
    ("Caída general del servicio", "El servicio no carga para nadie en la oficina; parece una caída general.", "tecnologia", "incidencia", "critical", True, False, False, "immediate_action", False),
    ("Corregir un dato de la próxima factura", "Hay un error de nombre en la próxima factura y pido corregirlo antes de emitirla.", "pagos", "solicitud", "low", False, False, False, "standard_action", False),
    ("El envío llegó bien, solo confirmo", "El envío llegó completo, solo confirmo recepción. Gracias.", "logistica", "retroalimentacion", "low", False, False, False, "no_action", False),
    ("Conflicto entre dos titulares", "Mi socio y yo damos instrucciones opuestas sobre cancelar o mantener el servicio.", "atencion_cliente", "solicitud", "high", True, False, False, "clarification", False),
    ("Cotización vs factura", "La factura no respeta los precios de la cotización firmada.", "ventas", "reclamo", "high", False, False, False, "standard_action", False),
    ("Pasos para conectar un dispositivo", "¿Cuáles son los pasos para conectar el dispositivo al servicio ya activo?", "tecnologia", "consulta", "low", False, False, False, "standard_action", False),
    ("Reclamo de demora sin reembolso", "El envío se retrasó tres días y quiero que quede registrado el reclamo, sin pedir dinero de vuelta.", "logistica", "reclamo", "medium", False, False, False, "standard_action", False),
]


def main() -> None:
    if len(CASES) != 50:
        raise SystemExit(f"se esperaban 50 casos, hay {len(CASES)}")
    subjects = [item[0] for item in CASES]
    if len(set(subjects)) != 50:
        raise SystemExit("hay asuntos duplicados")
    rows = []
    for index, (subject, body, area, intent, urgency, human, security, refund, action, repro) in enumerate(CASES, start=1):
        row = {
            "source_id": f"v5-row-{index:03d}",
            "source_dataset": "catalog-judge/ticket-rubric-v2",
            "source_queue": area,
            "source_type": intent,
            "source_priority": urgency,
            "subject_es": subject,
            "body_es": body,
            "texto": ticket_text({"subject_es": subject, "body_es": body}),
            "expected_area": area,
            "expected_intent": intent,
            "expected_urgency": urgency,
            "expected_human": human,
            "expected_security_legal": security,
            "expected_refund": refund,
            "expected_actionability": action,
            "expected_technical_repro": repro,
            "curation_note": "Texto nuevo rubricado con ticket-rubric-v2; confirmation v5; no es el lote v4.",
            "evaluation_split": "confirmation",
        }
        row["expected_route"] = compose_expected_route(row)
        rows.append(row)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print({"rows": len(rows), "path": str(OUT), "routes": {row["expected_route"] for row in rows}})


if __name__ == "__main__":
    main()
