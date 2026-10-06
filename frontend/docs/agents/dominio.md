# Dominio: glosario y decisiones

## Glosario

El vocabulario vive en `CONTEXT.md`, en la raíz. Es un glosario: cada entrada define
un término. No guarda especificaciones ni decisiones de implementación. Los
requisitos del reto y las referencias a los PDF viven en `docs/reto.md`.

Usa este vocabulario al nombrar variables, funciones, archivos y pruebas. Si hace
falta un término nuevo, defínelo; si se descarta un sinónimo, regístralo junto al término.

## Decisiones de arquitectura

Las decisiones difíciles de revertir se registran en `docs/adr/`, numeradas
como `0001-titulo-corto.md`. Registra una decisión cuando se cumplan las tres condiciones:

1. Cambiarla después tiene un costo significativo.
2. Sorprendería a quien lea el código sin conocer su contexto.
3. Hubo alternativas reales y razones concretas para elegir.

Las decisiones rutinarias van en la descripción del cambio o commit.

```markdown
# NNNN — Título

**Estado:** aceptada | reemplazada por NNNN

## Contexto
Hechos que obligaron a decidir.

## Decisión
Qué se decidió.

## Alternativas consideradas
Opciones y razones para descartarlas.

## Consecuencias
Beneficios, costos y restricciones.
```

Si cambia una decisión, escribe una nueva y marca la anterior como reemplazada.
No reescribas la historia.
