import logging


logger = logging.getLogger("aichatflow")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def with_trace(trace_id: str):
    return {"trace_id": trace_id}
