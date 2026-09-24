"""Prompts atómicos para Jev (contrato de tickets, 10 preguntas).

Tickets: una dimensión por pregunta; el código compone y decide la ruta.
``instructions`` estructuradas (``question``/``focus``/``decide``), Choice
con rúbrica de borde, Score con niveles situacionales y Noul con
``true``/``false``. Solo describe la rúbrica: los umbrales y las
etiquetas ``expected_*`` viven en el código, nunca en el prompt.

Retail usa la política de demanda de ``retail.py`` (Favorita no trae
texto de SKU). ``retail_questions`` queda como contrato para los tests
del wrapper SDK.
"""

from __future__ import annotations

from typing import Any

RETAIL_QUESTION_IDS = (
    "series_decision",
    "handling_risk",
    "exception_needed",
)

TICKET_QUESTION_IDS = (
    "area",
    "intent",
    "urgency",
    "is_ambiguous",
    "is_contradictory",
    "needs_specialist",
    "security_legal_risk",
    "refund_or_replacement",
    "actionability",
    "technical_repro",
)


def retail_questions() -> dict[str, Any]:
    """Contrato histórico de 3 preguntas de retail: solo para tests del wrapper SDK."""
    from typesafe_sdk import Choice, Noul

    return {
        "series_decision": Choice(
            instructions={
                "question": "Given `demand_bands` and `demand_pattern`, which assortment policy decision fits this public demand series?",
                "focus": "Judge the demand story told by the named bands (`volume`, `trend`, `presence`, `volatility`, `promo`). Do not infer stock, cost, margin, or inventory availability; the code owns the demand calculations.",
                "decide": "Pick the option whose `what` matches the bands; when two seem close, the `not_for` field says which neighbour wins.",
            },
            criteria={
                "include": {
                    "what": "Healthy demand story: present most days with a stable or growing trend.",
                    "not_for": "A declining trend, thin presence, or extreme volatility goes to `review`, not here.",
                    "examples": ["presence=alta with trend=estable goes here"],
                },
                "exclude": {
                    "what": "No usable demand: the series barely sells or is almost never present.",
                    "not_for": "Weak but nonzero demand with thin presence is `review`, not `exclude`.",
                    "examples": ["volume=nula or presence=muy_baja with volume=muy_baja goes here"],
                },
                "review": {
                    "what": "Anything in between: declining trend, thin presence, extreme volatility, or heavy promo dependence that needs a human or policy check.",
                    "not_for": "A clean stable/growing story with solid presence is `include`.",
                    "examples": ["trend=caida or volatility=extrema goes here"],
                },
            },
        ),
        "handling_risk": Noul(
            instructions={
                "question": "Does `demand_bands` indicate a handling, quality, or operational exception risk for this series?",
                "focus": "This is a semantic risk judgment over the named bands (`volatility`, `presence`, `promo`), not arithmetic over the raw floats. A heavy promo load alone counts: `promo`=`alta` is a risk even with solid presence.",
            },
            criteria={
                "true": {
                    "what": "The bands show extreme or high volatility, thin presence, or heavy promo dependence (`promo`=`alta`) that should not flow automatically.",
                    "examples": ["volatility=extrema, presence=baja, promo=alta even with presence=alta"],
                },
                "false": {
                    "what": "Ordinary demand shape: low or moderate volatility, solid presence, no or light promo.",
                    "not_for": "A merely declining or growing trend with ordinary volatility and presence is not handling risk by itself.",
                    "examples": ["volatility=moderada with presence=alta and promo=ligera"],
                },
            },
        ),
        "exception_needed": Noul(
            instructions={
                "question": "Does this series need a documented exception or human review under the demand policy?",
                "focus": "Answer from `demand_pattern` and `demand_bands` only. Do not invent a reason that is not supported by the state.",
            },
            criteria={
                "true": {
                    "what": "The state shows a falling trend, insufficient demand, or extreme volatility/absence that policy cannot pass silently.",
                    "examples": ["trend=caida, trend=insuficiente, volatility=extrema"],
                },
                "false": {
                    "what": "The series can follow the normal policy without an exception.",
                    "not_for": "Heavy promo alone, with solid presence and a stable trend, is not an exception by itself.",
                    "examples": ["trend=estable with presence=alta"],
                },
            },
        ),
    }


def tickets_questions() -> dict[str, Any]:
    """Diez preguntas atómicas; rúbrica v2 alineada con ``tickets/RUBRIC.md``."""
    from typesafe_sdk import Choice, Noul, Score

    return {
        "area": Choice(
            instructions={
                "question": "Which functional area owns the problem in `ticket.subject` and `ticket.body`? Select one area only.",
                "focus": "Match the core problem to exactly one owner. When billing and logistics overlap, the `not_for` fields decide.",
                "decide": "Read `what` for coverage and `not_for` for the neighbour that steals the case.",
            },
            criteria={
                "tecnologia": {
                    "what": "Application, system, device, integration, or technical error.",
                    "not_for": "A late delivery of a working product is logistica, not tecnologia.",
                    "examples": ["La app se cierra al exportar"],
                },
                "logistica": {
                    "what": "Delivery, order, stock, transport, or warehouse issue.",
                    "not_for": "A charge or invoice question about that order is pagos.",
                    "examples": ["El paquete lleva una semana en el almacén"],
                },
                "ventas": {
                    "what": "Price, quote, promotion, or purchase issue.",
                    "not_for": "Asking what a charge on the bill means is pagos or atencion_cliente, not ventas.",
                    "examples": ["El precio cotizado no coincide con la propuesta"],
                },
                "atencion_cliente": {
                    "what": "Service relationship or follow-up with an identifiable on-domain owner.",
                    "not_for": "If no area above matches, use otro. A billing line is pagos.",
                    "examples": ["Quiero el estado de mi caso anterior"],
                },
                "pagos": {
                    "what": "Charge, invoice, payment, refund, or payment-method issue.",
                    "not_for": "Complaining about delivery while mentioning the price stays logistica unless money must move.",
                    "examples": ["La factura muestra dos cargos idénticos"],
                },
                "seguridad": {
                    "what": "Access, credentials, fraud, privacy, data, or security issue.",
                    "not_for": "A generic login hiccup without access, credential, or fraud language is tecnologia.",
                    "examples": ["Alguien accedió a mi cuenta sin permiso"],
                },
                "rrhh": {
                    "what": "People, hiring, or human-resources process issue.",
                    "not_for": "Asking for a human to review a ticket is not rrhh.",
                    "examples": ["Consulta sobre el proceso de contratación"],
                },
                "otro": {
                    "what": "The topic is none of the areas above: empty, off-domain, or no identifiable owner.",
                    "not_for": "A generic but on-domain service question is atencion_cliente. Do not use otro because confidence is low.",
                    "examples": ["Texto vacío o un pedido sin ningún tema de soporte"],
                },
            },
        ),
        "intent": Choice(
            instructions={
                "question": "What is the main intent of `ticket.subject` and `ticket.body`?",
                "focus": "One intent. reclamo = something already went wrong. solicitud = a new action with no prior failure.",
                "decide": "A refund of a duplicate charge is reclamo. Asking the steps to request a refund, with no wrong charge, is solicitud.",
            },
            criteria={
                "consulta": {
                    "what": "The person asks for information or an explanation.",
                    "not_for": "Asking someone to do something is solicitud, not consulta.",
                    "examples": ["No entiendo un concepto de la factura"],
                },
                "incidencia": {
                    "what": "The person reports a failure or incorrect behavior.",
                    "not_for": "Dissatisfaction without a failure to report is reclamo.",
                    "examples": ["El botón de exportar falla"],
                },
                "reclamo": {
                    "what": "Something already went wrong and they report it or ask to fix it, including a refund of a bad charge.",
                    "not_for": "A new action with no prior problem is solicitud.",
                    "examples": ["Cobro duplicado; solicito la devolución del cargo repetido"],
                },
                "solicitud": {
                    "what": "The person requests a new action, change, or delivery with no prior failure.",
                    "not_for": "Fixing something that already broke is incidencia or reclamo, even if phrased as please fix.",
                    "examples": ["Necesito actualizar los datos de facturación de la próxima factura"],
                },
                "retroalimentacion": {
                    "what": "The person shares an opinion, suggestion, or improvement.",
                    "not_for": "A suggestion forced by a failure is incidencia first.",
                    "examples": ["Sugiero agregar un modo oscuro"],
                },
                "otro": {
                    "what": "The intent is unclear or does not fit the options above.",
                    "not_for": "Use only when no intent above matches.",
                    "examples": ["Mensaje sin contenido"],
                },
            },
        ),
        "urgency": Score(
            instructions={
                "question": "What urgency do `ticket.subject` and `ticket.body` state? Do not calculate time.",
                "focus": "Judge the situation described, not the emotion.",
            },
            criteria=[
                {
                    "what": "It can wait; no immediate consequence is stated.",
                    "examples": ["Consulta general para el próximo ciclo de revisión"],
                },
                {
                    "what": "It needs prompt attention but does not block a service.",
                    "examples": ["Un cargo a aclarar antes de la siguiente facturación"],
                },
                {
                    "what": "There is important impact that should be handled today or in the next operating window.",
                    "examples": ["Una entrega que bloquea un compromiso con un cliente hoy"],
                },
                {
                    "what": "There is a critical or security situation that must not wait.",
                    "examples": ["Acceso no autorizado a la cuenta"],
                },
            ],
        ),
        # Las tres señales humanas se componen con OR en la ruta y se
        # nombran la que dispara (ver routing.py).
        "is_ambiguous": Noul(
            instructions={
                "question": "Is `ticket.subject` or `ticket.body` ambiguous: does the message fail to identify what it is about?",
                "focus": "Unclear referent or unanswered 'which one': the person does not say which order, product, account, or previous request they mean. A clear standard request is false.",
            },
            criteria={
                "true": {
                    "what": "The message cannot be classified without guessing what it refers to.",
                    "examples": ["No sé qué pedí; revisen ustedes"],
                },
                "false": {
                    "what": "The referent is identifiable even if the ticket is short.",
                    "not_for": "A named-process information request is false; a specialist exception goes to needs_specialist, not here.",
                    "examples": ["La factura 4471 muestra dos cargos idénticos"],
                },
            },
        ),
        "is_contradictory": Noul(
            instructions={
                "question": "Do `ticket.subject` and `ticket.body` state opposed instructions or facts that cannot both be followed?",
                "focus": "Internal conflict inside one message: two directions that undo each other, or facts that clash. An ordinary complaint is false.",
            },
            criteria={
                "true": {
                    "what": "The message asks for two mutually exclusive things or contradicts itself.",
                    "examples": ["Cancele el pedido, pero igual envíenlo esta semana"],
                },
                "false": {
                    "what": "One consistent request, even a demanding one.",
                    "not_for": "A frustrated tone without conflicting instructions is false here.",
                    "examples": ["Cancelen el pedido 4471, ya no lo necesito"],
                },
            },
        ),
        "needs_specialist": Noul(
            instructions={
                "question": "Does the case require a specialist exception that an automatic flow must not close?",
                "focus": "A policy exception or a decision outside the standard flow: contract clauses, ownership disputes, or a requester who is not the account holder.",
            },
            criteria={
                "true": {
                    "what": "A specialist must decide an exception; the standard flow cannot close it.",
                    "examples": ["Mi expartner mantiene la cuenta y yo sigo pagando la suscripción"],
                },
                "false": {
                    "what": "The case is classifiable and the standard next action is clear.",
                    "not_for": "Ambiguous wording belongs to is_ambiguous; a plain information request is false here.",
                    "examples": ["La cantidad facturada no coincide y pido revisión"],
                },
            },
        ),
        "security_legal_risk": Noul(
            instructions={
                "question": "Do `ticket.subject` or `ticket.body` contain a concrete security, privacy, fraud, or legal risk?",
                "focus": "Concrete signals only: unauthorized access, credentials, fraud, sensitive data, privacy, or a concrete legal obligation. Mentions of the word security without such a signal do not count.",
            },
            criteria={
                "true": {
                    "what": "It mentions unauthorized access, credentials, fraud, sensitive data, privacy, or a concrete legal obligation.",
                    "examples": ["Alguien usó mis credenciales sin permiso"],
                },
                "false": {
                    "what": "It is an ordinary support problem without a concrete security or legal risk signal.",
                    "not_for": "A password reset link instruction is false; a request to disclose a password is true.",
                    "examples": ["Use este enlace para restablecer la contraseña"],
                },
            },
        ),
        "refund_or_replacement": Noul(
            instructions={
                "question": "Does the person ask in `ticket.body` to refund, return, exchange, or replace?",
                "focus": "An explicit request to move money or goods. A mere complaint without asking is not enough.",
            },
            criteria={
                "true": {
                    "what": "The person asks to return money, replace, exchange, or receive an equivalent item.",
                    "examples": ["Solicito la devolución del cobro duplicado"],
                },
                "false": {
                    "what": "There is no explicit request for refund, return, exchange, or replacement.",
                    "not_for": "Asking what the options are is not a request yet.",
                    "examples": ["¿Qué opciones tengo?"],
                },
            },
        ),
        "actionability": Choice(
            instructions={
                "question": "How actionable are `ticket.subject` and `ticket.body`?",
                "focus": "Decide whether the task and its object are present.",
                "decide": "Use `not_for` when two levels look close.",
            },
            criteria={
                "no_action": {
                    "what": "Only a feeling, thanks, or empty text. There is no task.",
                    "not_for": "A short but complete request is standard_action.",
                    "examples": ["Gracias, todo estuvo bien"],
                },
                "clarification": {
                    "what": "There is a task but the object is missing: which order, item, or account, or which concrete step.",
                    "not_for": "A self-contained quote, compatibility, or refund-status request is standard_action.",
                    "examples": ["Ayúdenme con mi pedido"],
                },
                "standard_action": {
                    "what": "The task and its object are identifiable, even in one short paragraph.",
                    "not_for": "Missing which order, item, or account is clarification. Fraud or an outage is immediate_action.",
                    "examples": ["Pido una cotización para una compra nueva", "¿Es compatible esta configuración?", "¿Cuál es el siguiente paso del reembolso ya aceptado?"],
                },
                "immediate_action": {
                    "what": "An immediate action with risk or impact that cannot wait.",
                    "not_for": "A routine billing mismatch without fraud is standard_action.",
                    "examples": ["Detecté un acceso no autorizado y necesito revisión hoy"],
                },
            },
        ),
        "technical_repro": Noul(
            instructions={
                "question": "If there is a technical problem, do `ticket.subject` and `ticket.body` include steps, a trigger, an error message, or evidence to reproduce it?",
                "focus": "Steps, a trigger, an error message, or concrete technical evidence. A bare 'it does not work' has none of these.",
            },
            criteria={
                "true": {
                    "what": "It describes steps, a trigger, an error message, or concrete technical evidence.",
                    "examples": ["Al exportar aparece error 500 después del paso 3"],
                },
                "false": {
                    "what": "There is no technical problem, or it lacks steps, an error message, or reproducible evidence.",
                    "not_for": "A detailed non-technical complaint is false here, not true.",
                    "examples": ["La app no funciona"],
                },
            },
        ),
    }


if len(RETAIL_QUESTION_IDS) != 3 or len(set(RETAIL_QUESTION_IDS)) != 3:
    raise RuntimeError("El contrato retail debe tener exactamente tres preguntas")
if len(TICKET_QUESTION_IDS) != 10 or len(set(TICKET_QUESTION_IDS)) != 10:
    raise RuntimeError("El contrato tickets debe tener exactamente diez preguntas")
