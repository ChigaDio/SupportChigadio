#!/bin/sh
cd "$(dirname "$0")"
(sleep 1; (xdg-open http://localhost:8000/ || open http://localhost:8000/) >/dev/null 2>&1) &
exec python3 server.py "$@"
