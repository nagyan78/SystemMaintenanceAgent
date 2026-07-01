"""Small local web front end for uploading and diagnosing Excel files."""

from __future__ import annotations

import argparse
import socket
import tempfile
import threading
import webbrowser
import zipfile
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .data_loader import load_product_data
from .report_generator import generate_html_dashboard
from .structure_checker import check_structure_issues
from .tree_analyzer import summarize_tree
from .tree_builder import add_tree_fields


MAX_UPLOAD_BYTES = 80 * 1024 * 1024


class UploadedFile:
    """A parsed uploaded file payload."""

    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self.content = content


class UploadDiagnosisHandler(BaseHTTPRequestHandler):
    """Serve a drag-and-drop upload page and return diagnosis results."""

    server_version = "StandardProductDiagnosis/0.3"

    def do_GET(self) -> None:
        """Render the upload page or health endpoint."""

        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_html(_render_upload_page())
            return
        if path == "/health":
            self._send_text("ok")
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Page not found")

    def do_POST(self) -> None:
        """Accept an Excel upload, run diagnosis, and return an HTML dashboard."""

        path = urlparse(self.path).path
        if path != "/analyze":
            self.send_error(HTTPStatus.NOT_FOUND, "Page not found")
            return

        try:
            upload = self._read_uploaded_file()
            html = _diagnose_uploaded_file(upload.filename, upload.content)
            self._send_html(html)
        except Exception as exc:  # noqa: BLE001 - local user-facing error page.
            self._send_html(_render_error_page(str(exc)), status=HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: object) -> None:
        """Keep server logs compact in the launch window."""

        print(f"{self.address_string()} - {format % args}")

    def _read_uploaded_file(self) -> UploadedFile:
        """Read and parse the uploaded multipart file payload."""

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise ValueError("没有收到上传文件。")
        if content_length > MAX_UPLOAD_BYTES:
            raise ValueError("上传文件过大，请使用 80MB 以内的 .xlsx 文件。")

        content_type = self.headers.get("Content-Type", "")
        boundary = _extract_boundary(content_type)
        body = self.rfile.read(content_length)
        upload = _parse_multipart_file(body, boundary)
        if not upload.content:
            raise ValueError("上传文件内容为空。")
        if not _is_xlsx_content(upload.content):
            raise ValueError(
                "当前文件不是标准 .xlsx 工作簿。请在 Excel/WPS 中选择“另存为”，保存成 .xlsx 后再上传。"
            )
        return upload

    def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        """Send a UTF-8 HTML response."""

        payload = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, text: str) -> None:
        """Send a UTF-8 plain-text response."""

        payload = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def run_server(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    """Start the local upload web server."""

    actual_port = _find_available_port(host, port)
    server = ThreadingHTTPServer((host, actual_port), UploadDiagnosisHandler)
    url = f"http://{host}:{actual_port}/"
    print("=" * 60)
    print("标准产品体系上传诊断前端已启动")
    print(f"浏览器地址: {url}")
    print("如果浏览器没有自动打开，请复制上面的地址到浏览器。")
    print("关闭这个窗口即可停止服务。")
    print("=" * 60)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    server.serve_forever()


def main() -> None:
    """Parse command-line arguments and run the local web server."""

    parser = argparse.ArgumentParser(description="标准产品体系上传诊断前端")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    parser.add_argument("--open-browser", action="store_true", help="启动后自动打开浏览器")
    args = parser.parse_args()
    run_server(args.host, args.port, args.open_browser)


def _diagnose_uploaded_file(filename: str, content: bytes) -> str:
    """Persist an uploaded file temporarily and return the diagnosis dashboard."""

    temp_path = _write_temp_excel(content)
    try:
        raw_df = load_product_data(str(temp_path))
        tree_df = add_tree_fields(raw_df)
        summary = summarize_tree(tree_df)
        issues = check_structure_issues(tree_df)
        dashboard = generate_html_dashboard(summary, issues)
        return _inject_upload_actions(dashboard, filename)
    finally:
        temp_path.unlink(missing_ok=True)


def _find_available_port(host: str, preferred_port: int) -> int:
    """Return the preferred port if available, otherwise find a nearby free port."""

    for port in range(preferred_port, preferred_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((host, port)) != 0:
                return port
    raise OSError(f"端口 {preferred_port}-{preferred_port + 19} 都被占用，请关闭其他服务后重试。")


def _write_temp_excel(content: bytes) -> Path:
    """Write uploaded Excel bytes to a temporary file for pandas/openpyxl."""

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as file:
        file.write(content)
        return Path(file.name)


def _is_xlsx_content(content: bytes) -> bool:
    """Return True when uploaded bytes look like an XLSX workbook."""

    if not content.startswith(b"PK"):
        return False
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as file:
            file.write(content)
            temp_path = Path(file.name)
        try:
            with zipfile.ZipFile(temp_path) as archive:
                names = set(archive.namelist())
                return "[Content_Types].xml" in names and "xl/workbook.xml" in names
        finally:
            temp_path.unlink(missing_ok=True)
    except zipfile.BadZipFile:
        return False


def _extract_boundary(content_type: str) -> bytes:
    """Extract a multipart boundary from the Content-Type header."""

    marker = "boundary="
    if marker not in content_type:
        raise ValueError("上传请求格式不正确，缺少 multipart boundary。")
    boundary = content_type.split(marker, 1)[1].strip()
    if boundary.startswith('"') and boundary.endswith('"'):
        boundary = boundary[1:-1]
    return boundary.encode("utf-8")


def _parse_multipart_file(body: bytes, boundary: bytes) -> UploadedFile:
    """Parse the first file field named ``file`` from a multipart payload."""

    delimiter = b"--" + boundary
    for raw_part in body.split(delimiter):
        part = raw_part.strip(b"\r\n")
        if not part or part == b"--" or b"\r\n\r\n" not in part:
            continue

        raw_headers, content = part.split(b"\r\n\r\n", 1)
        headers = raw_headers.decode("utf-8", errors="replace")
        if 'name="file"' not in headers:
            continue

        filename = _extract_filename(headers)
        return UploadedFile(filename=filename, content=content.rstrip(b"\r\n"))

    raise ValueError("没有找到名为 file 的上传字段。")


def _extract_filename(headers: str) -> str:
    """Extract and sanitize the uploaded filename from multipart headers."""

    if "filename*=" in headers:
        encoded = headers.split("filename*=", 1)[1].split(";", 1)[0].strip().strip('"')
        if "''" in encoded:
            encoded = encoded.split("''", 1)[1]
        filename = Path(unquote(encoded)).name
    elif "filename=" in headers:
        raw_filename = headers.split("filename=", 1)[1].split(";", 1)[0].strip().strip('"')
        filename = Path(raw_filename).name
    else:
        raise ValueError("上传字段缺少文件名。")

    if not filename:
        raise ValueError("上传文件名为空。")
    return filename


def _inject_upload_actions(dashboard: str, filename: str) -> str:
    """Add a small action bar to the generated dashboard page."""

    action_bar = f"""
  <div class="upload-actions">
    <a href="/">重新上传</a>
    <span>当前文件：{escape(filename)}</span>
  </div>
  <style>
    .upload-actions {{
      display: flex;
      gap: 14px;
      align-items: center;
      padding: 12px 32px;
      background: #ffffff;
      border-bottom: 1px solid #dfe5ef;
      color: #677287;
      font-size: 14px;
    }}
    .upload-actions a {{
      color: #1769aa;
      font-weight: 700;
      text-decoration: none;
    }}
  </style>
"""
    return dashboard.replace("<main>", f"{action_bar}\n  <main>", 1)


def _render_upload_page() -> str:
    """Render the drag-and-drop Excel upload form."""

    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>标准产品体系上传诊断</title>
  <style>
    :root {
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #18202f;
      --muted: #667085;
      --line: #d9e2ef;
      --primary: #1769aa;
      --primary-dark: #124f80;
      --primary-soft: #e7f1fb;
      --success: #147a4a;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: var(--bg);
      color: var(--text);
      font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", Arial, sans-serif;
    }
    main {
      width: min(760px, calc(100vw - 32px));
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 16px 42px rgba(24, 32, 47, 0.1);
      overflow: hidden;
    }
    header {
      padding: 28px 30px;
      background: #16324f;
      color: #ffffff;
    }
    h1 { margin: 0; font-size: 26px; line-height: 1.25; letter-spacing: 0; }
    header p { margin: 10px 0 0; color: #d7e6f3; font-size: 14px; line-height: 1.6; }
    form { display: grid; gap: 18px; padding: 28px 30px 30px; }
    .drop-zone {
      display: grid;
      place-items: center;
      min-height: 240px;
      padding: 28px;
      border: 2px dashed #9fb5ce;
      border-radius: 8px;
      background: #fbfcff;
      text-align: center;
      cursor: pointer;
      outline: none;
      transition: border-color 0.16s ease, background 0.16s ease, transform 0.16s ease;
    }
    .drop-zone:hover, .drop-zone:focus, .drop-zone.is-dragover {
      border-color: var(--primary);
      background: var(--primary-soft);
      transform: translateY(-1px);
    }
    .drop-zone.is-invalid { border-color: var(--danger); background: #fff1f0; }
    .drop-icon {
      width: 58px;
      height: 58px;
      display: grid;
      place-items: center;
      margin: 0 auto 14px;
      border-radius: 50%;
      background: #e8f2fb;
      color: var(--primary);
      font-size: 28px;
      font-weight: 700;
    }
    .drop-title { margin: 0; font-size: 20px; font-weight: 700; color: var(--text); }
    .drop-subtitle { margin: 8px 0 0; color: var(--muted); font-size: 14px; line-height: 1.6; }
    .file-input { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
    .file-meta {
      display: none;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      min-height: 52px;
      padding: 12px 14px;
      border: 1px solid #cde7d8;
      border-radius: 8px;
      background: #f0fbf5;
      color: var(--success);
      font-size: 14px;
    }
    .file-meta.is-visible { display: flex; }
    .file-meta strong { display: block; color: #0b5b36; word-break: break-all; }
    .file-meta span { color: #43785f; }
    .clear-file {
      min-width: 72px;
      height: 34px;
      border: 1px solid #b8dcc8;
      border-radius: 6px;
      background: #ffffff;
      color: #0b5b36;
      cursor: pointer;
    }
    .actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    .submit-button {
      width: fit-content;
      min-width: 136px;
      height: 42px;
      padding: 0 18px;
      border: 0;
      border-radius: 6px;
      background: var(--primary);
      color: #ffffff;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    .submit-button:hover { background: var(--primary-dark); }
    .submit-button:disabled { cursor: not-allowed; background: #a7b4c4; }
    .status { color: var(--muted); font-size: 14px; }
    .status.error { color: var(--danger); }
    .note { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.7; }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>标准产品体系上传诊断</h1>
      <p>把 Excel 文件拖进上传区域，系统会在本地临时读取并生成结构诊断看板。</p>
    </header>
    <form id="uploadForm" action="/analyze" method="post" enctype="multipart/form-data">
      <div id="dropZone" class="drop-zone" tabindex="0" role="button" aria-label="拖入或选择 xlsx 文件">
        <input id="fileInput" class="file-input" type="file" name="file" accept=".xlsx" required>
        <div>
          <div class="drop-icon">↓</div>
          <p class="drop-title">拖拽 .xlsx 文件到这里</p>
          <p class="drop-subtitle">也可以点击这个区域选择文件。请使用 Excel/WPS 另存为的标准 .xlsx 工作簿。</p>
        </div>
      </div>
      <div id="fileMeta" class="file-meta" aria-live="polite">
        <div>
          <strong id="fileName"></strong>
          <span id="fileSize"></span>
        </div>
        <button id="clearFile" class="clear-file" type="button">移除</button>
      </div>
      <div class="actions">
        <button id="submitButton" class="submit-button" type="submit" disabled>开始诊断</button>
        <span id="statusText" class="status">等待上传 Excel 文件</span>
      </div>
      <p class="note">当前首轮只检测父节点缺失、层级过深、节点过宽。上传文件只会被临时读取，不会写回修改。</p>
    </form>
  </main>
  <script>
    const form = document.querySelector("#uploadForm");
    const dropZone = document.querySelector("#dropZone");
    const fileInput = document.querySelector("#fileInput");
    const fileMeta = document.querySelector("#fileMeta");
    const fileName = document.querySelector("#fileName");
    const fileSize = document.querySelector("#fileSize");
    const clearFile = document.querySelector("#clearFile");
    const submitButton = document.querySelector("#submitButton");
    const statusText = document.querySelector("#statusText");

    function formatSize(bytes) {
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
      return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    }

    function setStatus(message, isError = false) {
      statusText.textContent = message;
      statusText.classList.toggle("error", isError);
      dropZone.classList.toggle("is-invalid", isError);
    }

    function setFile(file) {
      if (!file) return;
      if (!file.name.toLowerCase().endsWith(".xlsx")) {
        fileInput.value = "";
        fileMeta.classList.remove("is-visible");
        submitButton.disabled = true;
        setStatus("请选择 Excel/WPS 另存为的 .xlsx 文件", true);
        return;
      }

      const transfer = new DataTransfer();
      transfer.items.add(file);
      fileInput.files = transfer.files;
      fileName.textContent = file.name;
      fileSize.textContent = formatSize(file.size);
      fileMeta.classList.add("is-visible");
      submitButton.disabled = false;
      setStatus("文件已就绪，可以开始诊断");
    }

    dropZone.addEventListener("click", () => fileInput.click());
    dropZone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        fileInput.click();
      }
    });
    fileInput.addEventListener("change", () => setFile(fileInput.files[0]));

    ["dragenter", "dragover"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.add("is-dragover");
        setStatus("松开鼠标即可放入文件");
      });
    });
    ["dragleave", "drop"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.remove("is-dragover");
      });
    });
    dropZone.addEventListener("drop", (event) => {
      setFile(event.dataTransfer.files[0]);
    });

    clearFile.addEventListener("click", () => {
      fileInput.value = "";
      fileMeta.classList.remove("is-visible");
      submitButton.disabled = true;
      setStatus("等待上传 Excel 文件");
    });

    form.addEventListener("submit", () => {
      submitButton.disabled = true;
      submitButton.textContent = "诊断中...";
      setStatus("正在读取并分析文件，请稍等");
    });
  </script>
</body>
</html>"""


def _render_error_page(message: str) -> str:
    """Render a readable upload or analysis error page."""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>诊断失败</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #f4f7fb;
      color: #18202f;
      font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", Arial, sans-serif;
    }}
    main {{
      width: min(680px, calc(100vw - 32px));
      background: #ffffff;
      border: 1px solid #d9e2ef;
      border-radius: 8px;
      padding: 28px;
      box-shadow: 0 16px 42px rgba(24, 32, 47, 0.1);
    }}
    h1 {{ margin: 0 0 12px; font-size: 24px; }}
    p {{ color: #667085; line-height: 1.7; }}
    a {{ color: #1769aa; font-weight: 700; text-decoration: none; }}
  </style>
</head>
<body>
  <main>
    <h1>诊断失败</h1>
    <p>{escape(message)}</p>
    <a href="/">返回重新上传</a>
  </main>
</body>
</html>"""


if __name__ == "__main__":
    main()
