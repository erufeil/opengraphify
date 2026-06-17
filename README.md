# 
# SKILL: Graphify --> WORKER: OpenGraphify
#
# he aqui el worker silencioso: [OpenGraphify]
#

Background knowledge-graph updater for [graphify](https://github.com/safishamsi/graphify).
Runs the full extraction pipeline using a **local or cheap LLM** (Ollama, OpenRouter, DeepSeek, etc.)
so the Claude Code model in VS Code never spends tokens processing graph updates.

Una vez instalado, `opengraphify .` funciona desde **cualquier repositorio** de tu PC,
sin necesidad de copiar nada.

---

## Arquitectura

```text
%USERPROFILE%\.opengraphify\
    graphify\        ← graphify instalado UNA sola vez (pip -e)
                       se actualiza con actualiza-librerias.bat

d:\Github\ERF\opengraphify\   ← este repo (opengraphify)
    opengraphify\              ← código fuente
    install.bat                ← instala todo la primera vez
    actualiza-librerias.bat    ← actualiza graphify + opengraphify

C:\cualquier-repo\
    opengraphify.toml          ← config opcional por repo (backend, modelo, etc.)
    graphify-out\              ← grafo generado (ignorar en git)
```

opengraphify y graphify se instalan como paquetes pip globales.
Después `opengraphify .` funciona desde cualquier directorio de tu PC.

---

## ¿Puedo borrar la carpeta `/graphify` local?

**Sí**, una vez que ejecutaste `install.bat`.

La carpeta `graphify/` dentro del repo opengraphify es solo para referencia/desarrollo.
Después de instalar, graphify vive en `%USERPROFILE%\.opengraphify\graphify\` y está
en el `.gitignore` del proyecto.

---

## Ollama: ¿necesito modo server?

**No.** Ollama en Windows corre como servicio de fondo automáticamente al instalarlo
(ícono en la barra del sistema). No necesitás ejecutar `ollama serve` manualmente.

Solo necesitás:

1. Instalar Ollama desde [ollama.com](https://ollama.com)
2. Bajar el modelo: `ollama pull qwen2.5-coder:7b`

Ollama queda escuchando en `http://localhost:11434` siempre que la PC esté encendida.

---

## Instalación (primera vez)

Solo necesitás el archivo `install.bat` — **no hace falta clonar el repo antes**.
El script descarga todo solo.

```bat
install.bat
```

El script hace:

1. Clona graphify en `%USERPROFILE%\.opengraphify\graphify\` y lo instala con pip
2. Clona opengraphify en `%USERPROFILE%\.opengraphify\opengraphify\` y lo instala con pip

Ambos quedan registrados como paquetes pip (editable install).
El comando `opengraphify` queda disponible desde cualquier terminal.

**Requisitos previos:**

- Python 3.10+ ([python.org](https://www.python.org/downloads/))
- Git ([git-scm.com](https://git-scm.com/download/win))
- Ollama ([ollama.com](https://ollama.com)) + `ollama pull qwen2.5-coder:7b`

---

## Actualizar librerias

```bat
actualiza-librerias.bat
```

El script hace:

1. Re-clona graphify desde GitHub (última versión)
2. Reinstala graphify
3. Hace `git pull` en opengraphify y reinstala

> **¿Cuándo actualizar graphify?** graphify se actualiza con frecuencia.
> Si opengraphify deja de funcionar o querés nuevas funciones, ejecutá este bat.
> No es necesario hacerlo automáticamente.

---

## Configuración

Podés poner un `opengraphify.toml` en la raíz de cualquier repo que quieras escanear.
Si no hay uno, usa los defaults (Ollama + qwen2.5-coder:7b, cada 15 min).

```toml
[backend]
provider = "ollama"                    # proveedor
model    = "qwen2.5-coder:7b"          # modelo
base_url = "http://localhost:11434/v1" # URL del endpoint (Ollama default)
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

### Variables de entorno (override sin modificar el toml)

| Variable | Descripción |
| --- | --- |
| `OPENGRAPHIFY_PROVIDER` | Nombre del proveedor |
| `OPENGRAPHIFY_MODEL` | Modelo a usar |
| `OPENGRAPHIFY_BASE_URL` | URL base del endpoint API |
| `OPENGRAPHIFY_API_KEY` | API key |
| `OPENGRAPHIFY_INTERVAL` | Intervalo en minutos para `--watch` |

---

## Uso

### Una corrida manual (desde cualquier repo)

```bash
cd C:\mi-proyecto
opengraphify .
```

### Modo daemon (actualización automática)

```bash
opengraphify . --watch            # cada 15 min (según config)
opengraphify . --watch --interval 5
```

### Otros comandos

```bash
opengraphify . --force            # re-extracción completa (ignora caché)
opengraphify . --status           # estado del grafo: nodos, cambios pendientes

# Overrides inline sin toml
opengraphify . --model llama3.1:8b
opengraphify . --base-url https://openrouter.ai/api/v1 --model mistralai/mistral-7b-instruct
```

---

## Integración con graphify

opengraphify escribe en el **mismo directorio de salida** que graphify
(`graphify-out/` por defecto) y actualiza el mismo `manifest.json`.

Cuando graphify intenta actualizar el grafo, detecta que los hashes ya están al día
y **no vuelve a procesar nada**. El modelo de Claude Code queda libre.

```text
graphify-out/
├── graph.json              ← generado por opengraphify
├── graph.html              ← visualización interactiva
├── GRAPH_REPORT.md         ← informe de comunidades, nodos hub, ciclos
├── manifest.json           ← estado compartido (graphify ve el grafo como up-to-date)
├── .graphify_analysis.json
└── cache/                  ← caché semántico por archivo
```

Agregar al `.gitignore` del repo de trabajo:

```text
graphify-out/
```

---

## Ejecutar como servicio en background (Windows)

Desde una terminal de VS Code o PowerShell:

```powershell
Start-Process python -ArgumentList "-m opengraphify . --watch" -WindowStyle Hidden
```

O con Windows Task Scheduler:

- **Program:** `python`
- **Arguments:** `-m opengraphify C:\ruta\al\repo --watch`
- **Trigger:** Al iniciar sesión

---

## Modelos recomendados

| Caso | Modelo sugerido | Proveedor |
| --- | --- | --- |
| Gratis, sin internet | `qwen2.5-coder:7b` | Ollama local |
| Repos grandes (>500 archivos) | `codestral:22b` | Ollama local |
| Muy rápido y barato | `mistralai/mistral-7b-instruct` | OpenRouter |
| Alta calidad semántica | `deepseek/deepseek-coder-v2-lite-instruct` | OpenRouter |
