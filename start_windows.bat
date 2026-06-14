@echo off
setlocal

set PYTHONPATH=src
set TRADE_FILE=data\trades.xls

if exist "data\trades.xls" set TRADE_FILE=data\trades.xls
if not exist "%TRADE_FILE%" if exist "data\trades.xlsx" set TRADE_FILE=data\trades.xlsx
if not exist "%TRADE_FILE%" if exist "data\trades.csv" set TRADE_FILE=data\trades.csv
if not exist "%TRADE_FILE%" set TRADE_FILE=examples\trades_template.csv

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Starting trade behavior diagnosis system...
echo Trade file: %TRADE_FILE%
echo Open this URL in your browser: http://127.0.0.1:8765/
echo.

python -m trade_review.behavior_server --trades "%TRADE_FILE%" --port 8765
pause
