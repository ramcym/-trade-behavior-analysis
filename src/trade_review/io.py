from __future__ import annotations

import re
from datetime import datetime, time
from pathlib import Path
from io import StringIO

import pandas as pd

from .models import IntradayPoint, Trade


TRADE_COLUMN_ALIASES = {
    "date": ["交易日期", "成交日期", "日期", "发生日期", "date", "trade_date"],
    "time": ["成交时间", "交易时间", "时间", "发生时间", "time", "trade_time"],
    "code": ["证券代码", "股票代码", "代码", "证券编号", "code", "symbol", "stock_code"],
    "name": ["证券名称", "股票名称", "名称", "name", "stock_name"],
    "side": ["买卖方向", "买卖标志", "操作", "业务名称", "交易类别", "side", "direction", "action"],
    "price": ["成交价格", "成交价", "价格", "成交均价", "price", "trade_price"],
    "quantity": ["成交数量", "成交股数", "数量", "成交量", "quantity", "qty", "volume"],
    "amount": ["成交金额", "金额", "发生金额", "amount", "trade_amount"],
}

INTRADAY_COLUMN_ALIASES = {
    "datetime": ["日期时间", "时间戳", "datetime"],
    "date": ["日期", "交易日期", "date"],
    "time": ["时间", "成交时间", "分时", "time", "trade_time"],
    "price": ["价格", "成交价", "最新价", "收盘", "price", "close"],
    "volume": ["成交量", "数量", "成交手数", "volume", "qty"],
    "amount": ["成交金额", "金额", "amount"],
    "side": ["方向", "买卖方向", "性质", "side"],
}


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        try:
            return pd.read_excel(path)
        except Exception:
            return read_delimited_export(path)
    if path.suffix.lower() == ".csv":
        return read_csv_with_fallback(path)
    raise ValueError(f"不支持的文件类型: {path}")


def read_csv_with_fallback(path: Path) -> pd.DataFrame:
    for encoding in ["utf-8-sig", "gb18030", "gbk"]:
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, encoding="utf-8-sig", errors="replace")


def read_delimited_export(path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    for encoding in ["utf-8-sig", "gb18030", "gbk"]:
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    first_line = text.splitlines()[0] if text.splitlines() else ""
    sep = "\t" if "\t" in first_line else ","
    return pd.read_csv(StringIO(text), sep=sep)


def normalize_code(value: object) -> str:
    text = str(value).strip()
    text = re.sub(r"\.0$", "", text)
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 6:
        return digits[-6:]
    return digits.zfill(6) if digits else text


def load_trades(path: str | Path) -> list[Trade]:
    df = read_table(path)
    mapping = resolve_columns(df.columns, TRADE_COLUMN_ALIASES)
    required = ["date", "code", "side", "price"]
    missing = [key for key in required if key not in mapping]
    if missing:
        raise ValueError(f"交割单缺少必要字段: {', '.join(missing)}")

    trades: list[Trade] = []
    for _, row in df.iterrows():
        side = str(row[mapping["side"]]).strip()
        if not is_buy_side(side):
            continue
        trade_dt = parse_trade_datetime(
            row[mapping["date"]],
            row[mapping["time"]] if "time" in mapping else None,
        )
        trades.append(
            Trade(
                trade_dt=trade_dt,
                code=normalize_code(row[mapping["code"]]),
                name=str(row[mapping["name"]]).strip() if "name" in mapping else "",
                side=side,
                price=float_or_zero(row[mapping["price"]]),
                quantity=float_or_zero(row[mapping["quantity"]]) if "quantity" in mapping else 0.0,
                amount=float_or_zero(row[mapping["amount"]]) if "amount" in mapping else 0.0,
                raw=row.to_dict(),
            )
        )
    return trades


def load_intraday(path: str | Path, default_date: datetime | None = None) -> list[IntradayPoint]:
    df = read_table(path)
    mapping = resolve_columns(df.columns, INTRADAY_COLUMN_ALIASES)
    if "price" not in mapping:
        raise ValueError(f"分时文件缺少价格字段: {path}")
    if "datetime" not in mapping and "time" not in mapping:
        raise ValueError(f"分时文件缺少时间字段: {path}")

    points: list[IntradayPoint] = []
    for _, row in df.iterrows():
        ts = parse_intraday_datetime(row, mapping, default_date)
        points.append(
            IntradayPoint(
                ts=ts,
                price=float_or_zero(row[mapping["price"]]),
                volume=float_or_zero(row[mapping["volume"]]) if "volume" in mapping else 0.0,
                amount=float_or_zero(row[mapping["amount"]]) if "amount" in mapping else 0.0,
                side=str(row[mapping["side"]]).strip() if "side" in mapping else "",
            )
        )
    return sorted(points, key=lambda item: item.ts)


def resolve_columns(columns: pd.Index, aliases: dict[str, list[str]]) -> dict[str, str]:
    normalized = {normalize_label(column): column for column in columns}
    result: dict[str, str] = {}
    for key, names in aliases.items():
        for name in names:
            label = normalize_label(name)
            if label in normalized:
                result[key] = normalized[label]
                break
    return result


def find_data_file(directory: str | Path | None, code: str, trade_dt: datetime, prefix: str = "") -> Path | None:
    if not directory:
        return None
    directory = Path(directory)
    if not directory.exists():
        return None
    date_text = trade_dt.strftime("%Y%m%d")
    candidates = []
    for path in directory.glob("*"):
        if path.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
            continue
        name = path.stem
        if prefix and prefix not in name:
            continue
        if code in name and date_text in name:
            candidates.append(path)
    return sorted(candidates)[0] if candidates else None


def is_buy_side(side: str) -> bool:
    lowered = side.lower()
    return (any(token in side for token in ["买", "证券买入", "担保品买入"]) or lowered in {"buy", "b"}) and "卖" not in side


def normalize_label(value: object) -> str:
    return re.sub(r"[\s_（）()\-]+", "", str(value).strip().lower())


def float_or_zero(value: object) -> float:
    if pd.isna(value):
        return 0.0
    text = str(value).replace(",", "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_trade_datetime(date_value: object, time_value: object | None) -> datetime:
    date_part = parse_trade_date(date_value)
    if time_value is None or pd.isna(time_value):
        return datetime.combine(date_part, time(9, 30))
    if isinstance(time_value, datetime):
        return datetime.combine(date_part, time_value.time())
    text = str(time_value).strip()
    if re.fullmatch(r"\d{6}", text):
        text = f"{text[:2]}:{text[2:4]}:{text[4:]}"
    parsed_time = pd.to_datetime(text).time()
    return datetime.combine(date_part, parsed_time)


def parse_trade_date(date_value: object):
    if isinstance(date_value, datetime):
        return date_value.date()
    text = str(date_value).strip()
    text = re.sub(r"\.0$", "", text)
    if re.fullmatch(r"\d{8}", text):
        return datetime.strptime(text, "%Y%m%d").date()
    return pd.to_datetime(date_value).date()


def parse_intraday_datetime(row: pd.Series, mapping: dict[str, str], default_date: datetime | None) -> datetime:
    if "datetime" in mapping:
        value = row[mapping["datetime"]]
        parsed = pd.to_datetime(value)
        if default_date and parsed.date().year == 1900:
            return datetime.combine(default_date.date(), parsed.time())
        return parsed.to_pydatetime()
    if "date" in mapping:
        date_value = row[mapping["date"]]
    elif default_date:
        date_value = default_date.date()
    else:
        raise ValueError("分时文件只有时间列时必须提供 default_date")
    return parse_trade_datetime(date_value, row[mapping["time"]])
