from backend.tracing.interface import NoOpTracer, Tracer, get_tracer, set_tracer
from backend.tracing.setup import init_tracing

# ``DeepEvalTracer`` is intentionally not re-exported here: importing it pulls in
# ``deepeval`` eagerly, which the no-op path must avoid. Reach it via ``init_tracing``.
__all__ = ["NoOpTracer", "Tracer", "get_tracer", "init_tracing", "set_tracer"]
