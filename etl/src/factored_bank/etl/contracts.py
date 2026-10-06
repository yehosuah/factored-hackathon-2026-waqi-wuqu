"""Approved publication rules, separate from lossless Extract validation."""

import json
from importlib.resources import files

CONTRACT = json.loads(files(__package__).joinpath("contract.json").read_text())
VERSION = CONTRACT["version"]
TABLES = CONTRACT["tables"]
# Parent tables precede children, so quarantines propagate through required references.
ORDER = (
    "branches",
    "customers",
    "products",
    "service_agents",
    "transactions",
    "call_center_interactions",
    "call_transcripts",
    "complaints",
    "satisfaction_surveys",
)
# Tuple: child field, parent table, parent field, advisory-only approved exception.
REFERENCES = {
    "customers": [("registration_branch_id", "branches", "branch_id", True)],
    "products": [
        ("customer_id", "customers", "customer_id", False),
        ("opening_branch_id", "branches", "branch_id", False),
    ],
    "service_agents": [("assigned_branch_id", "branches", "branch_id", True)],
    "transactions": [
        ("customer_id", "customers", "customer_id", False),
        ("product_id", "products", "product_id", False),
        ("branch_id", "branches", "branch_id", False),
    ],
    "call_center_interactions": [
        ("customer_id", "customers", "customer_id", False),
        ("agent_id", "service_agents", "agent_id", False),
    ],
    "call_transcripts": [
        ("interaction_id", "call_center_interactions", "interaction_id", False),
        ("customer_id", "customers", "customer_id", False),
        ("agent_id", "service_agents", "agent_id", False),
    ],
    "complaints": [
        ("customer_id", "customers", "customer_id", False),
        ("affected_product_id", "products", "product_id", False),
        ("related_branch_id", "branches", "branch_id", False),
        ("origin_interaction_id", "call_center_interactions", "interaction_id", False),
        ("assigned_agent_id", "service_agents", "agent_id", False),
    ],
    "satisfaction_surveys": [
        ("interaction_id", "call_center_interactions", "interaction_id", False),
        ("customer_id", "customers", "customer_id", False),
        ("agent_id", "service_agents", "agent_id", False),
    ],
}


def identifier(name: str) -> str:
    """Quote only identifiers declared in the packaged contract or fixed implementation."""
    if not name.replace("_", "").isalnum():
        raise ValueError("invalid_identifier")
    return '"' + name + '"'
