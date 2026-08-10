import http.server
import socketserver
import urllib.error
import urllib.request
from pathlib import Path


PORT = 8080
BACKEND_URL = "http://localhost:8000"

# The frontend directory is two levels above this script.
STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            directory=str(STATIC_DIR),
            **kwargs,
        )

    def do_GET(self):
        if self.path.startswith("/api/"):
            self.proxy_request("GET")
            return

        super().do_GET()

    def do_POST(self):
        self.proxy_request("POST")

    def proxy_request(self, method: str):
        """Forward API requests to the backend server."""

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else None

        # Remove the /api prefix before sending the request to the backend.
        backend_path = self.path[len("/api"):]
        request = urllib.request.Request(
            BACKEND_URL + backend_path,
            data=body,
            method=method,
        )

        # Forward the headers that the backend needs.
        for header in ("Authorization", "Content-Type"):
            value = self.headers.get(header)
            if value:
                request.add_header(header, value)

        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                self.send_response(response.status)

                content_type = response.headers.get("Content-Type")
                if content_type:
                    self.send_header("Content-Type", content_type)

                self.end_headers()
                self.wfile.write(response.read())

        except urllib.error.HTTPError as error:
            # Pass the backend's error response back to the browser.
            response_body = error.read()

            self.send_response(error.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response_body)

        except Exception as error:
            self.send_error(
                502,
                f"Backend server is unavailable: {error}",
            )

    def log_message(self, *args):
        # Disable the default HTTP server logs.
        pass


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True

    with socketserver.TCPServer(("", PORT), Handler) as server:
        print(f"Frontend running at http://localhost:{PORT}")
        print(f"API requests are forwarded to {BACKEND_URL}")

        server.serve_forever()