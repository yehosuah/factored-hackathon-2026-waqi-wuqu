# Gestor de issues: archivos locales

Los issues de este repositorio son archivos Markdown bajo `.scratch/`. No hay gestor externo.

## Dónde van

`.scratch/<nombre-del-trabajo>/issues/<NN>-<slug>.md`

`NN` empieza en `01` y numera en orden de dependencia: lo que bloquea va primero.

## Formato

```markdown
# <NN>: <título>

**Qué se construye:** comportamiento de punta a punta desde la perspectiva de quien lo usa.

**Bloqueado por:** números o títulos previos, o "Nada (se puede empezar ya)".

**Estado:** listo-para-agente

- [ ] Criterio de aceptación verificable
```

Un issue está disponible cuando todos sus bloqueos están cerrados.
Para cerrarlo, marca los criterios y cambia el estado a `cerrado`. No borres el archivo:
es el registro del trabajo. Usa `en-progreso` o `bloqueado` cuando corresponda y explica el bloqueo.

No hay asignación automática ni vista de dependencias. Si trabajan varias personas,
coordinen quién toma cada archivo. Para cambiar de gestor, vuelve a ejecutar `configurar-desarrollo`.
