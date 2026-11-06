@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1

rem --- Wlasna instancja Px z dluzszym idle (firmowy Px na 3128 ma idle=30 i zrywa
rem --- bezczynne tunele CONNECT podczas dlugiego oczekiwania na model).
rem --- Zmienne ponizej obowiazuja tylko w tym oknie i dla aico; globalne proxy bez zmian.
set "PX_EXE=%ProgramFiles%\px\px.exe"
set "PX_PORT=3130"
set "PX_IDLE=300"
set "PX_PAC=http://rbins.bosch.com/fe.pac"
set "PX_TITLE=aico-px"
set "PX_STARTED=0"

if not exist "%PX_EXE%" (
    echo Nie znaleziono "%PX_EXE%". Popraw PX_EXE w aico.bat.
    pause
    exit /b 1
)

netstat -ano | findstr /r /c:":%PX_PORT% .*LISTENING" >nul
if not errorlevel 1 (
    echo Port %PX_PORT% jest juz zajety - uzywam istniejacego procesu. Sprawdz, czy to Px z idle=%PX_IDLE%.
) else (
    echo Uruchamiam Px na 127.0.0.1:%PX_PORT% z idle=%PX_IDLE% ...
    start "%PX_TITLE%" /min "%PX_EXE%" --port=%PX_PORT% --listen=127.0.0.1 --hostonly=1 --idle=%PX_IDLE% --pac=%PX_PAC% --foreground=1
    set "PX_STARTED=1"
    timeout /t 4 /nobreak >nul
    netstat -ano | findstr /r /c:":%PX_PORT% .*LISTENING" >nul
    if errorlevel 1 (
        echo Px nie nasluchuje na porcie %PX_PORT%. Sprawdz argumenty: "%PX_EXE%" --help
        taskkill /fi "WINDOWTITLE eq %PX_TITLE%" /t /f >nul 2>&1
        pause
        exit /b 1
    )
)

set "HTTP_PROXY=http://127.0.0.1:%PX_PORT%"
set "HTTPS_PROXY=http://127.0.0.1:%PX_PORT%"
set "ALL_PROXY=http://127.0.0.1:%PX_PORT%"
set "NO_PROXY=localhost,127.0.0.1,::1"

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" aico.py
) else (
    python aico.py
)

if "%PX_STARTED%"=="1" (
    taskkill /fi "WINDOWTITLE eq %PX_TITLE%" /t /f >nul 2>&1
)
pause
