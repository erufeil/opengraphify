<div align="center">

# 🕸️ OpenGraphify

**El worker silencioso de [graphify](https://github.com/safishamsi/graphify).**

Mantiene tu grafo de conocimiento actualizado en segundo plano usando un modelo
**local o barato** (Ollama, OpenRouter, DeepSeek…), para que el modelo de Claude Code
nunca gaste tokens caros procesando el grafo.

`SKILL: graphify` → `WORKER: opengraphify`

![license](https://img.shields.io/badge/license-MIT-green)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![backend](https://img.shields.io/badge/backend-Ollama%20%7C%20OpenRouter-orange)

</div>

---

## 💡 La idea en una línea

graphify construye un grafo de conocimiento de tu repo. Para los archivos **no-código**
(docs, papers, imágenes) necesita un LLM, y por defecto ese LLM es el modelo de Claude Code
→ **tokens caros**.

**OpenGraphify es una capa de ahorro**: corre exactamente el mismo pipeline pero apuntando
ese trabajo a un modelo **local (gratis) o barato** → **tokens baratos**. Cuando graphify
revisa el grafo, ve que ya está al día y **no procesa nada**. El modelo principal queda libre.

```text
                       ┌─────────────── tokens CAROS ────────────────┐
                       | graphify (skill)  →  modelo de Claude Code  |
                       |                          procesa el grafo   |
                       └─────────────────────────────────────────────┘

                       ┌─────────────── tokens BARATOS ──────────────┐
                       | opengraphify (worker) → Ollama / OpenRouter |
                       |                            procesa el grafo |
                       | graphify ve el grafo al día → no hace nada  |
                       └─────────────────────────────────────────────┘
```

---

## 🙏 Créditos — esto es graphify

> **Todo el motor de extracción, construcción, clustering y análisis del grafo es de
> [graphify](https://github.com/safishamsi/graphify), creado por [@safishamsi](https://github.com/safishamsi).**

OpenGraphify **no reimplementa** nada de eso: importa graphify como librería y reutiliza su
pipeline tal cual. Lo único que aporta es la **orquestación** para correrlo de forma autónoma
contra un backend económico, compartiendo el mismo `manifest.json`.

Si este proyecto te sirve, andá a **[github.com/safishamsi/graphify](https://github.com/safishamsi/graphify)**
y dejale una ⭐ — el mérito del trabajo pesado es suyo.

---

## 🧠 ¿Cómo funciona? (y por qué ahorra tanto)

El pipeline tiene dos tipos de extracción muy distintos:

| Etapa | Qué procesa | Usa IA | Costo |
| --- | --- | --- | --- |
| **AST** | Todo el **código** | ❌ No | Gratis, instantáneo |
| **Semántica** | Solo **docs, papers, imágenes** | ✅ Sí | Acá entra el modelo barato |

- **El código se grafica 100% sin IA.** Un parser de AST extrae funciones, clases, llamadas,
  imports y herencia de forma determinística. En un repo de 1000+ archivos, esto produce
  decenas de miles de nodos/edges en segundos, sin una sola llamada a un modelo.
- **La IA solo toca lo no estructurado.** Un doc en prosa, un PDF o un PNG no tienen árbol
  sintáctico; ahí el modelo traduce ese material a nodos/edges que se integran al **mismo grafo**.
  Después el clustering encuentra las conexiones cruzadas (ej: el doc de diseño ↔ el código que lo implementa).

> 🔌 **Corolario:** en un repo de **puro código** (sin docs/papers/imágenes), opengraphify
> arma el grafo completo **sin una sola llamada al modelo** — ni necesitás Ollama instalado.

### 🖼️ Imágenes y visión (importante)

Un modelo de **texto** (qwen2.5-coder, mistral, etc.) **no puede ver imágenes**. Por eso, con
el backend por defecto, opengraphify **ni siquiera manda los píxeles**: cada imagen raster
(`.jpg/.png/.webp/.gif`) se convierte en un **nodo** del grafo, pero su descripción es un
**texto adivinado a partir del nombre del archivo**, no una lectura real del contenido.

- **SVG es la excepción:** como es XML (texto), se lee como código y el modelo **sí** lo
  interpreta de verdad.
- **¿Querés descripciones reales en local?** Usá un **modelo de visión** en Ollama y prendé el
  candado: `ollama pull llama3.2-vision`, correr con `--model llama3.2-vision` y la variable
  `GRAPHIFY_OLLAMA_VISION=1`. (Pesa más; en una GPU con ~12 GB+ entra bien.)
- **Con Claude** (backend con visión) sí se mandan los píxeles y devuelve una descripción real.
- **¿No aportan?** Si son screenshots/fotos sin valor para el grafo, conviene **excluirlas** del
  scan: cuestan VRAM y tiempo para nodos-placeholder.

---

## 🏗️ Arquitectura

```text
%USERPROFILE%\.opengraphify\
├── graphify\          ← graphify instalado UNA vez (pip -e) · se actualiza con el .bat
└── opengraphify\      ← este worker, instalado UNA vez (pip -e)

C:\cualquier-repo\
├── opengraphify.toml  ← config opcional por repo (backend, modelo, intervalo)
└── graphify-out\      ← grafo generado (ignorar en git)
    ├── graph.json         ← el grafo
    ├── graph.html         ← visualización interactiva
    ├── GRAPH_REPORT.md    ← informe: comunidades, hubs, conexiones sorpresivas
    ├── manifest.json      ← estado compartido con graphify (clave del ahorro)
    └── cache\             ← caché semántico por archivo
```

Ambos quedan registrados como paquetes pip globales: `opengraphify .` funciona desde
**cualquier directorio** de tu PC, sin copiar nada.

---

## 🚀 Instalación (primera vez)

Solo necesitás el archivo **`install.bat`** — no hace falta clonar nada a mano, el script
descarga todo solo.

```bat
install.bat
```

Hace, de punta a punta:

1. Clona e instala **graphify** en `%USERPROFILE%\.opengraphify\graphify\`
2. Clona e instala **opengraphify** en `%USERPROFILE%\.opengraphify\opengraphify\`
3. Agrega los directorios `Scripts` de Python al `PATH` del usuario
4. Verifica que el comando `opengraphify` quede disponible

### Requisitos previos

| Requisito | Dónde |
| --- | --- |
| Python 3.10+ | [python.org](https://www.python.org/downloads/) — marcar *Add Python to PATH* |
| Git | [git-scm.com](https://git-scm.com/download/win) — marcar *Add Git to PATH* |
| Ollama (backend por defecto) | [ollama.com](https://ollama.com) + `ollama pull qwen2.5-coder:3b` |

> **Ollama no necesita modo server.** En Windows corre como servicio de fondo automáticamente
> al instalarlo (queda escuchando en `http://localhost:11434`). No hace falta `ollama serve`.
>
> 🎮 **¿Notebook sin GPU NVIDIA (iGPU Intel/AMD)?** El Ollama oficial corre en **CPU** y en
> repos grandes recalienta. Para acelerar con una **iGPU Intel Arc** (vía IPEX-LLM) y poder
> usar el 7B sin freír la CPU, mirá **[README-GPU.md](README-GPU.md)**.

---

## 🎯 Activar en un repo

Una sola vez, parado en la carpeta del repo:

```bash
graphify install --project    # conecta graphify: escribe CLAUDE.md + hook PreToolUse
opengraphify . --force         # construye el grafo inicial (sin tokens de Claude)
opengraphify . --watch         # lo mantiene actualizado en background
```

---

## 🕹️ Uso

```bash
opengraphify .                    # una corrida incremental (default)
opengraphify . --max 50           # procesa 50 archivos nuevos y termina
opengraphify . --force            # re-extracción completa (ignora caché)
opengraphify . --code-only        # solo código (AST), sin LLM/Ollama — rápido y offline
opengraphify . --code-only-1      # igual, pero nombra los clusters con el LLM al final
opengraphify . --status           # estado del grafo: nodos, edges, cambios pendientes
opengraphify . --watch            # modo daemon, cada 15 min (según config)
opengraphify . --watch --interval 5
opengraphify . --watch --code-only # mantiene el grafo de código fresco sin tokens ni calor

# Overrides inline sin tocar el toml
opengraphify . --model llama3.1:8b
opengraphify . --base-url https://openrouter.ai/api/v1 --model mistralai/mistral-7b-instruct
opengraphify . --max 5 --model qwen2.5-coder:7b
```

### Procesar repos grandes por tandas con `--max`

Para un repo grande, en vez de una maratón de horas que puede recalentar la máquina,
procesás de a **N archivos** y vas regulando. Cada corrida **cachea su progreso** (caché
por chunk), así la siguiente arranca donde quedó — incluso si la anterior se cortó:

```bash
opengraphify ./mi-repo --max 50    # procesa 50 archivos nuevos y termina
opengraphify ./mi-repo --max 50    # los próximos 50, etc.
```

> `--max` limita solo los archivos **semánticos sin cachear** (la parte lenta con LLM);
> los ya cacheados no cuentan contra el límite.

Durante la extracción semántica vas a ver el avance **archivo por archivo**:

```text
[opengraphify] semantic extraction on 56 files via ollama (qwen2.5-coder:3b), token_budget=4,000...
[opengraphify] semantic extraction on README.md (1/56)
[opengraphify] semantic extraction on ARCHITECTURE.md (2/56)
...
```

> Los archivos se procesan en *chunks* paralelos, así que las líneas aparecen en ráfagas
> (varios archivos de golpe cada vez que un chunk del modelo responde). El caché se guarda
> **después de cada chunk**, así que un corte (o un apagón térmico) es recuperable.

> 🐘 **Árboles enormes (decenas de miles de archivos, ej. el kernel de Linux):** el *primer*
> escaneo camina todo el árbol y puede tardar varios minutos (a partir de ahí las corridas
> incrementales son rápidas). Para que no parezca colgado, opengraphify muestra un latido con el
> conteo en vivo: `scanning files... 12,340 files scanned (24s)`. Consejo: en vez de grafear un
> repo gigante entero, apuntá a un **subdirectorio/subsistema** (`opengraphify ./fs/ext4 --code-only`).

### ⚡ Modo solo-código (`--code-only`)

Salta **por completo** la etapa semántica: **cero llamadas al LLM/Ollama**. Solo corre la
extracción AST del **código** (funciones, clases, llamadas, imports) + clustering + export.
Es rápido, offline, y no calienta la máquina.

```bash
opengraphify . --code-only            # una pasada, solo código (100% offline)
opengraphify . --code-only-1          # igual, pero nombra los clusters con el LLM al final
opengraphify . --watch --code-only    # mantiene el grafo de código fresco en background
```

- **No pierde tu trabajo semántico.** La detección de cambios y el manifest usan el hash de
  código (`kind="ast"`), que **preserva** el `semantic_hash` de los docs ya extraídos. Así, una
  pasada solo-código **nunca olvida** lo semántico ni fuerza una re-extracción después.
- **`--code-only`** no etiqueta comunidades con IA (reusa las etiquetas existentes si las hay, si
  no, `Community N`). **`--code-only-1`** hace lo mismo pero **sí** corre el paso final de
  etiquetado por LLM (~1 llamada cada 100 comunidades) para que los clusters tengan nombres reales
  — "solo-código *menos 1*". El resto (extracción del código) sigue siendo offline en ambos.
- **Ideal con `--watch`:** mantené el grafo del código al día de forma continua sin gastar tokens
  ni recalentar; cuando quieras, corré una pasada normal (`opengraphify .`) para completar la
  parte semántica de los docs/imágenes que cambiaron.

> En un repo de **puro código** el resultado es idéntico a una corrida normal (esa nunca llama al
> modelo igual). `--code-only` brilla cuando el repo **también** tiene docs/imágenes pero querés
> refrescar solo el código, barato y al instante.

### Como servicio en background (Windows)

```powershell
Start-Process opengraphify -ArgumentList ". --watch" -WindowStyle Hidden
```

O con el **Programador de tareas**: programa `opengraphify`, argumentos `C:\ruta\al\repo --watch`,
disparador "al iniciar sesión".

---

## ⚙️ Configuración

> ⚠️ **Dónde tiene que estar el `opengraphify.toml`** (causa típica de "no lee mi
> config"). Se busca, **en este orden**, y gana el primero que exista:
>
> 1. `<repo-que-escaneás>/opengraphify.toml` — el repo pasado como argumento
> 2. `<directorio-actual>/opengraphify.toml` — tu *cwd* al ejecutar
> 3. `%USERPROFILE%\.opengraphify\opengraphify.toml` — **config global** (aplica siempre)
>
> Editar el `opengraphify.toml` del repo *instalado* (`~/.opengraphify\opengraphify\`)
> **no** sirve: no está en esa lista. Para una config que valga en todos lados, usá la
> **global** `%USERPROFILE%\.opengraphify\opengraphify.toml`. Cada corrida imprime qué archivo
> cargó (`[opengraphify] config: ...`) para que veas exactamente cuál está en efecto.
> También podés forzar uno con `--config RUTA\al\opengraphify.toml`.

Poné un `opengraphify.toml` en la raíz del repo (o usá la config global). Si no hay ninguno,
usa los defaults (Ollama + `qwen2.5-coder:3b`, cada 15 min).

```toml
[backend]
provider = "ollama"                    # proveedor
model    = "qwen2.5-coder:3b"          # modelo (3b: liviano para CPU/iGPU; subí a 7b con GPU)
base_url = "http://localhost:11434/v1" # endpoint (Ollama por defecto)
api_key  = ""                          # vacío para Ollama local

[schedule]
interval_minutes = 15

[output]
out_dir         = "graphify-out"   # debe coincidir con el out_dir de graphify
generate_html   = true
generate_report = true

[extraction]
# Tuning para modelos locales chicos (más chico = más liviano/rápido por chunk).
token_budget       = 4000   # tokens de entrada empacados por chunk
max_output_tokens  = 2048   # tope de salida por chunk (se exporta como GRAPHIFY_MAX_OUTPUT_TOKENS)
force_json         = true   # fuerza salida JSON (modelos chicos si no responden en prosa)
max_retry_depth    = 1      # reintentos por bisección en chunks vacíos/fallidos (0 = ninguno)
# Resiliencia de red (ver "Errores, cuelgues y recuperación" más abajo)
api_timeout        = 180    # tope (seg) por request; corta un cuelgue de red (graphify default: 600 = 10 min)
chunk_retries      = 2      # reintentos in-run ante errores transitorios (524/429/5xx); 0 = ninguno
retry_wait_seconds = 30     # espera entre reintentos si el server no manda Retry-After (el 524 sí lo manda)
ollama_parallel    = 1      # requests simultáneos a la LLM (1 = serial, default). Ver "⚡ Paralelismo" abajo
```

### Usar OpenRouter en lugar de Ollama

```toml
[backend]
provider = "openrouter"
model    = "mistralai/mistral-7b-instruct"
base_url = "https://openrouter.ai/api/v1"
api_key  = "sk-or-..."
# Elige el proveedor de OpenRouter más rápido para este modelo en vez del más
# barato (por defecto OpenRouter balancea por precio). Sube el costo por
# token; no hace nada contra un Ollama local literal. Ver "⚡ Paralelismo" abajo
# para la diferencia entre esto y correr requests en simultáneo.
nitro    = false
```

### Variables de entorno (override sin tocar el toml)

| Variable | Descripción |
| --- | --- |
| `OPENGRAPHIFY_PROVIDER` | Nombre del proveedor |
| `OPENGRAPHIFY_MODEL` | Modelo a usar |
| `OPENGRAPHIFY_BASE_URL` | URL base del endpoint |
| `OPENGRAPHIFY_API_KEY` | API key |
| `OPENGRAPHIFY_INTERVAL` | Intervalo en minutos para `--watch` |
| `OPENGRAPHIFY_TOKEN_BUDGET` | Tokens de entrada por chunk (default 4000) |
| `GRAPHIFY_MAX_OUTPUT_TOKENS` | Tope de salida por chunk (default 2048) |
| `OPENGRAPHIFY_API_TIMEOUT` | Tope en segundos por request al backend (default 180) |
| `OPENGRAPHIFY_CHUNK_RETRIES` | Reintentos in-run ante errores 524/429/5xx (default 2) |
| `OPENGRAPHIFY_RETRY_WAIT` | Espera de reintento si no hay Retry-After (default 30s) |
| `GRAPHIFY_OLLAMA_VISION` | `1` para mandar píxeles a un modelo de visión de Ollama (default: off) |
| `OPENGRAPHIFY_DEBUG_HANG` | Si algo se cuelga: volca el stack cada N seg para diagnóstico |
| `OPENGRAPHIFY_NO_FAST_EXIT` | `1` para volver al cierre normal del intérprete (escape hatch) |
| `OPENGRAPHIFY_NITRO` | `1` para priorizar velocidad sobre costo en OpenRouter (`provider.sort=throughput`) |
| `OPENGRAPHIFY_OLLAMA_PARALLEL` | Cuántos requests simultáneos a la LLM (default 1 = serial). Ver "⚡ Paralelismo" |

---

## 🔗 Integración con graphify

opengraphify escribe en el **mismo `out_dir`** que graphify y actualiza el mismo
`manifest.json`. Cuando graphify intenta actualizar el grafo, detecta que los hashes ya están
al día y **no vuelve a procesar nada** → el modelo de Claude Code queda libre.

Agregá al `.gitignore` del repo de trabajo:

```text
graphify-out/
```

---

## 🔄 Actualizar las librerías

```bat
actualiza-librerias.bat
```

Re-clona graphify y opengraphify desde GitHub (última versión) y los reinstala.

> graphify se actualiza con frecuencia. Si opengraphify deja de funcionar o querés nuevas
> funciones, corré este `.bat`. No hace falta automatizarlo.

---

## 🤖 Modelos recomendados

| Caso | Modelo | Proveedor |
| --- | --- | --- |
| Default liviano (CPU / iGPU, sin internet) | `qwen2.5-coder:3b` | Ollama local |
| Mejor calidad (necesita GPU o CPU potente) | `qwen2.5-coder:7b` | Ollama local |
| Repos grandes con GPU dedicada | `codestral:22b` | Ollama local |
| Muy rápido y barato | `mistralai/mistral-7b-instruct` | OpenRouter |
| Alta calidad semántica | `deepseek/deepseek-coder-v2-lite-instruct` | OpenRouter |

> El default es el **3B** porque es seguro en CPU/iGPU. El **7B** entrega bastante mejor
> calidad de extracción; si tu hardware lo aguanta (idealmente GPU), subilo en el toml. Para
> correr el 7B acelerado por una **iGPU Intel Arc**, ver **[README-GPU.md](README-GPU.md)**.

---

## ⚡ Paralelismo: cuántos requests simultáneos aguanta tu setup

Hay **dos variables distintas** que suelen confundirse porque tienen nombres parecidos. Antes
de tocar cualquiera de las dos, conviene tener claro cuál controla qué:

| Variable | Quién la lee | Qué controla | Dónde se setea |
| --- | --- | --- | --- |
| `OLLAMA_NUM_PARALLEL` | El **servidor** Ollama (`ollama serve`) | Cuántos *slots* de generación reserva el server para un modelo cargado | Variable de entorno **del sistema donde corre el servicio Ollama** — requiere **reiniciar el servicio** para tomar efecto. `opengraphify.toml` no puede tocarla: no es su proceso. |
| `ollama_parallel` (toml) / `OPENGRAPHIFY_OLLAMA_PARALLEL` (env) | El **cliente** (opengraphify/graphify) | Cuántos requests HTTP dispara opengraphify **en simultáneo** hacia ese servidor | `opengraphify.toml`, sección `[extraction]` |

Ninguna de las dos alcanza sola: si el servidor permite 4 *slots* pero el cliente sigue
mandando de a uno (`ollama_parallel = 1`, el default), nunca vas a tener más de un request en
vuelo. Y si el cliente manda 4 a la vez pero el servidor solo tiene 1 *slot*, Ollama encola los
otros 3 — no hay error, pero tampoco hay ganancia real.

`ollama_parallel > 1` en el toml hace dos cosas automáticamente: exporta
`GRAPHIFY_OLLAMA_PARALLEL=1` (el gate que usa graphify internamente — por defecto fuerza serial
para el slot "ollama", justamente para no repetir el problema de abajo) y le pasa ese número
como techo de concurrencia real a extracción y labeling.

### El motivo del default serial

graphify fuerza `max_concurrency=1` para el backend "ollama" por una razón medida, no por
paranoia: un Ollama local sirve **un request a la vez por modelo cargado** salvo que
explícitamente le habilites *slots* paralelos, y mandarle varios sin ese permiso server-side
produce **presión de VRAM y respuestas huecas** (graphify issue #798). Por eso subir
`ollama_parallel` en el toml sin haber configurado `OLLAMA_NUM_PARALLEL` en el servidor no hace
nada malo, pero tampoco hace nada útil.

### Caso real: 3090 (24GB) sirviendo 3 modelos a la vez

Este es el análisis para un Ollama local que mantiene cargados simultáneamente
`qwen2.5-coder:7b` (extracción de opengraphify), `gemma3:4b` (otro uso) y `nomic-embed-text`
(embeddings para RAG) — el **peor caso**, todos residentes a la vez.

**Por qué importa la distinción cliente/servidor acá:** los pesos de cada modelo se cargan
**una sola vez** en VRAM sin importar cuántos requests en paralelo le mandes — lo único que
escala con la concurrencia es la **KV-cache** (la memoria de contexto activo) de cada request
en vuelo, más un margen chico de buffers de cómputo.

| Modelo | Peso en VRAM (Q4, tal cual lo baja Ollama) | KV-cache por token | KV-cache a ~14k de contexto (1 slot) |
| --- | --- | --- | --- |
| `qwen2.5-coder:7b` | ~6 GB | ~56 KB/token (28 capas, GQA 4 KV-heads, head_dim 128 — calculado del config real) | ~0,79 GB |
| `gemma3:4b` | ~3,3 GB | ~129 KB/token (**aproximado**, derivado de las cifras públicas de VRAM-vs-contexto de Gemma 3 4B, no de un cálculo capa-por-capa — Gemma 3 intercala 5:1 capas de atención local/global, así que el costo real por capa varía) | ~1,82 GB |
| `nomic-embed-text` | ~0,27 GB | Insignificante — es un encoder, un solo forward pass sin generación autoregresiva, no acumula KV-cache | ~0,05-0,1 GB fijo |

Con los tres cargados en reposo: `6 + 3,3 + 0,27 ≈ 9,6 GB` de 24GB, antes de sumar ningún slot
paralelo. Quedan **~14,4 GB libres** de entrada.

| `ollama_parallel` (qwen y gemma a la vez) | VRAM total estimada (peor caso, 3 modelos + N slots cada uno) | Margen sobre 24GB |
| --- | --- | --- |
| 1 (serial, default) | ~11,2 GB | ~12,8 GB — muy holgado |
| **2** | ~15,8 GB | ~8,2 GB — holgado |
| 3 | ~18,4 GB | ~5,6 GB — ajustado pero razonable |
| 4 | ~21,0 GB | ~3,0 GB — arriesgado sin medir antes |

**Conclusión para este caso:** con los 3 modelos residentes, `ollama_parallel = 2` (el default
que dejamos en el toml de este perfil) tiene margen de sobra — no hacía falta ser tan
conservador. `3` también entra cómodo. `4` ya empieza a comerse el colchón de golpe si además
el sistema operativo o Ollama reservan buffers extra — ahí sí conviene medir antes de confiar
en la cuenta de arriba.

> ⚠️ Estos números asumen que **ambos modelos generativos usan un contexto similar (~14k)**. Si
> `gemma3:4b` lo usás con un contexto mucho más chico (charla corta) o mucho más grande, su
> columna de KV-cache cambia proporcional al contexto real, no al de este ejemplo.
>
> 💡 En la práctica, Ollama **descarga modelos inactivos** después de `OLLAMA_KEEP_ALIVE`
> (5 min por defecto) — el "peor caso" de los 3 juntos solo se da si los estás usando a los
> tres dentro de esa ventana. Fuera de eso, la VRAM real usada suele ser bastante menor a la
> tabla de arriba.

### Configurar el lado servidor (Ollama)

En la máquina donde corre `ollama serve` (no en el `opengraphify.toml` — ese es el cliente):

```powershell
# Windows: variable de entorno de sistema (no de sesión), después reiniciar el servicio Ollama
[System.Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL", "4", "Machine")
# reiniciar el servicio Ollama (o el equipo) para que tome efecto
```

Variables relevantes del lado servidor:

| Variable | Qué hace |
| --- | --- |
| `OLLAMA_NUM_PARALLEL` | *Slots* de generación paralelos por modelo cargado (default 1). Sube la VRAM en `slots × contexto`. |
| `OLLAMA_MAX_LOADED_MODELS` | Cuántos modelos distintos pueden estar cargados a la vez (relevante si tenés varios como acá). |
| `OLLAMA_KEEP_ALIVE` | Cuánto tiempo queda cargado un modelo inactivo antes de descargarse (default 5m). Subirlo evita recargas frecuentes; bajarlo libera VRAM más rápido entre usos. |

### Configurar el lado cliente (opengraphify)

```toml
[extraction]
ollama_parallel = 2   # requests simultáneos que opengraphify le manda a este backend
```

Aplica tanto a la extracción semántica como al etiquetado de comunidades. Es independiente de
`nitro` (que solo tiene sentido con OpenRouter): `nitro` acelera **cada** request eligiendo el
proveedor más rápido; `ollama_parallel` reduce **cuántos** requests en serie hacen falta para
un lote. Para un backend con muchos requests independientes (que es exactamente el caso de
opengraphify: un request por chunk/lote), la concurrencia suele pesar más que la velocidad de
un request individual — y se combinan.

---

## 🛠️ Troubleshooting

<details>
<summary><b>El comando <code>opengraphify</code> no se reconoce</b></summary>

```text
opengraphify : El término 'opengraphify' no se reconoce como nombre de un cmdlet...
```

**Causa:** el directorio `Scripts` de Python recién se agrega al `PATH` al instalar, y las
terminales **ya abiertas** no lo ven.

**Solución:**
1. **Cerrá y abrí una terminal nueva** — casi siempre es esto.
2. Mientras tanto siempre funciona: `python -m opengraphify .`
3. Si en una terminal nueva sigue sin andar, verificá dónde quedó el `.exe`:
   ```powershell
   python -c "import sysconfig; print(sysconfig.get_path('scripts','nt_user'))"
   ```
   Ese directorio tiene que estar en tu `PATH` de usuario. `install.bat` lo agrega solo;
   si lo borraste, volvé a correr `install.bat`.

> Cuando Python está en `Program Files`, pip instala en modo *user* y pone el `.exe` en
> `…\AppData\Roaming\Python\Python3xx\Scripts`, **no** en el `Scripts` del sistema. Por eso
> `install.bat` agrega **ambos** directorios al `PATH`.
</details>

<details>
<summary><b>"does not appear to be a Python project: neither 'setup.py' nor 'pyproject.toml' found"</b></summary>

**Causa:** un **clon roto**. La carpeta en `%USERPROFILE%\.opengraphify\` quedó con solo
`.git` y sin archivos (típico de un clon interrumpido o de un `git clone --filter=blob:none`
cuya segunda fase falló).

**Solución:** borrá la carpeta incompleta y volvé a correr `install.bat`, que ahora detecta
clones rotos y reclona solo:
```powershell
Remove-Item -Recurse -Force "$env:USERPROFILE\.opengraphify\graphify"
Remove-Item -Recurse -Force "$env:USERPROFILE\.opengraphify\opengraphify"
install.bat
```
</details>

<details>
<summary><b>No puedo borrar <code>.opengraphify</code>: "No dispone de permisos suficientes"</b></summary>

**Causa:** git crea archivos `.pack` / `.idx` / `.rev` con atributo **solo-lectura**, y
Windows se niega a borrarlos con un `rmdir`/`del` común.

**Solución:** limpiá los atributos y después borrá:
```powershell
$d = "$env:USERPROFILE\.opengraphify"
Get-ChildItem $d -Recurse -Force | ForEach-Object { try { $_.Attributes = 'Normal' } catch {} }
Remove-Item -Recurse -Force $d
```
</details>

<details>
<summary><b>pip instala en el Python equivocado</b></summary>

**Causa:** tenés más de un Python y `pip` apunta a otro distinto de `python`.

**Solución:** usá siempre `python -m pip` (nunca `pip` pelado). Para ver cuál estás usando:
```powershell
python -c "import sys; print(sys.executable)"
```
`install.bat` ya usa `python -m pip` en todos lados.
</details>

<details>
<summary><b>Falla la extracción semántica (Ollama)</b></summary>

```text
[opengraphify] semantic extraction failed: Connection refused
```

**Causas y soluciones:**
- **Ollama no está corriendo:** abrí la app de Ollama (en Windows queda como servicio de
  fondo). Probá `curl http://localhost:11434/api/tags`.
- **Modelo no descargado:** `ollama pull qwen2.5-coder:3b` (o el que tengas en el toml).
- **Otro endpoint/puerto:** ajustá `base_url` en `opengraphify.toml` o pasá
  `--base-url http://localhost:11434/v1`.

> Recordá: esto **solo** afecta a docs/papers/imágenes. El grafo del **código** se construye
> igual sin Ollama.
</details>

<details>
<summary><b>Dice "graph is up to date" pero yo esperaba cambios</b></summary>

**Causa:** las corridas incrementales comparan hashes contra `manifest.json` y saltan lo que
no cambió; la extracción semántica además tiene **caché por archivo**.

**Solución:** forzá una re-extracción completa:
```bash
opengraphify . --force
```
</details>

<details>
<summary><b>La notebook se recalienta / quiero usar la GPU Intel (no NVIDIA)</b></summary>

El Ollama oficial solo acelera con **NVIDIA (CUDA)** o **AMD (ROCm)**; con una **iGPU Intel
Arc** corre en **CPU**, y en repos grandes eso recalienta (en casos extremos, BSOD del driver
Intel `igdlmdn64.sys`). Para correr el modelo sobre la Arc vía **IPEX-LLM** (más velocidad,
menos calor, y poder usar el 7B), seguí la guía dedicada:

➡️ **[README-GPU.md](README-GPU.md)** — reinstalar el driver Arc, verificar la GPU, instalar
el Ollama de IPEX-LLM y arrancarlo (incluye el troubleshooting de "`ollama list` se cuelga").

Mientras tanto, para bajar el estrés en CPU: usá el default **3B**, `--max N` para procesar por
tandas, y `OPENGRAPHIFY_TOKEN_BUDGET` más chico.
</details>

### 🧯 Errores, cuelgues y recuperación

<details>
<summary><b>Se queda colgado al terminar y el cursor no vuelve</b></summary>

Era un cuelgue conocido cuando el backend es **remoto**: al terminar el trabajo (el grafo ya
escrito), un socket *keep-alive* abierto trababa el cierre del intérprete **hasta ~10 min**.

**Ya está resuelto:** al terminar una corrida opengraphify **fuerza un cierre limpio** y, además,
**acota el timeout de red** a `api_timeout` (180s por defecto, contra los 600s = 10 min de
graphify), así un request trabado falla rápido en vez de congelar todo.

- Si aun así ves un cuelgue, corré con `OPENGRAPHIFY_DEBUG_HANG=1`: vuelca el *stack* del frame
  trabado cada N segundos para diagnosticarlo.
- `OPENGRAPHIFY_NO_FAST_EXIT=1` vuelve al cierre normal del intérprete (escape hatch).

</details>

<details>
<summary><b>"chunk failed" / error 524 / timeout: ¿se perdió todo?</b></summary>

**No.** Un chunk que falla (524 de Cloudflare, timeout, 5xx) se descarta **solo ese chunk**:
vas a ver `Partial results returned` y el grafo se construye igual con **todo lo demás**.

- **Se recupera solo:** los archivos del chunk fallido **no se anotan en el `manifest.json`**, así
  que la **próxima corrida los reprocesa** (los demás quedan cacheados y se saltean).
- **Reintento in-run:** ante un error *retryable* opengraphify espera el `Retry-After` del server
  (o `retry_wait_seconds`) y reintenta hasta `chunk_retries` veces antes de darlo por perdido.
- **Para menos 524** contra un backend remoto lento: bajá `token_budget` (chunks más rápidos).

> `Extraction warning (N issues): Edge ... missing required field 'source_file'` es un **warning
> cosmético** (el modelo omitió un campo en N aristas de miles). Las aristas **igual quedan en el
> grafo** — no es un fallo y no hace falta rehacer nada.
</details>

<details>
<summary><b>Quiero ver el grafo nodo por nodo (no agregado por comunidades)</b></summary>

Cuando el grafo supera **5000 nodos**, el `graph.html` se arma como **vista agregada por
comunidades** (si no, el navegador no aguanta 40k nodos). Para ver **nodo por nodo** usá la
exportación **Obsidian de graphify** sobre el grafo ya generado (comparten `graphify-out/`),
parado en el repo escaneado:

```bash
python -m graphify export obsidian
```

Genera `graphify-out/obsidian/` (un `.md` por nodo + `graph.canvas`); abrí esa carpeta como
*vault* en Obsidian, que sí maneja decenas de miles de nodos. Ojo: `--obsidian` es un flag de
**graphify**, opengraphify no lo expone.
</details>

---

## 📄 Licencia

OpenGraphify se distribuye bajo licencia **[MIT](LICENSE)** © 2026 erufeil.

El motor subyacente, **[graphify](https://github.com/safishamsi/graphify)**, es de
[@safishamsi](https://github.com/safishamsi) y mantiene su propia licencia. Revisá los términos
en su repositorio oficial antes de redistribuir.



