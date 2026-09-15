"""
SENTINEL-AI: Edge AI Profiler & Quantization Benchmark REST Routes
Exposes Real-Time Pipeline Latency Flamegraphs and Quantization Benchmarking.
"""

from fastapi import APIRouter, Query
from typing import Dict, Any

from backend.ai.profiler import edge_ai_profiler

router = APIRouter(prefix="/api/ai/profile", tags=["Edge AI Profiler & Quantization"])

@router.get("/live")
def get_live_pipeline_profile() -> Dict[str, Any]:
    """Returns measured rolling stopwatch latencies for every perception stage."""
    return edge_ai_profiler.get_live_profile()

@router.post("/benchmark")
def run_quantization_benchmark(iterations: int = Query(default=10, ge=1, le=50)) -> Dict[str, Any]:
    """
    Runs multi-engine comparative quantization benchmark:
    PyTorch FP32 vs ONNX Runtime FP16 vs TensorRT INT8 Quantized.
    """
    return edge_ai_profiler.run_quantization_benchmark(num_iterations=iterations)
