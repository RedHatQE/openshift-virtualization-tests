"""CoverPort coverage server — exposes coverage data via HTTP on port 53700."""
import http.server
import threading
import os

COVERAGE_PORT = int(os.environ.get("COVERAGE_PORT", "53700"))


class CoverageHandler(http.server.BaseHTTPRequestHandler):
    """Serves coverage data collected by coverage.py."""

    def do_GET(self):
        if self.path == "/coverage":
            try:
                import coverage
                cov = coverage.Coverage.current()
                if cov:
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".lcov", delete=False) as f:
                        cov.lcov_report(outfile=f.name)
                        data = open(f.name).read()
                        os.unlink(f.name)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(data.encode())
                    return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(f"Error: {e}".encode())
                return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"CoverPort coverage server ready")

    def log_message(self, format, *args):
        pass  # Suppress request logs


def start():
    """Start coverage server in a background thread."""
    server = http.server.HTTPServer(("0.0.0.0", COVERAGE_PORT), CoverageHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


# Auto-start when imported
start()
