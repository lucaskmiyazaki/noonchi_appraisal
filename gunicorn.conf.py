# gunicorn.conf.py — shared config for all three servers
# Each server overrides `bind` and `workers` via CLI if needed.

import multiprocessing

# gthread worker supports Flask's threading model and SSE streaming correctly
worker_class = "gthread"

# 2 workers × 4 threads = 8 concurrent requests; tune based on CPU/RAM
workers = 2
threads = 4

# Keep connections open for SSE streams (pipeline, upload job)
timeout = 3600
keepalive = 65

# Logging
accesslog = "-"   # stdout (captured by systemd / run_all_servers.sh)
errorlog = "-"
loglevel = "info"

# Security: don't show gunicorn version in Server header
forwarded_allow_ips = "127.0.0.1"
