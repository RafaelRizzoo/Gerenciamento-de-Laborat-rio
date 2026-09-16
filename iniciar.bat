@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Gestao de Produtos Quimicos - Tenaris

rem =====================================================================
rem  iniciar.bat - roda o sistema SEM Docker (so com Python).
rem
rem   iniciar.bat            atualiza, prepara e liga o sistema
rem   iniciar.bat backup     salva uma copia do banco nesta pasta
rem   iniciar.bat zerar      APAGA o banco e recomeca com os exemplos
rem
rem  Enquanto esta janela estiver aberta, o sistema esta no ar.
rem  Para desligar: feche a janela (ou Ctrl+C).
rem =====================================================================

set "PY=.venv\Scripts\python.exe"

echo ============================================================
echo   Gestao de Produtos Quimicos - Tenaris
echo ============================================================
echo.

if /i "%~1"=="backup"   goto backup
if /i "%~1"=="zerar"    goto zerar
if /i "%~1"=="exemplos" goto exemplos
if not "%~1"=="" (
    echo Opcao desconhecida: %~1
    echo Use: iniciar.bat [backup^|zerar^|exemplos]
    echo.
    pause
    exit /b 1
)

rem =====================================================================
rem  1. Python instalado?
rem =====================================================================
echo [1/5] Procurando o Python...
set "PYBASE="
py -3 --version >nul 2>&1 && set "PYBASE=py -3"
if not defined PYBASE (
    python --version >nul 2>&1 && set "PYBASE=python"
)
if not defined PYBASE goto instalar_python

for /f "tokens=2" %%v in ('%PYBASE% --version 2^>^&1') do set "PYVER=%%v"
echo       Python !PYVER! encontrado.

rem =====================================================================
rem  2. Codigo atualizado (se a pasta veio de um git clone)
rem =====================================================================
echo.
echo [2/5] Buscando atualizacoes...
if not exist ".git" (
    echo       Pasta sem git - usando o codigo que ja esta aqui.
    goto ambiente
)
where git >nul 2>&1
if errorlevel 1 (
    echo       Git nao instalado - usando o codigo que ja esta aqui.
    goto ambiente
)
git pull --ff-only
if errorlevel 1 (
    echo.
    echo       [AVISO] Nao consegui atualizar pelo git ^(mensagem acima^).
    echo               Seguindo com o codigo que ja esta na pasta.
    echo.
)

rem =====================================================================
rem  3. Ambiente virtual e bibliotecas
rem =====================================================================
:ambiente
echo.
echo [3/5] Preparando as bibliotecas do Python...

if not exist "%PY%" (
    echo       Criando o ambiente virtual ^(.venv^). Demora um pouco na primeira vez.
    %PYBASE% -m venv .venv
    if errorlevel 1 goto erro_venv
)

rem Instala so quando o requirements.txt mudou desde a ultima vez.
set "PRECISA=1"
if exist ".venv\requirements-instalado.txt" (
    fc /b "requirements.txt" ".venv\requirements-instalado.txt" >nul 2>&1
    if not errorlevel 1 set "PRECISA=0"
)

if "!PRECISA!"=="0" (
    echo       Bibliotecas ja instaladas.
) else (
    echo       Instalando/atualizando ^(precisa de internet^)...
    rem o pyodbc so e' necessario com SQL Server; fica de fora
    findstr /v /i "pyodbc" requirements.txt > "%TEMP%\req-tenaris.txt"
    "%PY%" -m pip install --upgrade pip --quiet
    "%PY%" -m pip install -r "%TEMP%\req-tenaris.txt"
    if errorlevel 1 goto erro_pip
    copy /y "requirements.txt" ".venv\requirements-instalado.txt" >nul
    del "%TEMP%\req-tenaris.txt" >nul 2>&1
    echo       Pronto.
)

rem =====================================================================
rem  4. Banco de dados
rem =====================================================================
echo.
echo [4/5] Preparando o banco de dados...
"%PY%" preparar.py
if errorlevel 1 goto erro_banco

rem =====================================================================
rem  5. Subir a aplicacao
rem =====================================================================
echo.
echo [5/5] Ligando o sistema...

rem --- alguem ja esta usando a porta 5001? ------------------------------
set "OCUPADA="
for /f "tokens=5" %%p in ('netstat -ano -p tcp 2^>nul ^| findstr /r /c:":5001 .*LISTENING"') do set "OCUPADA=%%p"
if defined OCUPADA goto porta_ocupada

:subir
echo.
echo ------------------------------------------------------------
echo   Endereco:  http://localhost:5001
echo   Na rede:   http://SEU-IP:5001   ^(veja o IP com  ipconfig^)
echo.
echo   DEIXE ESTA JANELA ABERTA enquanto estiver usando.
echo   Para desligar: feche a janela ou aperte Ctrl+C.
echo ------------------------------------------------------------
echo.

rem abre o navegador alguns segundos depois, quando o servidor ja respondeu
start "" /b cmd /c "ping -n 7 127.0.0.1 >nul & start http://localhost:5001"

"%PY%" main.py

echo.
echo Sistema encerrado.
pause
exit /b 0


rem =====================================================================
rem  Backup do banco
rem =====================================================================
:backup
if not exist "gestao_quimicos.db" (
    echo Nao encontrei o arquivo gestao_quimicos.db nesta pasta.
    echo.
    pause
    exit /b 1
)
call :carimbo
copy /y "gestao_quimicos.db" "backup_quimicos_!CARIMBO!.db" >nul
echo Copia salva nesta pasta: backup_quimicos_!CARIMBO!.db
echo.
pause
exit /b 0


rem =====================================================================
rem  Solicitacoes de exemplo, para demonstracao
rem =====================================================================
:exemplos
if not exist "%PY%" (
    echo Rode o iniciar.bat uma vez antes ^(sem opcao^) para preparar o ambiente.
    echo.
    pause
    exit /b 1
)
echo Criando as solicitacoes de exemplo a partir das FDS reais...
echo.
"%PY%" exemplos_demo.py
echo.
pause
exit /b 0


rem =====================================================================
rem  Zerar o banco
rem =====================================================================
:zerar
echo [ATENCAO] Isto APAGA todos os produtos, documentos e usuarios
echo           cadastrados e recomeca com os dados de exemplo.
echo.
set /p "OK=Digite ZERAR para confirmar: "
if /i not "!OK!"=="ZERAR" (
    echo Cancelado. Nada foi apagado.
    echo.
    pause
    exit /b 0
)
if exist "gestao_quimicos.db" (
    call :carimbo
    copy /y "gestao_quimicos.db" "backup_antes_de_zerar_!CARIMBO!.db" >nul
    del "gestao_quimicos.db"
)
echo Banco apagado ^(uma copia de seguranca ficou nesta pasta^).
echo Rode o iniciar.bat de novo para recriar com os dados de exemplo.
echo.
pause
exit /b 0


rem =====================================================================
rem  A porta 5001 ja esta ocupada
rem =====================================================================
:porta_ocupada
set "QUEM=?"
for /f "tokens=1" %%n in ('tasklist /fi "PID eq !OCUPADA!" /nh 2^>nul') do set "QUEM=%%n"

echo.
echo ------------------------------------------------------------
echo   [ATENCAO] A porta 5001 ja esta em uso.
echo             Programa: !QUEM!   ^(PID !OCUPADA!^)
echo ------------------------------------------------------------
echo.

echo !QUEM! | findstr /i "docker vpnkit wslrelay" >nul
if not errorlevel 1 goto porta_docker

echo !QUEM! | findstr /i "python" >nul
if not errorlevel 1 goto porta_python

echo   Outro programa deste computador esta usando a porta 5001.
echo   Feche esse programa e rode o iniciar.bat de novo.
echo.
pause
exit /b 1

:porta_docker
echo   E' o conteiner do Docker que esta no ar - os dois nao podem
echo   rodar ao mesmo tempo, e cada um tem o seu proprio banco.
echo.
set /p "OK=Parar o conteiner do Docker e continuar sem ele? (S/N): "
if /i not "!OK!"=="S" (
    echo.
    echo   Tudo bem. O sistema ja esta no ar pelo Docker: http://localhost:5001
    echo.
    pause
    exit /b 0
)
docker stop gestao-quimicos >nul 2>&1
if errorlevel 1 (
    echo.
    echo   Nao consegui parar pelo comando. Pare pelo Docker Desktop, na aba
    echo   Containers, no botao de stop do item gestao-quimicos.
    echo.
    pause
    exit /b 1
)
echo   Conteiner parado.
ping -n 3 127.0.0.1 >nul
goto subir

:porta_python
echo   O sistema ja parece estar no ar em outra janela preta.
echo.
set /p "OK=Encerrar aquela e ligar de novo aqui? (S/N): "
if /i not "!OK!"=="S" (
    echo.
    echo   Tudo bem. Abra http://localhost:5001 que ele ja esta funcionando.
    echo.
    pause
    exit /b 0
)
taskkill /pid !OCUPADA! /f >nul 2>&1
ping -n 3 127.0.0.1 >nul
goto subir


rem =====================================================================
rem  Carimbo de data/hora para os nomes de backup
rem =====================================================================
:carimbo
set "CARIMBO="
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmm" 2^>nul') do set "CARIMBO=%%i"
if not defined CARIMBO set "CARIMBO=%RANDOM%"
goto :eof


rem =====================================================================
rem  Erros
rem =====================================================================
:instalar_python
echo.
echo       Python nao encontrado neste computador.
echo.
set /p "OK=Instalar agora automaticamente? (S/N): "
if /i not "!OK!"=="S" goto python_manual
where winget >nul 2>&1
if errorlevel 1 goto python_manual
echo.
echo       Instalando o Python ^(pode pedir confirmacao do Windows^)...
winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
echo.
echo       Instalacao concluida. FECHE esta janela e rode o iniciar.bat
echo       de novo ^(o Windows precisa reconhecer o Python^).
echo.
pause
exit /b 0

:python_manual
echo.
echo       Baixe o Python em: https://www.python.org/downloads/
echo       Na primeira tela do instalador, MARQUE a caixinha
echo       "Add python.exe to PATH" antes de clicar em Install.
echo.
echo       Depois de instalar, rode o iniciar.bat de novo.
echo.
start "" https://www.python.org/downloads/
pause
exit /b 1

:erro_venv
echo.
echo [ERRO] Nao consegui criar o ambiente virtual ^(.venv^).
echo        Apague a pasta .venv, se existir, e tente de novo.
echo.
pause
exit /b 1

:erro_pip
echo.
echo [ERRO] Nao consegui instalar as bibliotecas.
echo        Quase sempre e' falta de internet ou bloqueio do proxy da empresa.
echo        Tente de novo conectada a internet; se persistir, mande esta tela
echo        para o Rafael.
echo.
pause
exit /b 1

:erro_banco
echo.
echo [ERRO] Falha ao preparar o banco de dados ^(mensagem acima^).
echo        Mande esta tela para o Rafael.
echo.
pause
exit /b 1
