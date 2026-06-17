@echo off
setlocal EnableDelayedExpansion

echo ==============================================
echo  opengraphify - Actualizar librerias
echo ==============================================
echo.

set DEPS_DIR=%USERPROFILE%\.opengraphify

if not exist "%DEPS_DIR%" (
    echo No se encontro instalacion previa en %DEPS_DIR%
    echo Ejecuta install.bat primero.
    pause & exit /b 1
)

REM -----------------------------------------------
REM 1. Actualizar graphify (re-clonar)
REM -----------------------------------------------
echo [1/2] Actualizando graphify...
if exist "%DEPS_DIR%\graphify" (
    echo      Eliminando version anterior...
    rmdir /s /q "%DEPS_DIR%\graphify"
)
git clone --filter=blob:none --depth 1 https://github.com/safishamsi/graphify.git "%DEPS_DIR%\graphify"
if errorlevel 1 (
    echo ERROR: no se pudo clonar graphify.
    pause & exit /b 1
)
pip install -e "%DEPS_DIR%\graphify" --quiet
if errorlevel 1 (
    echo ERROR: pip install graphify fallo.
    pause & exit /b 1
)
echo      graphify actualizado OK.

REM -----------------------------------------------
REM 2. Actualizar opengraphify (re-clonar)
REM -----------------------------------------------
echo.
echo [2/2] Actualizando opengraphify...
if exist "%DEPS_DIR%\opengraphify" (
    echo      Eliminando version anterior...
    rmdir /s /q "%DEPS_DIR%\opengraphify"
)
git clone --filter=blob:none --depth 1 https://github.com/erufeil/opengraphify.git "%DEPS_DIR%\opengraphify"
if errorlevel 1 (
    echo ERROR: no se pudo clonar opengraphify.
    pause & exit /b 1
)
pip install -e "%DEPS_DIR%\opengraphify" --quiet
if errorlevel 1 (
    echo ERROR: pip install opengraphify fallo.
    pause & exit /b 1
)
echo      opengraphify actualizado OK.

echo.
echo ==============================================
echo  Actualizacion completada!
echo  Fuentes en: %DEPS_DIR%
echo ==============================================
echo.
pause
endlocal
