"""Display vocabulary, not business validation or a mapping to model labels.

Unknown strings never leave DuckDB. Extending this vocabulary requires code review.
"""

CARD_TYPES = ("Tarjeta Crédito", "Tarjeta Débito")
PRODUCT_TYPES = (
    "Cuenta Ahorro",
    "Cuenta Corriente",
    *CARD_TYPES,
    "Préstamo Personal",
    "Préstamo Hipotecario",
    "Inversión",
    "Seguro",
)
BOOL = ("true", "false")
REASONS = ("Transaccional", "Producto", "Queja", "Técnico", "Comercial", "Retención")
DISTRIBUTIONS = {
    "products": {
        "product_type": PRODUCT_TYPES,
        "product_status": ("Active", "Closed", "Blocked", "Suspended"),
    },
    "transactions": {
        "transaction_type": (
            "Purchase",
            "Withdrawal",
            "Transfer",
            "Payment",
            "Deposit",
            "Adjustment",
        ),
        "transaction_status": ("Approved", "Declined", "Pending", "Reversed"),
        "currency": ("USD", "MXN", "COP", "ARS"),
        "is_fraud": BOOL,
    },
    "call_center_interactions": {
        "contact_reason": REASONS,
        "was_resolved": BOOL,
        "was_escalated": BOOL,
        "requires_followup": BOOL,
    },
    "call_transcripts": {"detected_language": ("es", "pt")},
    "complaints": {
        "category": ("Transactions", "Fees", "Technical", "Branch", "Service"),
        "subcategory": (
            "Cargo no reconocido",
            "Cobro indebido",
            "Problema con app",
            "Atención en sucursal",
            "Calidad de servicio",
        ),
        "status": ("In Process", "Open", "Resolved", "Escalated", "Closed", "Rejected"),
    },
    "satisfaction_surveys": {"survey_type": ("CSAT", "NPS", "CES")},
}
EVENTS = {
    "transactions": "transaction_date",
    "call_center_interactions": "interaction_date",
    "complaints": "creation_date",
    "satisfaction_surveys": "survey_date",
}
LEAKAGE_CANDIDATES = {
    "products": [
        "current_balance",
        "product_status",
        "credit_limit",
        "days_past_due",
        "last_transaction_date",
        "last_updated",
    ],
    "transactions": ["transaction_status", "response_code", "is_fraud", "fraud_score"],
    "call_center_interactions": [
        "was_resolved",
        "was_escalated",
        "requires_followup",
        "duration_seconds",
        "detected_sentiment",
        "sentiment_score",
    ],
    "call_transcripts": [
        "full_text",
        "agent_text",
        "customer_text",
        "main_topics",
        "detected_intents",
        "detected_keywords",
        "mentioned_entities",
    ],
    "complaints": [
        "status",
        "resolution_date",
        "closing_date",
        "resolution_days",
        "resolution",
        "compensation_granted",
        "resolution_satisfaction",
        "sla_breached",
    ],
    "satisfaction_surveys": ["main_score", "nps_category", "open_comments", "comment_sentiment"],
}
