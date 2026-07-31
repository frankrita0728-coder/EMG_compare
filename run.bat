@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo  emg-compare.app (Streamlit)
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [錯誤] 找不到 python，請先安裝 Python 或加入 PATH。
  echo.
  pause
  exit /b 1
)

echo [1/2] 安裝依賴...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [錯誤] pip 安裝失敗。
  pause
  exit /b 1
)

echo.
echo [2/2] 啟動 Streamlit...
echo 瀏覽器會自動開啟；若要停止，在此視窗按 Ctrl+C
echo.

python -m streamlit run streamlit_app.py
if errorlevel 1 (
  echo.
  echo [錯誤] 程式結束異常，錯誤碼 %errorlevel%
  pause
)
