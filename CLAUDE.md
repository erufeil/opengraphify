# Open Graphify



## Referencia de Archivos de Contexto

Este proyecto utiliza un sistema de documentación modular para mantener el contexto del desarrollo:

1. **`CLAUDE.md`** - (Este archivo) Documento principal de diseño por IA
2. **`CLAUDE-library.md`** - Diccionario completo de endpoints, variables, formatos y estructuras
3. **`CLAUDE-code.md`** - Arquitectura detallada, algoritmos y estructuras de código
4. **`CLAUDE-memory.md`** - Historial de cambios, problemas resueltos y decisiones técnicas
5. **`CLAUDE-rta1.md`** - Respuestas del usuario a preguntas de diseño (v1)
6. **`CLAUDE-plan.md`** - Planificación de desarrollo y próximos pasos a seguir, en términos de Etapa 1, 2, 3, ...

Cada vez que termines una intervención debes actualizar los documentos para que reflejen los últimos cambios, y crear un archivo `CLAUDE-rta<N>.md` con todo lo realizado en esa intervención.

Metodo de Instalacion solo con:
Commit y
install.bat

Metodo de actualizacion solo con:
commit y
actualiza-librerias.bat

Plan Features:

### mejora 1: vista Obsidian

Si además quieres ver los nodos individuales con su nombre (no agrupados), eso es la vista Obsidian/full-node de graphify (--obsidian)

### mejora 2: Guarda por Chunk y menos contexto

Guardar el caché por chunk (en runner.py, dentro de on_chunk_done) para que un crash sea recuperable y el trabajo se reanude desde donde quedó.", actualiza por defecto uso de: model = "qwen2.5-coder:3b" ; # PowerShell (sesión actual)
$env:OPENGRAPHIFY_TOKEN_BUDGET = "4000"     # input por chunk más chico
$env:GRAPHIFY_MAX_OUTPUT_TOKENS = "2048"    # menos reserva de salida → num_ctx ~8k. Los threads estaban bien al 50% pero si el ventilador funcionaba 10hr seguidas, yo agregaria que procese una cantidad de archivos asi cuando un repositorio es grande que le pueda poner "--max 50" y procesa 50 archivos y asi voy regulando