@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo  EMG Compare
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [錯誤] 找不到 python，請先安裝 Python 或加入 PATH。
  echo.
  pause
  exit /b 1
)

echo [1/3] 安裝依賴...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [錯誤] pip 安裝失敗。
  pause
  exit /b 1
)

echo.
echo [2/3] 釋放 8080 埠（若被占用）...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8080" ^| findstr "LISTENING"') do (
  echo 結束舊行程 PID %%p
  taskkill /F /PID %%p >nul 2>&1
)

echo.
echo [3/3] 啟動網頁服務...
echo 開啟後請到： http://127.0.0.1:8080/
echo 若要停止，在此視窗按 Ctrl+C
echo.

start "" "http://127.0.0.1:8080/"
python app.py
if errorlevel 1 (
  echo.
  echo [錯誤] 程式結束異常，錯誤碼 %errorlevel%
  pause
)
