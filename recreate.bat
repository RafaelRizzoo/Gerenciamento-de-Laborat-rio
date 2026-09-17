@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Gestao de Produtos Quimicos - Tenaris

rem =====================================================================
rem  recreate.bat - faz tudo o que e' preciso no dia a dia.
rem
rem   recreate.bat            atualiza o codigo e recria o conteiner
rem   recreate.bat parar      para a aplicacao
rem   recreate.bat logs       mostra o que a aplicacao esta fazendo
rem   recreate.bat backup     salva uma copia do banco nesta pasta
rem   recreate.bat zerar      APAGA o banco e comeca do zero (pede confirmacao)
rem =====================================================================

echo ============================================================
echo   Gestao de Produtos Quimicos - Tenaris
echo ============================================================
echo.

rem --- o Docker esta rodando? ------------------------------------------
docker version >nul 2>&1
if errorlevel 1 goto sem_docker
docker info >nul 2>&1
if errorlevel 1 goto sem_docker

rem --- qual acao foi pedida? -------------------------------------------
if /i "%~1"=="parar"  goto parar
if /i "%~1"=="stop"   goto parar
if /i "%~1"=="logs"   goto logs
if /i "%~1"=="backup" goto backup
if /i "%~1"=="zerar"  goto zerar
if not "%~1"=="" (
    echo Opcao desconhecida: %~1
    echo Use: recreate.bat [parar^|logs^|backup^|zerar]
    echo.
    pause
    exit /b 1
)

rem =====================================================================
rem  Fluxo normal: atualizar o codigo e recriar o conteiner
rem =====================================================================

echo [1/4] Buscando atualizacoes do GitHub...
if not exist ".git" (
    echo       Pasta sem git - usando o codigo que ja esta aqui.
    goto construir
)
where git >nul 2>&1
if errorlevel 1 (
    echo       Git nao instalado - usando o codigo que ja esta aqui.
    goto construir
)
git pull --ff-only
if errorlevel 1 (
    echo.
    echo       [AVISO] Nao consegui atualizar pelo git ^(mensagem acima^).
    echo               Seguindo com o codigo que ja esta na pasta.
    echo.
)

:construir
echo.
echo [2/4] Parando o conteiner anterior...
docker compose down

echo.
echo [3/4] Reconstruindo e subindo ^(a primeira vez demora alguns minutos^)...
echo.
docker compose up -d --build
if errorlevel 1 goto erro_subir

echo.
echo [4/4] Esperando a aplicacao responder...
where curl >nul 2>&1
if errorlevel 1 (
    echo       ^(sem curl para conferir - aguardando 10 segundos^)
    timeout /t 10 >nul
    goto pronto
)
set TENTATIVA=0
:esperar
set /a TENTATIVA+=1
curl -s -o nul http://localhost:5001/login >nul 2>&1
if not errorlevel 1 goto pronto
if %TENTATIVA% GEQ 30 goto demorou
timeout /t 2 >nul
goto esperar

:pronto
echo       Aplicacao no ar.
echo.
echo ============================================================
echo   Pronto! Abrindo http://localhost:5001
echo.
echo   Login de administrador:  jusilva@tenaris.com
echo   Senha:                   123456
echo   ^(consulta, FDS e cadastro funcionam sem login^)
echo.
echo   O banco NAO foi apagado - fica guardado fora do conteiner.
echo ============================================================
start "" http://localhost:5001
echo.
echo Para acompanhar o funcionamento: recreate.bat logs
echo.
pause
exit /b 0

:demorou
echo.
echo [AVISO] O conteiner subiu, mas a pagina ainda nao respondeu.
echo         Veja o que aconteceu com: recreate.bat logs
echo.
pause
exit /b 1

rem =====================================================================
rem  Acoes extras
rem =====================================================================

:parar
echo Parando a aplicacao...
docker compose down
echo.
echo Parada. Os dados continuam salvos.
echo Para subir de novo, execute o recreate.bat sem nenhuma opcao.
echo.
pause
exit /b 0

:logs
echo Mostrando o funcionamento da aplicacao.
echo Pressione Ctrl+C ou feche a janela para sair.
echo.
docker compose logs -f
exit /b 0

:backup
for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set HOJE=%%c-%%b-%%a
set DESTINO=backup_quimicos_%HOJE%.db
echo Copiando o banco para %DESTINO% ...
docker compose cp app:/dados/gestao_quimicos.db "%DESTINO%"
if errorlevel 1 (
    echo.
    echo [ERRO] Nao consegui copiar. A aplicacao precisa estar rodando.
    echo.
    pause
    exit /b 1
)
echo.
echo Backup salvo nesta pasta como %DESTINO%
echo.
pause
exit /b 0

:zerar
echo ATENCAO: isto APAGA todos os produtos, documentos e usuarios
echo          cadastrados e recomeca com os dados de exemplo.
echo.
set /p RESPOSTA=Digite APAGAR para confirmar:
if /i not "%RESPOSTA%"=="APAGAR" (
    echo.
    echo Cancelado - nada foi apagado.
    echo.
    pause
    exit /b 0
)
echo.
echo Apagando o banco e recriando do zero...
docker compose down -v
docker compose up -d --build
if errorlevel 1 goto erro_subir
echo.
echo Banco recriado com os dados de exemplo.
timeout /t 5 >nul
start "" http://localhost:5001
echo.
pause
exit /b 0

rem =====================================================================
rem  Erros
rem =====================================================================

:sem_docker
echo [ERRO] O Docker Desktop nao esta rodando.
echo.
echo        1. Abra o Docker Desktop pelo menu Iniciar
echo        2. Espere o icone da baleia parar de piscar
echo        3. Execute este arquivo de novo
echo.
echo        Se ainda nao instalou: https://www.docker.com/products/docker-desktop/
echo.
pause
exit /b 1

:erro_subir
echo.
echo [ERRO] Falhou ao construir ou subir o conteiner.
echo        Copie a mensagem acima e mande para a Julia.
echo.
pause
exit /b 1
