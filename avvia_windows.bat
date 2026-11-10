@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creo l'ambiente Python...
  py -m venv .venv
  if errorlevel 1 (
    echo Python non trovato: installa Python 3.11+ e riprova.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -c "import streamlit, pandas" >nul 2>&1
if errorlevel 1 (
  echo Installo Streamlit e le dipendenze...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Installazione non riuscita. Controlla la connessione Internet.
    pause
    exit /b 1
  )
)
echo.
echo Scegli un PIN per l'area Gestione (non usare un PIN personale).
set /p "ADMIN_PIN=PIN amministratore: "
if "%ADMIN_PIN%"=="" (
  echo Il PIN non puo' essere vuoto.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run app.py
pause
