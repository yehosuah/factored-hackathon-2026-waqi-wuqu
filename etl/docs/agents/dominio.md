# Dominio: glosario y decisiones

## Glosario

El vocabulario del dominio vive en `CONTEXT.md`, en la raíz. Es un glosario:
no es una especificación, un cuaderno de notas ni un registro de implementación.
Usa ese vocabulario para nombrar conceptos en código y pruebas; agrega definiciones cuando falten.
Los requisitos y fuentes del reto viven en `docs/hackathon-brief.md`.

## Decisiones de arquitectura

Se registran en `docs/adr/`, numeradas como `0001-titulo-corto.md`, solo cuando:

1. Son costosas de revertir.
2. Sorprenderían a quien no conoce el contexto.
3. Hubo alternativas reales.

Si falta alguna condición, documenta la decisión en el cambio correspondiente.

```markdown
# NNNN - <título>

**Estado:** aceptada | reemplazada por NNNN

## Contexto
Hechos que obligaron a decidir.

## Decisión
Qué se decidió.

## Alternativas consideradas
Alternativas y razones para descartarlas.

## Consecuencias
Qué se facilita y qué se dificulta.
```

Cuando cambia una decisión, escribe otra y marca la anterior como reemplazada.
El registro conserva su historia.
