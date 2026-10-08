"""Hardware snapshot + per-stage engine registry. Cheap to poll once a second."""
import os
import platform
import threading
import time

import psutil

_lock = threading.Lock()
_engine = {}            # {"transcribe": {...}, "render": {...}, "llm": {...}}
_stage = {"name": None, "since": None}
_nv = {"h": None, "name": None, "tried": False}
psutil.cpu_percent(None)  # prime


def reset():
    with _lock:
        _engine.clear()


def set_engine(kind, **info):
    with _lock:
        info["since"] = time.time()
        _engine[kind] = info


def set_stage(name):
    with _lock:
        _stage.update(name=name, since=time.time())


def get_engine():
    with _lock:
        return {"engines": dict(_engine), "stage": dict(_stage)}


def _cpu_name():
    try:
        if os.name == "nt":
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                               r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
    except Exception:
        pass
    return platform.processor() or "CPU"


_CPU_NAME = _cpu_name()


def _nvml():
    if _nv["tried"]:
        return _nv["h"]
    _nv["tried"] = True
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        n = pynvml.nvmlDeviceGetName(h)
        _nv.update(h=h, name=n.decode() if isinstance(n, bytes) else n)
    except Exception:
        _nv["h"] = None
    return _nv["h"]


def snapshot():
    vm = psutil.virtual_memory()
    out = {
        "cpu": {"name": _CPU_NAME, "percent": psutil.cpu_percent(None),
                "threads": psutil.cpu_count(logical=True)},
        "ram": {"used_gb": round(vm.used / 2**30, 1), "total_gb": round(vm.total / 2**30, 1),
                "percent": vm.percent},
        "gpu": None,
        **get_engine(),
    }
    h = _nvml()
    if h:
        try:
            import pynvml
            u = pynvml.nvmlDeviceGetUtilizationRates(h)
            m = pynvml.nvmlDeviceGetMemoryInfo(h)
            try:
                enc = pynvml.nvmlDeviceGetEncoderUtilization(h)[0]
            except Exception:
                enc = None
            try:
                temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
            except Exception:
                temp = None
            out["gpu"] = {"name": _nv["name"], "percent": u.gpu, "encoder_percent": enc,
                          "vram_used_gb": round(m.used / 2**30, 2),
                          "vram_total_gb": round(m.total / 2**30, 2),
                          "vram_percent": round(m.used / m.total * 100), "temp_c": temp}
        except Exception:
            pass
    return out
