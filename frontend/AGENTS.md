# Instrucciones de desarrollo

Este repositorio contiene el frontend de FactoredAI_FRT. Usa React, TypeScript y Vite.
Lee `README.md` para instalar y verificar el ambiente, y `docs/reto.md` para conocer
los requisitos y límites extraídos de `GeneralInfo/`.

## Forma de trabajo

- Para trabajo sustancial, usa `achiever-mode` y `toolkit:afinar`; si falta contexto,
  usa `plan-de-sesion`. Mantén triviales las tareas triviales.
- Confirma las decisiones de producto abiertas antes de implementarlas.
- Valida cambios de código con `npm run check` y comprueba en navegador los cambios visibles.
- Usa los nombres del glosario. Mantén los textos de interfaz separados de la lógica.
- Identifica claramente los datos y acciones simulados. Una interfaz no prueba que
  una operación bancaria se haya ejecutado.
- Las claves privadas, credenciales de modelos y registros de clientes no van en
  el navegador, `public/`, variables `VITE_*` ni Git.
- El backend debe aplicar identidad, permisos, aislamiento por cliente y políticas.
  Los controles visuales del frontend no sustituyen esas verificaciones.

## Skills de desarrollo

### Gestor de issues

Issues locales en `.scratch/`. Ver `docs/agents/gestor-de-issues.md`.

### Dominio

Contexto único en `CONTEXT.md`; decisiones en `docs/adr/`. Ver `docs/agents/dominio.md`.
