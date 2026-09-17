import os
import shutil
from typing import Final


DEFAULT_MEMORY_PER_JOB_GIB: Final = 8


def configured_value(name: str) -> int | None:
    value = os.environ.get(name, "").strip().lower()

    if not value or value == "auto":
        return None

    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer or 'auto'") from error

    if parsed < 1:
        raise ValueError(f"{name} must be at least 1")

    return parsed


def cpu_count() -> int:
    return max(1, os.cpu_count() or 1)


def gpu_capacity() -> tuple[int, int] | None:
    try:
        import torch

        if not torch.cuda.is_available():
            return None

        device_count = torch.cuda.device_count()
        # The transcription code currently selects CUDA device 0, so do not
        # combine memory across GPUs that the model does not use.
        total_memory = torch.cuda.get_device_properties(0).total_memory
        memory_per_job = int(
            os.environ.get(
                "WORKER_MEMORY_PER_JOB_GIB",
                DEFAULT_MEMORY_PER_JOB_GIB,
            )
        )
        if memory_per_job < 1:
            raise ValueError("WORKER_MEMORY_PER_JOB_GIB must be at least 1")

        capacity = max(
            1,
            total_memory // (memory_per_job * 1024**3),
        )
        return device_count, int(capacity)
    except (ImportError, RuntimeError):
        return None


def worker_capacity() -> tuple[int, int, str]:
    processes = configured_value("WORKER_PROCESSES")
    threads = configured_value("WORKER_THREADS")

    configured_max = configured_value("WORKER_MAX_CONCURRENCY")
    gpu = gpu_capacity()
    if gpu:
        device_count, gpu_capacity_value = gpu
        automatic_capacity = min(cpu_count(), gpu_capacity_value)
        automatic_processes = 1
        resource_summary = (
            f"{device_count} GPU(s), up to {gpu_capacity_value} job(s) by VRAM"
        )
    else:
        automatic_capacity = cpu_count()
        automatic_processes = 1
        resource_summary = f"{cpu_count()} CPU(s), no CUDA GPU detected"

    if configured_max:
        automatic_capacity = min(automatic_capacity, configured_max)

    processes = processes or automatic_processes
    threads = threads or max(1, automatic_capacity // processes)

    return processes, threads, resource_summary


def main() -> None:
    processes, threads, resource_summary = worker_capacity()
    print(
        f"Starting Dramatiq with {processes} process(es) and "
        f"{threads} thread(s) per process ({resource_summary})",
        flush=True,
    )

    dramatiq = shutil.which("dramatiq")
    if dramatiq is None:
        raise RuntimeError("The dramatiq executable is not installed")

    os.execv(
        dramatiq,
        [
            dramatiq,
            "app.worker.tasks",
            "--processes",
            str(processes),
            "--threads",
            str(threads),
        ],
    )


if __name__ == "__main__":
    main()
