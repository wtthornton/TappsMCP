# Model Optimization Patterns

## Overview

This guide covers model optimization patterns for AI/ML models, including
quantization, pruning, knowledge distillation, inference optimization,
serving strategies, and hardware-specific considerations. These techniques
reduce latency, memory usage, and compute cost for production deployments.

## Quantization

### Post-Training Quantization (PTQ)

Reduce precision after training without retraining:

```python
import torch

def quantize_dynamic(model: torch.nn.Module) -> torch.nn.Module:
    """Apply dynamic quantization to linear layers."""
    quantized = torch.quantization.quantize_dynamic(
        model,
        {torch.nn.Linear},
        dtype=torch.qint8,
    )
    return quantized
```

### Precision Levels

| Format | Size | Speedup | Accuracy Impact |
|---|---|---|---|
| FP32 | 4 bytes | Baseline | None |
| FP16 | 2 bytes | ~2x | Minimal |
| BF16 | 2 bytes | ~2x | Minimal (better range) |
| INT8 | 1 byte | ~4x | Small (< 1% drop) |
| INT4 | 0.5 bytes | ~8x | Moderate (1-3% drop) |

### NNCF Quantization

```python
import nncf

def quantize_with_calibration(model, data_loader):
    """Quantize model with calibration dataset for better accuracy."""
    calibration_dataset = nncf.Dataset(data_loader)
    quantized_model = nncf.quantize(
        model,
        calibration_dataset,
        preset=nncf.QuantizationPreset.MIXED,
    )
    return quantized_model
```

### GGUF Quantization for LLMs

For large language models, GGUF format enables efficient quantization:

```python
# Using llama.cpp for quantization
# Convert to GGUF format
# python convert.py model_dir --outtype f16

# Quantize to Q4_K_M (good balance of quality and size)
# quantize model.gguf model-q4_k_m.gguf Q4_K_M
```

| GGUF Type | Bits | Quality | Use Case |
|---|---|---|---|
| Q2_K | ~3 | Low | Minimal hardware |
| Q4_K_M | ~4.8 | Good | Balanced default |
| Q5_K_M | ~5.7 | Very good | Quality-focused |
| Q8_0 | 8 | Excellent | Near-original |

## Pruning

### Magnitude-Based Pruning

Remove weights with the smallest magnitudes:

```python
import torch
from torch.nn.utils import prune

def prune_model(model: torch.nn.Module, amount: float = 0.3) -> None:
    """Prune 30% of weights by magnitude across all linear layers."""
    for name, module in model.named_modules():
        if isinstance(module, torch.nn.Linear):
            prune.l1_unstructured(module, name="weight", amount=amount)


def finalize_pruning(model: torch.nn.Module) -> None:
    """Make pruning permanent by removing reparameterization."""
    for name, module in model.named_modules():
        if isinstance(module, torch.nn.Linear):
            prune.remove(module, "weight")
```

### Structured Pruning

Remove entire neurons or channels for hardware-efficient speedup:

```python
def structured_prune(model: torch.nn.Module, amount: float = 0.2) -> None:
    """Prune entire output channels from conv layers."""
    for name, module in model.named_modules():
        if isinstance(module, torch.nn.Conv2d):
            prune.ln_structured(
                module, name="weight", amount=amount, n=2, dim=0
            )
```

### Gradual Pruning Schedule

```python
def gradual_pruning_schedule(
    initial_sparsity: float,
    final_sparsity: float,
    total_steps: int,
    current_step: int,
) -> float:
    """Calculate sparsity at current step using cubic schedule."""
    if current_step >= total_steps:
        return final_sparsity
    progress = current_step / total_steps
    sparsity = final_sparsity + (initial_sparsity - final_sparsity) * (
        1 - progress
    ) ** 3
    return sparsity
```

## Knowledge Distillation

### Standard Distillation

Train a smaller student model to mimic a larger teacher:

```python
import torch
import torch.nn.functional as F

def distillation_loss(
    student_logits: torch.Tensor,
    teacher_logits: torch.Tensor,
    labels: torch.Tensor,
    temperature: float = 4.0,
    alpha: float = 0.7,
) -> torch.Tensor:
    """Compute distillation loss combining soft and hard targets."""
    soft_loss = F.kl_div(
        F.log_softmax(student_logits / temperature, dim=-1),
        F.softmax(teacher_logits / temperature, dim=-1),
        reduction="batchmean",
    ) * (temperature ** 2)

    hard_loss = F.cross_entropy(student_logits, labels)

    return alpha * soft_loss + (1 - alpha) * hard_loss
```

### Training Loop

```python
def train_student(
    teacher: torch.nn.Module,
    student: torch.nn.Module,
    train_loader: torch.utils.data.DataLoader,
    optimizer: torch.optim.Optimizer,
    epochs: int = 10,
) -> None:
    """Train student model with knowledge distillation."""
    teacher.eval()
    student.train()

    for epoch in range(epochs):
        total_loss = 0.0
        for batch_x, batch_y in train_loader:
            with torch.no_grad():
                teacher_logits = teacher(batch_x)

            student_logits = student(batch_x)
            loss = distillation_loss(student_logits, teacher_logits, batch_y)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
```

## Inference Optimization

### Batch Processing

```python
import torch

def batch_inference(
    model: torch.nn.Module,
    data: list[torch.Tensor],
    batch_size: int = 32,
) -> list[torch.Tensor]:
    """Process data in batches for better GPU utilization."""
    model.eval()
    results = []

    with torch.no_grad():
        for i in range(0, len(data), batch_size):
            batch = torch.stack(data[i:i + batch_size])
            output = model(batch)
            results.extend(output.unbind(0))

    return results
```

### Model Compilation (PyTorch 2.x)

```python
import torch

def compile_model(model: torch.nn.Module) -> torch.nn.Module:
    """Compile model for faster inference with torch.compile."""
    compiled = torch.compile(
        model,
        mode="reduce-overhead",  # best for inference
        fullgraph=True,
    )
    return compiled
```

### ONNX Export for Cross-Platform Inference

```python
import torch

def export_to_onnx(
    model: torch.nn.Module,
    sample_input: torch.Tensor,
    output_path: str,
) -> None:
    """Export model to ONNX format for cross-platform inference."""
    torch.onnx.export(
        model,
        sample_input,
        output_path,
        opset_version=17,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch_size"},
            "output": {0: "batch_size"},
        },
    )
```

### Async Inference Pipeline

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=4)

async def async_inference(model, data: list) -> list:
    """Run inference in a thread pool for async compatibility."""
    loop = asyncio.get_event_loop()

    def _sync_infer():
        return [model.predict(item) for item in data]

    return await loop.run_in_executor(_executor, _sync_infer)
```

## Model Caching and Loading

### Lazy Model Loading

```python
from functools import lru_cache

@lru_cache(maxsize=4)
def load_model(model_name: str):
    """Load and cache model to avoid repeated disk I/O."""
    import torch
    model = torch.load(f"models/{model_name}.pt", weights_only=True)
    model.eval()
    return model
```

### Memory-Mapped Loading

```python
import torch

def load_large_model(path: str) -> torch.nn.Module:
    """Load a large model with memory mapping for reduced RAM usage."""
    model = torch.load(
        path,
        map_location="cpu",
        mmap=True,
        weights_only=True,
    )
    return model
```

## Hardware-Specific Optimization

### GPU Optimization

- Use mixed precision (FP16/BF16) for training and inference
- Enable TF32 on Ampere+ GPUs for faster FP32 operations
- Use CUDA graphs for reduced kernel launch overhead
- Pin memory for faster CPU-to-GPU transfers

### CPU Optimization

- Use Intel MKL or OpenBLAS for linear algebra
- Enable multi-threading with OMP_NUM_THREADS
- Use INT8 quantization for CPU inference
- Consider ONNX Runtime for optimized CPU execution

### Apple Silicon (MPS)

```python
import torch

device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
model = model.to(device)
```

## Serving Optimization

### Model Serving Checklist

1. Quantize to INT8 or FP16 for inference
2. Compile model with torch.compile or export to ONNX
3. Use batch processing for throughput
4. Implement request queuing for GPU utilization
5. Add model warmup on server startup
6. Monitor latency percentiles (p50, p95, p99)

### Warmup Strategy

```python
import torch

def warmup_model(model: torch.nn.Module, input_shape: tuple) -> None:
    """Run dummy inference to warm up CUDA kernels and JIT."""
    model.eval()
    dummy = torch.randn(*input_shape)
    with torch.no_grad():
        for _ in range(3):
            model(dummy)
```

## Anti-Patterns

### Premature Optimization

Do not optimize before profiling. Measure latency and memory usage first,
then target the bottleneck.

### Over-Quantization

INT4 quantization can degrade model quality significantly. Always validate
accuracy after quantization on a representative test set.

### Ignoring Batch Size

Single-item inference wastes GPU compute. Always batch requests when possible.

## Quick Reference

| Technique | Speedup | Quality Impact | Complexity |
|---|---|---|---|
| FP16 quantization | 2x | Minimal | Low |
| INT8 quantization | 4x | Small | Medium |
| Pruning (30%) | 1.5x | Small | Medium |
| Distillation | 2-10x | Moderate | High |
| torch.compile | 1.5-3x | None | Low |
| ONNX Runtime | 1.5-2x | None | Medium |
| Batching | 2-8x | None | Low |
