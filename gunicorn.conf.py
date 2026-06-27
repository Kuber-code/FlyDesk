"""gunicorn config.

prometheus_client runs in multiprocess mode under gunicorn (each worker is its
own process with its own registry). When a worker exits we mark it dead so its
metric files are reaped and `/metrics` aggregates only live workers.
"""


def child_exit(server, worker):
    try:
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)
    except Exception:  # multiprocess mode not enabled (no PROMETHEUS_MULTIPROC_DIR)
        pass
