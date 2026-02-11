import http.server
import socketserver
import logging
import sys

# 설정
PORT = 8080

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SERVING] %(message)s',
    stream=sys.stdout
)

class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # 헬스 체크용 응답
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Mervis Service Server is Alive (Dummy Mode)")
        
    def log_message(self, format, *args):
        # 기본 로그 포맷 덮어쓰기
        logging.info("%s - - [%s] %s" %
                     (self.client_address[0],
                      self.log_date_time_string(),
                      format%args))

if __name__ == "__main__":
    try:
        logging.info(f"Starting Dummy Server on port {PORT}...")
        with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
            logging.info("Server is running. Waiting for requests...")
            httpd.serve_forever()
    except Exception as e:
        logging.error(f"Server Error: {e}")