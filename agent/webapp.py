import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from agent import SmartQueryAgent, load_records
from openai_client import OpenAIQueryPlanner


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


class QueryHandler(BaseHTTPRequestHandler):
    agent: SmartQueryAgent = None  # type: ignore[assignment]
    data_file: str = ""
    planner: OpenAIQueryPlanner = None  # type: ignore[assignment]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self._serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        if parsed.path == "/app.js":
            return self._serve_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
        if parsed.path == "/styles.css":
            return self._serve_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
        if parsed.path == "/api/meta":
            return self._send_json(
                {
                    "fields": self.agent.fields,
                    "data_file": self.data_file,
                    "row_count": len(self.agent.records),
                    "openai_enabled": self.planner.is_enabled,
                    "openai_model": self.planner.model,
                }
            )
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/query":
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return self._send_json({"error": "请求体不是合法 JSON。"}, status=HTTPStatus.BAD_REQUEST)

        query = str(payload.get("query", "")).strip()
        if not query:
            return self._send_json({"error": "query 不能为空。"}, status=HTTPStatus.BAD_REQUEST)

        return self._send_json(self.agent.ask(query))

    def log_message(self, format: str, *args) -> None:
        return

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="聊天式数据查询 Web 应用")
    parser.add_argument("--data", default="data/sample_sales.json", help="CSV 或 JSON 数据文件路径")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", default=8000, type=int, help="端口")
    parser.add_argument("--openai-model", default=None, help="可选，指定 OpenAI 模型")
    args = parser.parse_args()

    records = load_records(args.data)
    planner = OpenAIQueryPlanner(model=args.openai_model)
    agent = SmartQueryAgent(records, planner=planner)
    data_file = str(Path(args.data).resolve())

    class AppHandler(QueryHandler):
        pass

    AppHandler.agent = agent
    AppHandler.data_file = data_file
    AppHandler.planner = planner

    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Web UI 已启动: http://{args.host}:{args.port}")
    print(f"当前数据源: {data_file}")
    if planner.is_enabled:
        print(f"OpenAI 已启用，模型: {planner.model}")
    else:
        print("OpenAI 未启用，将使用本地规则解析。")
    server.serve_forever()


if __name__ == "__main__":
    main()
