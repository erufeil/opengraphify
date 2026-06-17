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
REM    Primero verifica si ya esta instalado como paquete pip.
REM    Si esta, lo saltea (no duplica ni pisa la instalacion existente).
REM    Si no esta, clona a la carpeta central y lo instala.
REM -----------------------------------------------
echo [1/4] graphify...
pip show graphify >nul 2>&1
if not errorlevel 1 (
    REM Ya instalado — mostrar desde donde
    for /f "tokens=1,* delims=: " %%A in ('pip show graphify ^| findstr /i "Location"') do (
        echo      Ya instalado. Ubicacion: %%B
    )
    echo      Saltando. Para reinstalar en %DEPS_DIR%\graphify: borrar esa carpeta y volver a correr.
) else (
    echo      No esta instalado. Clonando...
    if not exist "%DEPS_DIR%\graphify" (
        git clone --filter=blob:none --depth 1 https://github.com/safishamsi/graphify.git "%DEPS_DIR%\graphify"
        if errorlevel 1 (
            echo ERROR: no se pudo clonar graphify. Verificar conexion a internet.
            pause & exit /b 1
        )
    )
    echo      Instalando...
    pip install -e "%DEPS_DIR%\graphify" --quiet
    if errorlevel 1 (
        echo ERROR: pip install graphify fallo.
        pause & exit /b 1
    )
    echo      OK ^(fuente: %DEPS_DIR%\graphify^)
)

REM -----------------------------------------------
REM 2. Instalar dependencias extra de graphify para Ollama
REM    (el extra [ollama] agrega el cliente openai que graphify necesita)
REM -----------------------------------------------
echo.
echo [2/4] Dependencias de graphify para Ollama...
pip install "openai>=1.0" --quiet
echo      OK.

REM -----------------------------------------------
REM 3. opengraphify
REM    Si este bat esta dentro del repo (hay pyproject.toml al lado),
REM    instala desde ahi. Si no, clona de GitHub.
REM -----------------------------------------------
echo.
echo [3/4] opengraphify...
pip show opengraphify >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=1,* delims=: " %%A in ('pip show opengraphify ^| findstr /i "Location"') do (
        echo      Ya instalado. Ubicacion: %%B
    )
    echo      Saltando. Para reinstalar: borrar %DEPS_DIR%\opengraphify y volver a correr.
) else (
    REM Detectar si estamos corriendo desde el repo fuente
    set OGF_SOURCE=
    if exist "%~dp0pyproject.toml" (
        set OGF_SOURCE=%~dp0
        REM Quitar barra final
        if "!OGF_SOURCE:~-1!"=="\" set OGF_SOURCE=!OGF_SOURCE:~0,-1!
        echo      Fuente local detectada: !OGF_SOURCE!
    ) else (
        echo      Fuente local no encontrada. Clonando de GitHub...
        if not exist "%DEPS_DIR%\opengraphify" (
            git clone --filter=blob:none --depth 1 https://github.com/erufeil/opengraphify.git "%DEPS_DIR%\opengraphify"
            if errorlevel 1 (
                echo ERROR: no se pudo clonar opengraphify.
                echo Asegurate de que el repo tenga el codigo publicado en GitHub,
                echo o corre este bat desde la carpeta del repo opengraphify.
                pause & exit /b 1
            )
        )
        set OGF_SOURCE=%DEPS_DIR%\opengraphify
    )
    echo      Instalando desde !OGF_SOURCE!...
    pip install -e "!OGF_SOURCE!" --quiet
    if errorlevel 1 (
        echo ERROR: pip install opengraphify fallo.
        pause & exit /b 1
    )
    echo      OK ^(fuente: !OGF_SOURCE!^)
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
