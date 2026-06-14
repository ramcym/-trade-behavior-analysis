#!/usr/bin/env bash
set -e

export PYTHONPATH=src
TRADE_FILE="data/trades.xls"

if [ -f "data/trades.xls" ]; then
  TRADE_FILE="data/trades.xls"
elif [ -f "data/trades.xlsx" ]; then
  TRADE_FILE="data/trades.xlsx"
elif [ -f "data/trades.csv" ]; then
  TRADE_FILE="data/trades.csv"
else
  TRADE_FILE="examples/trades_template.csv"
fi

echo "Installing dependencies..."
pip install -r requirements.txt

echo
echo "Starting trade behavior diagnosis system..."
echo "Trade file: ${TRADE_FILE}"
echo "Open this URL in your browser: http://127.0.0.1:8765/"
echo

python -m trade_review.behavior_server --trades "${TRADE_FILE}" --port 8765
