#!/usr/bin/env python3

import sys
from pathlib import Path
from wsgiref.simple_server import make_server

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.web import create_app


def main() -> None:
    app = create_app()
    server = make_server("0.0.0.0", 5050, app)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
