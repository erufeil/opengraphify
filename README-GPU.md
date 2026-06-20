# README-GPU — Driver Intel Arc, verificación y aceleración por GPU/NPU

Notebook: **HP 14-ep1002la** · CPU **Intel Core Ultra 5 125H** (Meteor Lake) ·
iGPU **Intel Arc (Xe-LPG, 112 EU / 7 Xe-cores)** · **NPU** Intel AI Boost ·
**24 GB RAM (8+16)** · **sin CUDA** (CUDA es exclusivo de NVIDIA).

> **Idea central:** el crash `igdlmdn64.sys (0xD1)` y "la GPU desapareció" son un
> fallo del **driver de la Arc** bajo estrés. Primero hay que **recuperar y
> actualizar el driver**. Después, la mejor jugada no es pelear con un modelo 3B
> que no cumple, sino **correr qwen2.5-coder:7b sobre la iGPU Arc** (vía IPEX-LLM),
> que baja el calor (GPU en vez de CPU) **y** te devuelve la calidad del 7B.

---

## 1. Reinstalar el driver `igdlmdn64.sys` y recuperar la GPU desaparecida

`igdlmdn64.sys` es el driver kernel de la gráfica Intel. No se "reinstala el
archivo" suelto: se reinstala el **paquete de driver Intel Arc Graphics**.

### Paso 0 — Primeros auxilios (a veces alcanza)

1. **Apagado total**, no reinicio: apagá la notebook, sacá el cargador, esperá
   ~30 s y prendé. Un driver caído (TDR) suele reaparecer con un cold boot.
2. **Administrador de dispositivos** (`devmgmt.msc`):
   - Menú **Ver → Mostrar dispositivos ocultos**.
   - Buscá en **Adaptadores de pantalla** la "Intel Arc Graphics". Si aparece con
     un **triángulo amarillo** (código 43 / 10 / 31) está viva pero con el driver
     roto. Si no aparece, mirá en **Otros dispositivos**.
   - **Acción → Buscar cambios de hardware**.

### Paso 1 — Reinstalación limpia (recomendado para un crash recurrente)

1. **Descargá** el driver antes de desinstalar nada (vas a quedar sin gráfica un
   rato):
   - **Intel Driver & Support Assistant (DSA)** — detecta tu equipo y baja el
     driver Arc correcto automáticamente. Es lo más simple.
   - O bajá manual el **Intel Arc Graphics WHQL/DCH** más reciente (a junio 2026,
     rama `32.0.101.xxxx` o superior) desde Intel.
   - Alternativa OEM: el driver gráfico específico de **HP para la 14-ep1002la**
     en soporte de HP (a veces es más estable en notebooks, aunque más viejo).
2. **Desinstalá en limpio con DDU** (Display Driver Uninstaller):
   - Descargá DDU, entrá en **Modo seguro** de Windows.
   - DDU → seleccioná **GPU → Intel** → **"Clean and restart"**.
3. Al reiniciar, **instalá el driver** que bajaste en el Paso 1.
4. **Bloqueá que Windows Update lo pise**: Windows a veces reinstala una versión
   rota del driver Intel por su cuenta. Tras instalar el bueno, usá la
   herramienta **"Show or hide updates"** de Microsoft para ocultar la
   actualización de driver de pantalla Intel, o configurá que Windows no instale
   drivers automáticamente.

### Paso 2 — Si la GPU sigue sin aparecer

- Verificá en **BIOS/UEFI** que la gráfica integrada no esté deshabilitada.
- Probá una versión de driver **distinta** (a veces la última tiene un bug y una
  anterior es estable, o viceversa). Los crashes `0xD1` de la Arc suelen ser bugs
  de versión puntual que se arreglan subiendo (o bajando) de versión.
- Revisá temperatura: si el crash fue térmico (10 h al 100 %), limpiá ventilación
  y usá base refrigerante; un driver no aguanta un SoC en throttling extremo.

> **Importante:** si después vas a poner la **iGPU a inferir** (sección 4), el
> driver tiene que estar **al día y estable sí o sí** — ahí la Arc pasa a hacer
> cómputo pesado, no solo dibujar la pantalla. Un driver viejo = mismo crash pero
> ahora a propósito.

---

## 2. Cómo verificar que la GPU está OK

| Herramienta | Qué mirar |
|---|---|
| **Administrador de dispositivos** | "Intel Arc Graphics" en Adaptadores de pantalla, **sin** triángulo amarillo |
| **Administrador de tareas → Rendimiento → GPU** | Aparece la GPU Intel Arc, con memoria compartida y uso de motores |
| **`dxdiag`** (pestaña Pantalla) | Nombre de la GPU + "No se encontraron problemas" |
| **Intel Arc Control / Graphics Software** | Panel de control de Intel; versión de driver y estado |
| **`Get-PnpDevice -Class Display`** (PowerShell) | Estado `OK` del dispositivo |

Para verificar que sirve para **cómputo** (no solo pantalla):

- Instalá **`clinfo`** o el sample de **oneAPI** y confirmá que la Arc aparece como
  device OpenCL/SYCL.
- O directamente la prueba real: corré un modelo (sección 4) y mirá en
  **Administrador de tareas → GPU** que el motor **"Compute"** se mueva durante la
  inferencia, y/o `ollama ps` muestre `100% GPU` en la columna PROCESSOR.

---

## 3. Análisis: ¿por qué se "rompe" el 3B? Las opciones de contexto

La explicación web que leíste ("el 3B se rompe porque se acumula demasiado
**contexto histórico** en llama.cpp / autocompletado") **no aplica a tu caso**.
Eso pasa en plugins de **autocompletado** (Continue, etc.) que mantienen una
conversación con historial creciente. **opengraphify es distinto:** cada chunk es
una llamada **independiente y sin estado** — no hay historial que se acumule. Así
que `LLAMA_ARG_CTX_SIZE` y "reducir el búfer de fragmentos" son de otro escenario.

### Las opciones de contexto que SÍ importan acá

En opengraphify/graphify el "contexto" se controla con tres perillas (ya
documentadas en `README-info.md`):

| Perilla | Qué es | Default actual |
|---|---|---|
| `num_ctx` (Ollama) | ventana de contexto que reserva el modelo | auto = `input + salida + 2000`, piso **8192** |
| `token_budget` | tokens de **entrada** empacados por chunk | 4000 |
| `max_output_tokens` | tope de **salida** por chunk (`GRAPHIFY_MAX_OUTPUT_TOKENS`) | 2048 |

Dato clave: **si `num_ctx` es más chico que el prompt real, Ollama TRUNCA el
prompt en silencio** y el modelo devuelve JSON vacío o roto (graphify hasta avisa
de esto). Pero con tus defaults (`4000 + 2048 + 2000 → piso 8192`) el prompt entra
bien, así que **la truncación no es la causa**.

### Conclusión sobre el 3B

Si con el contexto correcto el 3B igual "casi nunca entrega lo solicitado", el
problema es **capacidad del modelo**, no contexto: un 3B se marea con el esquema
JSON estricto + el envoltorio de seguridad `<untrusted_source>` + varios archivos
por chunk, y emite prosa, fences markdown o JSON inválido. Opciones, de menor a
mayor impacto:

1. **Chunks más chicos para el 3B** — bajá `token_budget` a ~2000. Menos archivos
   por request = menos entidades que modelar = JSON más simple y más estable.
   (Es la única perilla de "contexto" que realmente puede ayudar al 3B.)
2. **Forzar JSON** — Ollama soporta `format: json` / structured outputs, que
   obliga al modelo a emitir JSON válido. Hoy graphify no lo pasa; sería un cambio
   de código (vía commit + `actualiza-librerias.bat`) si querés exprimir el 3B.
3. **La solución de fondo: volver al 7B, pero en GPU** (sección 4). El 7B sí sigue
   el esquema; el problema que tenías con el 7B era velocidad/calor en CPU, y eso
   lo resuelve la iGPU. Esto es lo que recomiendo.

---

## 4. Usar la iGPU Arc con Ollama (más GPU, menos CPU)

**La verdad incómoda:** el **Ollama estándar de Windows NO usa la Intel Arc**.
Solo acelera con NVIDIA (CUDA) o AMD (ROCm). Hoy tu Ollama corre en **CPU** — por
eso ~1 min/chunk y el calor sostenido. "Configurar Ollama para usar más GPU"
**requiere cambiar el backend**. Dos caminos:

### Opción A (recomendada) — Ollama de IPEX-LLM (Intel, vía SYCL/oneAPI)

Intel mantiene un **fork de Ollama acelerado** que sí corre sobre la Arc iGPU.
Probado en el **Core Ultra 5 125H**. Lo más fácil es el **"Ollama Portable Zip"**
de IPEX-LLM:

1. Asegurate del **driver Arc actualizado** (sección 1) y de tener el runtime
   oneAPI que pida la guía.

2. **Desinstalá / apagá el Ollama oficial primero** (importante, para que no haya
   conflicto). Los dos usan el mismo puerto `11434` y el mismo comando `ollama`,
   así que conviene dejar solo el de IPEX-LLM:
   - Cerrá el Ollama que esté corriendo: ícono en la bandeja → **Quit**, o desde
     PowerShell `Stop-Process -Name ollama -Force` (o terminá `ollama app.exe` en
     el Administrador de tareas).
   - **Desinstalá el Ollama oficial**: Configuración → Aplicaciones → "Ollama" →
     Desinstalar (o `winget uninstall Ollama.Ollama`).
   - Si tenías el oficial como **servicio/inicio automático**, desactivalo
     (`Win+R` → `shell:startup`, sacá Ollama; o desactivá el servicio).
   - Asegurate de que el puerto quedó libre: `netstat -ano | findstr 11434` no
     debería devolver nada.
   - (Tus modelos ya descargados quedan en `%USERPROFILE%\.ollama\models`; el zip
     de IPEX-LLM puede reutilizarlos, no hace falta re-bajarlos.)

3. **Cuál asset bajar** del release de IPEX-LLM (la página lista 3 productos
   distintos — fijate en el **prefijo** y el **sufijo**, no en la fecha sola):

   | Archivo | Qué es | ¿Bajar? |
   | --- | --- | --- |
   | `ollama-ipex-llm-…-win.zip` | **Ollama** acelerado para GPU Intel | ✅ **Sí** |
   | `llama-cpp-ipex-llm-…-win.zip` | llama.cpp pelado (sin server Ollama) | ❌ No |
   | `llama-cpp-ipex-llm-…-win-npu.zip` | llama.cpp para la **NPU** (build aparte, no es "viejo") | ❌ No |
   | `…-ubuntu…` / `…-xeon…` | builds de Linux/servidor | ❌ No |

   Elegí el **`ollama-…-win.zip` con la fecha más alta**. En la lista que tenías,
   ese era **`ollama-ipex-llm-2.3.0b20250725-win.zip`** (25-jul-2025). Verificá el
   `sha256` tras bajarlo:
   `47fc5a3c3e8d95f97e06df8884535700ecb816c1ea9d85a8ef7d96d77fbc06fe`.
   Si en el repo hay un release más nuevo, usá el `ollama-…-win.zip` más reciente.

4. **Descomprimí** el zip en una carpeta propia (p. ej. `D:\ollama-ipex`). NO
   corras `ollama serve` a mano: el zip trae su **lanzador** `start-ollama.bat`,
   que setea el entorno de GPU antes de arrancar el server. Desde **cmd** (no
   PowerShell — los scripts son de cmd):

   ```bat
   cd /d D:\ollama-ipex
   start-ollama.bat
   ```

   Se abre una **ventana nueva "Ollama Serve"**: **esa ventana ES el server**, se
   queda mostrando logs y **no acepta que escribas** — es normal, dejala abierta
   (minimizala). Esperá a ver estas dos líneas:

   ```text
   msg="using Intel GPU"
   msg="Listening on 127.0.0.1:11434 ..."
   ```

5. La aceleración a GPU **ya viene configurada** en el `ollama-serve.bat` del zip
   (no tenés que setear nada): incluye `OLLAMA_NUM_GPU=999` (todas las capas a la
   Arc), `ZES_ENABLE_SYSMAN=1`, `OLLAMA_HOST=127.0.0.1:11434`. El server expone la
   **misma API** que el Ollama oficial, incluido el endpoint OpenAI
   `/v1/chat/completions` → **opengraphify funciona sin cambios** (mismo
   `base_url`).

6. **En OTRA ventana de cmd** (no la del server), bajá y usá el **7B**:

   ```bat
   cd /d D:\ollama-ipex
   ollama list                      :: ver modelos ya presentes
   ollama pull qwen2.5-coder:7b     :: bajarlo si falta
   ```

   Y en `opengraphify.toml` poné `model = "qwen2.5-coder:7b"`.

   > Ojo con la **carpeta de modelos**: este server usa `OLLAMA_MODELS=D:\ollama-models`
   > (no el `~/.ollama` del Ollama oficial). Los modelos que tuvieras en la carpeta
   > vieja no se ven acá — bajalos de nuevo con `ollama pull`.

Con esto: el 7B corre en la **Arc**, la **CPU queda libre** (menos calor → menos
riesgo de otro `0xD1`), y mantenés tu pipeline. Tus 24 GB de RAM alcanzan de
sobra para un 7B Q4 (~5 GB de pesos + contexto) en memoria compartida.

> Nota de versión: el Ollama de IPEX-LLM que probamos reporta **0.9.3** y ya trae
> los endpoints `/v1` (`/v1/chat/completions`, `/v1/models`), que es todo lo que
> opengraphify necesita.

> Nota de RAM: Intel recomienda 16 GB en **doble canal** para el máximo de la Arc.
> Tu 8+16 corre en "flex mode" (parte en doble canal, parte en simple): rinde un
> poco menos que 2×8 o 2×16 simétrico, pero es **suficiente** para un 7B Q4.

#### Troubleshooting: `ollama list` (o `pull`) se cuelga

Síntoma real que vimos: el comando cliente queda colgado y hay que cortarlo con
`Ctrl+C`. **Casi siempre es por dos servers en conflicto**: si corrés
`start-ollama.bat` **dos veces**, quedan dos `ollama.exe` peleando por el puerto
`11434` y la carpeta de modelos; uno toma el puerto pero queda deadlockeado y
**deja de responder** (un `GET /api/version` también da timeout).

Cómo confirmarlo y arreglarlo:

```bat
:: ¿cuántos servers hay? ¿el puerto responde?
netstat -ano | findstr 11434
:: matá TODOS los ollama y arrancá uno solo
taskkill /F /IM ollama.exe
:: confirmá que NO queda ninguna línea "LISTENING" (un "TIME_WAIT" suelto es inofensivo)
netstat -ano | findstr 11434
:: ahora sí, UNA sola vez
start-ollama.bat
```

Regla: **`start-ollama.bat` una sola vez por sesión.** Si dudás de si ya hay uno
corriendo, `taskkill /F /IM ollama.exe` primero y arrancá limpio. Para verificar
que quedó sano antes de pullear: `curl http://127.0.0.1:11434/api/version` debe
responder al toque, o abrí `http://127.0.0.1:11434` en el navegador (dice
"Ollama is running"). Otras causas posibles del cuelgue: variables de proxy
(`HTTP_PROXY`/`HTTPS_PROXY`) sin `no_proxy=localhost,127.0.0.1` — el server las
limpia, pero una ventana cliente nueva no.

### Opción B — Ollama con backend Vulkan (experimental)

Ollama incorporó **soporte Vulkan experimental** (desde ~0.12.6, compilando desde
fuente / release rc) que abre la puerta a GPUs Intel/AMD sin SYCL/ROCm. Es más
nuevo y menos pulido que IPEX-LLM, pero es nativo de Ollama. Opción si no querés
el fork de Intel.

### Lo que NO mueve la aguja

- `OLLAMA_NUM_THREADS`, `num_ctx`, etc. en el Ollama **oficial** solo regulan la
  **CPU** — no van a "pasar trabajo a la Arc" porque ese binario ni la ve. Bajar
  threads sirve para **calor/estabilidad**, no para acelerar con GPU.

---

## 5. Usar la NPU (OpenVINO) — análisis honesto

Tu Core Ultra tiene NPU (Intel AI Boost), pero para **modelos coder grandes hoy
es un callejón limitado**:

- En **OpenVINO 2026.0**, el soporte NPU para esta familia llega solo hasta
  modelos **chicos**: `Qwen2.5-1.5B-Instruct` y `Qwen2.5-coder-**0.5B**`. Un 7B en
  NPU todavía **no está soportado de forma usable** (la NPU tiene límites de
  memoria y de operadores). Existe algún 7B INT4 "para NPU" experimental
  (`llmware/...-npu-ov`), pero es bleeding-edge y no apto para producción.
- **Conclusión:** la NPU te sirve para un 0.5–1.5B… que es justo el tamaño que ya
  viste que **no cumple** con tu prompt. Para tu tarea, la NPU **no es el camino
  hoy**. La iGPU Arc sí.

Si igual querés explorar OpenVINO (por ejemplo para correr el 7B INT4 **en la
Arc**, no en la NPU):

- **OpenVINO Model Server (OVMS)** expone endpoints **compatibles con OpenAI** y
  ya soporta **modelos GGUF** (Qwen2/2.5/3, Llama3) desplegables con un comando,
  apuntando a **GPU** o NPU. opengraphify podría apuntar su `base_url` ahí sin
  más cambios.
- Hay modelos 7B ya convertidos, p. ej. `AIFunOver/Qwen2.5-Coder-7B-Instruct-openvino-4bit`
  en Hugging Face, que en la **Arc** rinde bien.
- **NoLlama**: front-end local para hardware Intel (API estilo OpenAI/Ollama) que
  autodetecta NPU/Arc/CPU. Es la vía "fácil" si querés probar el stack Intel sin
  pelear con OpenVINO a mano.

---

## 6. Plan de acción recomendado

1. **Recuperá y actualizá el driver Arc** (sección 1) — sin esto, nada de GPU.
   Verificá con la sección 2.
2. **Instalá el Ollama de IPEX-LLM** (sección 4, Opción A) y confirmá `100% GPU`
   en `ollama ps`.
3. **Volvé al 7B**: en `opengraphify.toml`, `model = "qwen2.5-coder:7b"`. Recuperás
   calidad y, al correr en la Arc, sin el calor que mataba la CPU.
4. **Mantené las redes de seguridad** que ya agregamos: `--max N` para procesar en
   tandas y el **caché por chunk** para reanudar si algo se corta.
5. Si por lo que sea seguís en CPU con el 3B, bajá `token_budget` a ~2000 y
   considerá forzar `format: json` (cambio de código) — pero es un parche, no la
   solución.

---

## Fuentes

- [intel/ipex-llm (GitHub)](https://github.com/intel/ipex-llm)
- [Run Ollama with IPEX-LLM on Intel GPU (quickstart)](https://github.com/intel/ipex-llm/blob/main/docs/mddocs/Quickstart/ollama_quickstart.md)
- [Run Ollama Portable Zip on Intel GPU with IPEX-LLM](https://github.com/intel/ipex-llm/blob/main/docs/mddocs/Quickstart/ollama_portable_zip_quickstart.md)
- [Intel Arc GPU + Ollama: Full Setup Guide with IPEX-LLM (Markaicode)](https://markaicode.com/intel-arc-gpu-ollama-openvino-tutorial/)
- [ollama Rolls Out Experimental Vulkan Support (Phoronix)](https://www.phoronix.com/news/ollama-Experimental-Vulkan)
- [Build and run ollama with Vulkan on Intel Arc (kovasky.me)](https://kovasky.me/blogs/ollama_vulkan_intel/)
- [OpenVINO 2026.0.0 Release Notes (NPU: Qwen2.5-1.5B, Qwen2.5-coder-0.5B)](https://github.com/openvinotoolkit/openvino/releases/tag/2026.0.0)
- [OpenVINO Model Server soporta modelos GGUF (blog)](https://blog.openvino.ai/blog-posts/openvino-genai-supports-gguf-models)
- [Qwen2.5-Coder-7B-Instruct-openvino-4bit (Hugging Face)](https://huggingface.co/AIFunOver/Qwen2.5-Coder-7B-Instruct-openvino-4bit)
- [Intel Arc Graphics DCH Driver (TechSpot)](https://www.techspot.com/drivers/driver/file/information/18420/)
- [igdkmd64.sys / BSOD Intel Arc 140V (Microsoft Q&A)](https://learn.microsoft.com/en-us/answers/questions/5548686/how-to-fix-igdkmd64-sys-blue-screen-of-death-error)
