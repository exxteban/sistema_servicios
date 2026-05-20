@echo off
REM Script para crear el archivo .env desde el ejemplo
REM Este script copia .env.example a .env para que puedas editarlo

echo ========================================
echo   Configurador de Base de Datos
echo   Sistema Cliente Silvio
echo ========================================
echo.

if exist .env (
    echo [ADVERTENCIA] Ya existe un archivo .env
    echo.
    set /p OVERWRITE="¿Deseas sobrescribirlo? (S/N): "
    if /i not "%OVERWRITE%"=="S" (
        echo Operación cancelada.
        pause
        exit /b 0
    )
)

echo Copiando .env.example a .env...
copy .env.example .env >nul

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [ÉXITO] Archivo .env creado correctamente.
    echo.
    echo ========================================
    echo   PRÓXIMOS PASOS:
    echo ========================================
    echo.
    echo 1. Abre MySQL y ejecuta:
    echo    CREATE DATABASE bd_silvio CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    echo    CREATE USER 'silvio_user'@'localhost' IDENTIFIED BY 'tu_password';
    echo    GRANT ALL PRIVILEGES ON bd_silvio.* TO 'silvio_user'@'localhost';
    echo    FLUSH PRIVILEGES;
    echo.
    echo 2. Edita el archivo .env y actualiza:
    echo    - El usuario de MySQL (silvio_user)
    echo    - La contraseña (tu_password_aqui)
    echo    - El nombre de la base de datos si es diferente
    echo.
    echo 3. Ejecuta el sistema:
    echo    python run.py
    echo.
    echo Para más información, lee: CAMBIO_BASE_DATOS.md
    echo ========================================
) else (
    echo.
    echo [ERROR] No se pudo crear el archivo .env
    echo Verifica que existe el archivo .env.example
)

echo.
pause
