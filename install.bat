@echo off
setlocal EnableDelayedExpansion

echo ==============================================
echo  opengraphify - Instalacion
echo  (solo necesitas este archivo .bat)
echo ==============================================
echo.

REM Carpeta central donde viven graphify y opengraphify
set DEPS_DIR=%USERPROFILE%\.opengraphify

REM -----------------------------------------------
REM Verificar que git y pip esten disponibles
REM -----------------------------------------------
where git >nul 2>&1
if errorlevel 1 (
    echo ERROR: 'git' no encontrado en PATH.
    echo Instalar desde: https://git-scm.com/download/win
    pause & exit /b 1
)
where pip >nul 2>&1
if errorlevel 1 (
    echo ERROR: 'pip' no encontrado en PATH.
    echo Instalar Python desde: https://www.python.org/downloads/
    pause & exit /b 1
)

REM -----------------------------------------------
REM Crear carpeta central
REM -----------------------------------------------
if not exist "%DEPS_DIR%" mkdir "%DEPS_DIR%"
echo Carpeta de instalacion: %DEPS_DIR%
echo.

REM -----------------------------------------------
REM 1. graphify
REM    Usa la carpeta central como fuente unica.
REM    Si la carpeta ya existe: ya fue instalado por este bat, saltar.
REM    Si no existe: clonar e instalar, pisando cualquier version vieja.
REM    Esto garantiza compatibilidad: opengraphify siempre usa la version
REM    correcta de graphify, independientemente de lo que haya instalado antes.
REM -----------------------------------------------
echo [1/4] graphify...
if exist "%DEPS_DIR%\graphify" (
    echo      Ya instalado desde %DEPS_DIR%\graphify
    echo      Para actualizar a la ultima version: actualiza-librerias.bat
) else (
    echo      Clonando...
    git clone --filter=blob:none --depth 1 https://github.com/safishamsi/graphify.git "%DEPS_DIR%\graphify"
    if errorlevel 1 (
        echo ERROR: no se pudo clonar graphify. Verificar conexion a internet.
        pause & exit /b 1
    )
    echo      Instalando ^(pisa cualquier version previa^)...
    pip install -e "%DEPS_DIR%\graphify" --quiet
    if errorlevel 1 (
        echo ERROR: pip install graphify fallo.
        pause & exit /b 1
    )
    echo      OK ^(fuente: %DEPS_DIR%\graphify^)
)

REM -----------------------------------------------
REM 2. Dependencia: openai SDK (necesaria para que graphify hable con Ollama)
REM -----------------------------------------------
echo.
echo [2/4] Dependencias para Ollama...
pip install "openai>=1.0" --quiet
echo      OK.

REM -----------------------------------------------
REM 3. opengraphify
REM    Misma logica: carpeta central como fuente unica.
REM -----------------------------------------------
echo.
echo [3/4] opengraphify...
if exist "%DEPS_DIR%\opengraphify" (
    echo      Ya instalado desde %DEPS_DIR%\opengraphify
    echo      Para actualizar: actualiza-librerias.bat
) else (
    echo      Clonando...
    git clone --filter=blob:none --depth 1 https://github.com/erufeil/opengraphify.git "%DEPS_DIR%\opengraphify"
    if errorlevel 1 (
        echo ERROR: no se pudo clonar opengraphify.
        pause & exit /b 1
    )
    echo      Instalando...
    pip install -e "%DEPS_DIR%\opengraphify" --quiet
    if errorlevel 1 (
        echo ERROR: pip install opengraphify fallo.
        pause & exit /b 1
    )
    echo      OK ^(fuente: %DEPS_DIR%\opengraphify^)
)

REM -----------------------------------------------
REM 4. Verificar que el comando quedo en PATH
REM -----------------------------------------------
echo.
echo [4/4] Verificando PATH...
where opengraphify >nul 2>&1
if errorlevel 1 (
    echo      AVISO: 'opengraphify' no esta en PATH todavia.
    echo      Cerra y reabri la terminal, luego proba: opengraphify --help
    echo      Si sigue sin aparecer: python -m opengraphify --help
) else (
    echo      OK. 'opengraphify' disponible en PATH.
)

echo.
echo ==============================================
echo  Instalacion completada!
echo.
echo  graphify    : %DEPS_DIR%\graphify
echo  opengraphify: %DEPS_DIR%\opengraphify
echo.
echo  Proximos pasos:
echo    1. Instalar Ollama: https://ollama.com
echo    2. Bajar el modelo: ollama pull qwen2.5-coder:7b
echo    3. Ir a cualquier repo y correr: opengraphify .
echo.
echo  Comandos utiles:
echo    opengraphify .                 una corrida incremental
echo    opengraphify . --watch         daemon cada 15 min
echo    opengraphify . --status        ver estado del grafo
echo    opengraphify . --force         re-extraccion completa
echo ==============================================
echo.
pause
endlocal
