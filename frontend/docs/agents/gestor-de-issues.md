# Gestor de issues: archivos locales

Los issues de este repositorio son archivos Markdown bajo `.scratch/`.
El remoto está en GitHub, pero al configurar el proyecto no había issues abiertos
ni cerrados. Por ahora se usa el gestor local.

## Dónde van

```text
.scratch/<nombre-del-trabajo>/issues/<NN>-<slug>.md
```

`NN` empieza en `01` y numera en orden de dependencia: lo que bloquea va primero.

## Formato

```markdown
# <NN>: <título>

**Qué se construye:** comportamiento de punta a punta desde la perspectiva del usuario.

**Bloqueado por:** números o títulos de los issues previos, o "Nada (se puede empezar ya)".

**Estado:** listo-para-agente

- [ ] Criterio de aceptación verificable
```

## Cómo se trabaja

Un issue está disponible cuando todo lo que lo bloquea está cerrado. Al empezarlo,
marca `en-curso`; al terminar, verifica sus criterios, márcalos y cambia el estado
a `cerrado`. No borres el archivo: conserva el registro del trabajo.

Los tickets se versionan; no guardes credenciales, datos restringidos ni archivos
temporales en `.scratch/`. No hay asignación automática ni vista de dependencias.
Si el equipo necesita esas funciones, vuelve a ejecutar `configurar-desarrollo`
para cambiar de gestor.
