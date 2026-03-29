import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.orchestration.orchestrator import handle_question


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Inventory AI</title>
  <style>
    :root {
      --bg: #f6f8fc;
      --card: #ffffff;
      --line: #e5eaf3;
      --text: #0f172a;
      --muted: #5b6478;
      --accent: #4f46e5;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Inter", "Segoe UI", sans-serif;
      background: radial-gradient(1200px 400px at 90% -10%, #eaf0ff 0%, var(--bg) 60%);
      color: var(--text);
    }
    .wrap {
      max-width: 900px;
      margin: 0 auto;
      padding: 28px 16px 44px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
      padding: 18px;
    }
    h1 {
      margin: 0;
      font-size: 2rem;
      letter-spacing: -0.02em;
    }
    .sub {
      margin-top: 8px;
      color: var(--muted);
      font-size: 0.97rem;
    }
    .query {
      margin-top: 14px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
    }
    input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px 14px;
      font-size: 15px;
      outline: none;
      color: var(--text);
      background: #fff;
    }
    input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.15);
    }
    button {
      border: 0;
      border-radius: 12px;
      background: var(--accent);
      color: #fff;
      font-weight: 600;
      padding: 12px 16px;
      cursor: pointer;
    }
    button:hover { background: #4338ca; }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    .result {
      margin-top: 14px;
      display: none;
    }
    .pill {
      display: inline-block;
      margin-bottom: 10px;
      border-radius: 999px;
      border: 1px solid #cfd5ff;
      background: #eef0ff;
      color: #3730a3;
      padding: 4px 10px;
      font-size: 13px;
      font-weight: 700;
    }
    .answer {
      white-space: pre-wrap;
      line-height: 1.5;
      margin-bottom: 12px;
    }
    details {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 8px 10px;
      background: #fafbff;
      margin-top: 8px;
    }
    summary {
      cursor: pointer;
      font-weight: 600;
      color: #1f2a44;
    }
    pre {
      overflow: auto;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      margin: 8px 0 0;
      font-size: 12px;
    }
    .err {
      margin-top: 10px;
      color: #9f1239;
      background: #fff1f5;
      border: 1px solid #fecdd3;
      border-radius: 10px;
      padding: 10px;
      display: none;
      white-space: pre-wrap;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Inventory AI</h1>
      <div class="sub">Minimal interface for SQL + RAG + HYBRID questions.</div>

      <div class="query">
        <input id="question" placeholder="Ask a question..." />
        <button id="ask">Ask</button>
      </div>

      <div id="error" class="err"></div>

      <div id="result" class="result">
        <div id="route" class="pill">Route: -</div>
        <div id="answer" class="answer"></div>

        <details>
          <summary>SQL</summary>
          <pre id="sql">-</pre>
        </details>
        <details>
          <summary>JSON Result</summary>
          <pre id="json">-</pre>
        </details>
      </div>
    </div>
  </div>

  <script>
    const askBtn = document.getElementById("ask");
    const input = document.getElementById("question");
    const errorEl = document.getElementById("error");
    const resultEl = document.getElementById("result");
    const routeEl = document.getElementById("route");
    const answerEl = document.getElementById("answer");
    const sqlEl = document.getElementById("sql");
    const jsonEl = document.getElementById("json");

    function setBusy(flag) {
      askBtn.disabled = flag;
      askBtn.textContent = flag ? "Working..." : "Ask";
    }

    function showError(message) {
      errorEl.style.display = "block";
      errorEl.textContent = message;
    }

    function clearError() {
      errorEl.style.display = "none";
      errorEl.textContent = "";
    }

    async function ask() {
      const question = input.value.trim();
      if (!question) return;
      setBusy(true);
      clearError();
      try {
        const res = await fetch("/api/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Request failed");

        resultEl.style.display = "block";
        routeEl.textContent = "Route: " + (data.route || "-");
        answerEl.textContent = data.answer || "-";
        sqlEl.textContent = data.sql || "-";
        jsonEl.textContent = JSON.stringify(data.result || {}, null, 2);
      } catch (err) {
        showError(err.message || String(err));
      } finally {
        setBusy(false);
      }
    }

    askBtn.addEventListener("click", ask);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") ask();
    });
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" or self.path.startswith("/?"):
            data = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/ask":
            self._send_json({"error": "Not found"}, status=404)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length) if content_length > 0 else b""
            payload = json.loads(body.decode("utf-8")) if body else {}
            question = str(payload.get("question", "")).strip()
            if not question:
                self._send_json({"error": "Missing question"}, status=400)
                return
            result = handle_question(question)
            self._send_json(result, status=200)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Inventory AI running on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

