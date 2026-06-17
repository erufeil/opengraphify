@echo off
setlocal EnableDelayedExpansion

echo ==============================================
echo  opengraphify - Instalacion universal
echo  Corre este archivo desde cualquier carpeta
echo ==============================================
echo.

set DEPS_DIR=%USERPROFILE%\.opengraphify

REM -----------------------------------------------
REM Verificar git
REM -----------------------------------------------
where.exe git >nul 2>&1
if errorlevel 1 (
    echo ERROR: 'git' no encontrado en PATH.
    echo Instalar desde: https://git-scm.com/download/win
    echo Marcar "Add Git to PATH" durante la instalacion.
    pause & exit /b 1
)

REM -----------------------------------------------
REM Verificar python
REM -----------------------------------------------
where.exe python >nul 2>&1
if errorlevel 1 (
    echo ERROR: 'python' no encontrado en PATH.
    echo Instalar Python 3.10+ desde: https://www.python.org/downloads/
    echo Marcar "Add Python to PATH" durante la instalacion.
    pause & exit /b 1
)

echo Python activo:
python --version
for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)"') do echo   Ejecutable: %%P
echo.

REM -----------------------------------------------
REM Crear carpeta central de dependencias
REM -----------------------------------------------
if not exist "%DEPS_DIR%" mkdir "%DEPS_DIR%"
echo Carpeta central: %DEPS_DIR%
echo.

REM -----------------------------------------------
REM 1. Clonar e instalar graphify
REM -----------------------------------------------
echo [1/5] graphify...
if exist "%DEPS_DIR%\graphify" (
    echo      Carpeta ya existe, saltando clon.
    echo      Para actualizar a la ultima version: actualiza-librerias.bat
) else (
    echo      Clonando desde GitHub...
    git clone --filter=blob:none --depth 1 https://github.com/safishamsi/graphify.git "%DEPS_DIR%\graphify"
    if errorlevel 1 (
        echo ERROR: no se pudo clonar graphify. Verificar conexion a internet.
        pause & exit /b 1
    )
    echo      Clonado OK.
)
echo      Instalando como paquete pip...
python -m pip install -e "%DEPS_DIR%\graphify" --quiet
if errorlevel 1 (
    echo ERROR: instalacion de graphify fallo.
    pause & exit /b 1
)
echo      OK.

REM -----------------------------------------------
REM 2. openai SDK (graphify lo necesita para Ollama)
REM -----------------------------------------------
echo.
echo [2/5] openai SDK...
python -m pip install "openai>=1.0" --quiet
echo      OK.

REM -----------------------------------------------
REM 3. Clonar e instalar opengraphify
REM -----------------------------------------------
echo.
echo [3/5] opengraphify...
if exist "%DEPS_DIR%\opengraphify" (
    echo      Carpeta ya existe, saltando clon.
    echo      Para actualizar: actualiza-librerias.bat
) else (
    echo      Clonando desde GitHub...
    git clone --filter=blob:none --depth 1 https://github.com/erufeil/opengraphify.git "%DEPS_DIR%\opengraphify"
    if errorlevel 1 (
        echo ERROR: no se pudo clonar opengraphify.
        pause & exit /b 1
    )
    echo      Clonado OK.
)
echo      Instalando como paquete pip...
python -m pip install -e "%DEPS_DIR%\opengraphify" --quiet
if errorlevel 1 (
    echo ERROR: instalacion de opengraphify fallo.
    pause & exit /b 1
)
echo      OK.

REM -----------------------------------------------
REM 4. Agregar carpeta Scripts al PATH del usuario
REM    para que "opengraphify" funcione sin "python -m"
REM -----------------------------------------------
echo.
echo [4/5] Configurando PATH...
for /f "delims=" %%S in ('python -c "import sysconfig; print(sysconfig.get_path(\"scripts\"))"') do set SCRIPTS_DIR=%%S
echo      Scripts en: %SCRIPTS_DIR%

REM Activar en esta sesion
set PATH=%PATH%;%SCRIPTS_DIR%

REM Verificar si ya esta en el PATH permanente del usuario
powershell -NoProfile -Command "exit ([Environment]::GetEnvironmentVariable('Path','User') -like '*%SCRIPTS_DIR%*')" >nul 2>&1
if errorlevel 1 (
    echo      Agregando al PATH permanente del usuario...
    powershell -NoProfile -Command ^
        "$old = [Environment]::GetEnvironmentVariable('Path','User'); ^
         $new = $old + ';%SCRIPTS_DIR%'; ^
         [Environment]::SetEnvironmentVariable('Path', $new, 'User')"
    echo      Agregado. Funciona en terminales NUEVAS.
) else (
    echo      Ya estaba en PATH.
)

REM -----------------------------------------------
REM 5. Verificar instalacion
REM -----------------------------------------------
echo.
echo [5/5] Verificando...

python -m opengraphify --help >nul 2>&1
if errorlevel 1 (
    echo      ERROR: python -m opengraphify fallo. Ver errores arriba.
    pause & exit /b 1
)
echo      OK - python -m opengraphify funciona.

opengraphify --help >nul 2>&1
if errorlevel 1 (
    echo      'opengraphify' aun no disponible en esta sesion ^(normal^).
    echo      Abri una nueva terminal y funcionara directamente.
) else (
    echo      OK - 'opengraphify' disponible directamente.
)

echo.
echo ================================================
echo  Instalacion completada!
echo.
echo  graphify    : %DEPS_DIR%\graphify
echo  opengraphify: %DEPS_DIR%\opengraphify
echo  Scripts     : %SCRIPTS_DIR%
echo.
echo  PROXIMOS PASOS:
echo.
echo  1. Instalar Ollama ^(si no lo tenes^):
echo       https://ollama.com
echo.
echo  2. Bajar el modelo de IA local:
echo       ollama pull qwen2.5-coder:7b
echo.
echo  3. En cada repo nuevo ^(una sola vez^):
echo       graphify install --project
echo.
echo  4. Construir el primer grafo ^(sin gastar tokens de Claude^):
echo       python -m opengraphify . --force
echo.
echo  5. En terminales NUEVAS ya funciona sin python -m:
echo       opengraphify . --watch
echo ================================================
echo.
pause
endlocal
