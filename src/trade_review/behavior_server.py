from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .behavior import (
    BUY_QUALITIES,
    EMOTION_SOURCES,
    EMOTIONS,
    PLAN_FOLLOWS,
    POSITION_QUALITIES,
    STOP_EXECUTIONS,
    SYSTEM_FITS,
    diagnose_behavior,
    ensure_annotation_file,
    load_annotations,
    load_closed_trades,
    update_annotation,
    write_behavior_report,
)


PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"


class BehaviorState:
    def __init__(self, trades_path: Path, annotations_path: Path, report_path: Path, imports_dir: Path):
        self.trades_path = trades_path
        self.annotations_path = annotations_path
        self.report_path = report_path
        self.imports_dir = imports_dir

    def load_payload(self) -> dict:
        trades = load_closed_trades(self.trades_path)
        annotations = ensure_annotation_file(trades, self.annotations_path)
        diagnosis = diagnose_behavior(trades, annotations)
        return {
            "source": {
                "trades_path": str(self.trades_path),
                "annotations_path": str(self.annotations_path),
            },
            "choices": {
                "system_fit": SYSTEM_FITS,
                "plan_follow": PLAN_FOLLOWS,
                "emotion_state": EMOTIONS,
                "emotion_sources": EMOTION_SOURCES,
                "buy_quality": BUY_QUALITIES,
                "position_quality": POSITION_QUALITIES,
                "stop_execution": STOP_EXECUTIONS,
            },
            "diagnosis": diagnosis.__dict__,
        }

    def import_delivery_note(self, filename: str, content_base64: str) -> dict:
        safe_name = safe_filename(filename)
        if Path(safe_name).suffix.lower() not in {".xls", ".xlsx", ".csv"}:
            raise ValueError("仅支持 .xls、.xlsx、.csv 交割单文件。")
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        target = unique_path(self.imports_dir / safe_name)
        target.write_bytes(base64.b64decode(content_base64))
        load_closed_trades(target)
        self.trades_path = target
        self.annotations_path = Path("annotations") / f"{target.stem}_annotations.json"
        trades = load_closed_trades(self.trades_path)
        ensure_annotation_file(trades, self.annotations_path)
        return self.load_payload()


def make_handler(state: BehaviorState):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/data":
                self.send_json(state.load_payload())
                return
            if parsed.path == "/api/report":
                trades = load_closed_trades(state.trades_path)
                annotations = ensure_annotation_file(trades, state.annotations_path)
                diagnosis = diagnose_behavior(trades, annotations)
                output = write_behavior_report(diagnosis, state.report_path)
                self.send_json({"ok": True, "path": str(output)})
                return
            path = parsed.path.lstrip("/") or "index.html"
            self.send_static(path)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if parsed.path == "/api/annotation":
                trade_id = str(payload.pop("trade_id"))
                annotation = update_annotation(state.annotations_path, trade_id, payload)
                self.send_json({"ok": True, "annotation": annotation.__dict__})
                return
            if parsed.path == "/api/import":
                try:
                    data = state.import_delivery_note(str(payload["filename"]), str(payload["content_base64"]))
                except Exception as exc:
                    self.send_json({"ok": False, "error": str(exc)}, status=400)
                    return
                self.send_json({"ok": True, **data})
                return
            self.send_error(404)

        def send_static(self, path: str) -> None:
            target = (STATIC_DIR / path).resolve()
            if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists():
                self.send_error(404)
                return
            content = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:
            print(f"{self.address_string()} - {format % args}")

    return Handler


def safe_filename(filename: str) -> str:
    name = Path(filename).name.strip() or "delivery_note.xls"
    stem = Path(name).stem
    suffix = Path(name).suffix
    stem = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", stem, flags=re.UNICODE).strip("._") or "delivery_note"
    return f"{stem}{suffix}"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for idx in range(1, 1000):
        candidate = path.with_name(f"{path.stem}_{idx}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise ValueError("导入文件过多，请清理 imports 目录后重试。")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="启动本地交割单行为诊断 Web 系统")
    parser.add_argument("--trades", default="最近一个月交割单数据.xls", help="交割单路径")
    parser.add_argument("--annotations", default="annotations/trade_annotations.json", help="标注保存路径")
    parser.add_argument("--report", default="reports/behavior_diagnosis.md", help="报告输出路径")
    parser.add_argument("--imports-dir", default="imports", help="导入交割单保存目录")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    args = parser.parse_args(argv)

    state = BehaviorState(Path(args.trades), Path(args.annotations), Path(args.report), Path(args.imports_dir))
    trades = load_closed_trades(state.trades_path)
    ensure_annotation_file(trades, state.annotations_path)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print(f"行为诊断系统已启动: http://{args.host}:{args.port}")
    print(f"交割单: {state.trades_path}")
    print(f"标注文件: {state.annotations_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("已停止。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
