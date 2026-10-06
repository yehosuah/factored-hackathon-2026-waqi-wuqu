"""Comprueba el entorno con una fixture temporal, sin datos del organizador."""

import json
import platform
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import polars as pl
from pydantic import BaseModel, ConfigDict, ValidationError


class FixtureRow(BaseModel):
    """Contrato mínimo de prueba; no representa el esquema bancario completo."""

    model_config = ConfigDict(strict=True, extra="forbid")

    fixture_id: str
    amount: Decimal


def verify() -> dict[str, object]:
    """Verifica contratos, Parquet y SQL usando importes decimales exactos."""
    rows = [
        FixtureRow(fixture_id="setup-001", amount=Decimal("10.25")),
        FixtureRow(fixture_id="setup-002", amount=Decimal("20.50")),
    ]
    try:
        FixtureRow.model_validate({"fixture_id": "invalid", "amount": "not-a-number"})
    except ValidationError:
        pass
    else:
        raise RuntimeError("El contrato aceptó un importe inválido")

    with TemporaryDirectory(prefix="factored-setup-") as directory:
        path = Path(directory) / "fixture.parquet"
        frame = pl.DataFrame(
            [row.model_dump() for row in rows],
            schema={"fixture_id": pl.String, "amount": pl.Decimal(precision=15, scale=2)},
        )
        frame.write_parquet(path)
        restored = pl.scan_parquet(path).collect()
        if restored.to_dicts() != frame.to_dicts():
            raise RuntimeError("Parquet no conservó los valores de la fixture")

        with duckdb.connect(":memory:") as connection:
            result = connection.execute(
                "SELECT count(*), sum(amount) FROM read_parquet(?)", [str(path)]
            ).fetchone()
        if result != (2, Decimal("30.75")):
            raise RuntimeError(f"Resultado SQL inesperado: {result!r}")

    return {
        "status": "ok",
        "python": platform.python_version(),
        "packages": {name: version(name) for name in ("duckdb", "polars", "pydantic")},
        "checks": ["strict_contract", "invalid_input_rejected", "parquet_roundtrip", "sql_sum"],
        "data_source": "team_generated_setup_fixture",
        "organizer_dataset_validated": False,
    }


def main() -> None:
    print(json.dumps(verify(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
