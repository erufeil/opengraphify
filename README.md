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
                       ┌─────────────── tokens CAROS ───────────────┐
   graphify (skill)  →  modelo de Claude Code procesa el grafo
                       └─────────────────────────────────────────────┘

                       ┌─────────────── tokens BARATOS ─────────────┐
   opengraphify (worker) → Ollama / OpenRouter procesa el grafo
                            graphify ve el grafo al día → no hace nada
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
| Ollama (backend por defecto) | [ollama.com](https://ollama.com) + `ollama pull qwen2.5-coder:7b` |

> **Ollama no necesita modo server.** En Windows corre como servicio de fondo automáticamente
> al instalarlo (queda escuchando en `http://localhost:11434`). No hace falta `ollama serve`.

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
opengraphify . --force            # re-extracción completa (ignora caché)
opengraphify . --status           # estado del grafo: nodos, edges, cambios pendientes
opengraphify . --watch            # modo daemon, cada 15 min (según config)
opengraphify . --watch --interval 5

# Overrides inline sin tocar el toml
opengraphify . --model llama3.1:8b
opengraphify . --base-url https://openrouter.ai/api/v1 --model mistralai/mistral-7b-instruct
```

Durante la extracción semántica vas a ver el avance **archivo por archivo**:

```text
[opengraphify] semantic extraction on 56 files via ollama (qwen2.5-coder:7b)...
[opengraphify] semantic extraction on README.md (1/56)
[opengraphify] semantic extraction on ARCHITECTURE.md (2/56)
...
```

> Los archivos se procesan en *chunks* paralelos, así que las líneas aparecen en ráfagas
> (varios archivos de golpe cada vez que un chunk del modelo responde).

### Como servicio en background (Windows)

```powershell
Start-Process opengraphify -ArgumentList ". --watch" -WindowStyle Hidden
```

O con el **Programador de tareas**: programa `opengraphify`, argumentos `C:\ruta\al\repo --watch`,
disparador "al iniciar sesión".

---

## ⚙️ Configuración

Poné un `opengraphify.toml` en la raíz de cualquier repo. Si no hay, usa los defaults
(Ollama + `qwen2.5-coder:7b`, cada 15 min).

```toml
[backend]
provider = "ollama"                    # proveedor
model    = "qwen2.5-coder:7b"          # modelo
base_url = "http://localhost:11434/v1" # endpoint (Ollama por defecto)
api_key  = ""                          # vacío para Ollama local

[schedule]
interval_minutes = 15

[output]
out_dir         = "graphify-out"   # debe coincidir con el out_dir de graphify
generate_html   = true
generate_report = true
```

### Usar OpenRouter en lugar de Ollama

```toml
[backend]
provider = "openrouter"
model    = "mistralai/mistral-7b-instruct"
base_url = "https://openrouter.ai/api/v1"
api_key  = "sk-or-..."
```

### Variables de entorno (override sin tocar el toml)

| Variable | Descripción |
| --- | --- |
| `OPENGRAPHIFY_PROVIDER` | Nombre del proveedor |
| `OPENGRAPHIFY_MODEL` | Modelo a usar |
| `OPENGRAPHIFY_BASE_URL` | URL base del endpoint |
| `OPENGRAPHIFY_API_KEY` | API key |
| `OPENGRAPHIFY_INTERVAL` | Intervalo en minutos para `--watch` |

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
| Gratis, sin internet | `qwen2.5-coder:7b` | Ollama local |
| Repos grandes (>500 archivos) | `codestral:22b` | Ollama local |
| Muy rápido y barato | `mistralai/mistral-7b-instruct` | OpenRouter |
| Alta calidad semántica | `deepseek/deepseek-coder-v2-lite-instruct` | OpenRouter |

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
- **Modelo no descargado:** `ollama pull qwen2.5-coder:7b`.
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

---

## 📄 Licencia

OpenGraphify se distribuye bajo licencia **[MIT](LICENSE)** © 2026 erufeil.

El motor subyacente, **[graphify](https://github.com/safishamsi/graphify)**, es de
[@safishamsi](https://github.com/safishamsi) y mantiene su propia licencia. Revisá los términos
en su repositorio oficial antes de redistribuir.
