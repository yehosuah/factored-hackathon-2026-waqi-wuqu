# 0002 - Referencias de sucursal no resueltas

**Estado:** aceptada, acordada con el usuario el 2026-10-01.

## Contexto

El perfil completo encontró referencias de sucursal ausentes en 149,995 de 150,000
clientes y en 831 agentes de servicio. Rechazar esas relaciones como claves foráneas
estrictas descartaría casi todos los clientes y sus registros dependientes.

## Decisión

Conservar `registration_branch_id` y `assigned_branch_id` con indicadores explícitos
de relación no resuelta. No fabricar equivalencias ni habilitar afirmaciones que
dependan de esas relaciones. Las demás relaciones de identidad y propiedad siguen
estrictas y se propagan a cuarentena cuando fallan.

## Alternativas consideradas

Rechazar toda referencia ausente impediría el consumo del núcleo del dataset.
Inventar un mapeo o convertir silenciosamente los IDs a null perdería evidencia.

## Consecuencias

La entrega mantiene cobertura de clientes y evidencia del defecto. Las métricas o
funciones por sucursal requieren otra fuente o un contrato revisado. De los agentes
aceptados, 811 conservan este indicador; otros agentes fueron rechazados por reglas
distintas.
