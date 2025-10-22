import torch
import ctypes
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class UltraHighSpeedBridge:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return

        self.lib = None
        self.ctx = None
        self.enabled = False
        self.bandwidth_gbps = 0.0
        self.num_streams = 16
        self.pinned_pool = {}
        self.max_pool_size = 4 * 1024 * 1024 * 1024
        self.pool_sizes = [
            1 * 1024 * 1024,
            10 * 1024 * 1024,
            100 * 1024 * 1024,
            500 * 1024 * 1024,
            1024 * 1024 * 1024,
            2 * 1024 * 1024 * 1024,
        ]
        self.pool_initialized = False
        
        try:
            dll_path = self._find_dll()
            kernel_enabled = os.environ.get('ULTRA_BRIDGE_KERNEL') == '1'
            bridge_enabled = os.environ.get('ULTRA_BRIDGE_ENABLED') == '1'

            if dll_path and os.path.exists(dll_path):
                self.lib = ctypes.CDLL(str(dll_path))

                if kernel_enabled:
                    try:
                        self.lib.ultra_memcpy_async_raw.argtypes = [
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                            ctypes.c_int, ctypes.c_void_p
                        ]
                        self.lib.ultra_memcpy_async_raw.restype = ctypes.c_int

                        self.lib.ultra_get_device_count.restype = ctypes.c_int
                        self.lib.ultra_set_device.argtypes = [ctypes.c_int]
                        self.lib.ultra_set_device.restype = ctypes.c_int
                    except Exception as e:
                        logger.warning(f"Failed to setup kernel functions: {e}")

                    logger.info("=" * 80)
                    logger.info("CUDA Kernel High-Speed Bridge ENABLED")
                    logger.info(f"  DLL: {dll_path}")
                    logger.info(f"  Compute Capability: sm_75 to sm_120")
                    logger.info(f"  Mode: Direct CUDA Kernel")
                    logger.info("=" * 80)
                    self.enabled = True
                    self._initialized = True
                    return

                self._setup_functions()

                if self.lib.hsgpu_init() == 0:
                    config = self._create_config()
                    self.ctx = self.lib.hsgpu_create_context(ctypes.byref(config))
                    if self.ctx:
                        self.enabled = bridge_enabled
                        self._init_pinned_pool()
                        self._measure_bandwidth()
                        logger.info("=" * 80)
                        logger.info(f"Ultra High-Speed GPU Bridge {'ENABLED' if self.enabled else 'DISABLED'}")
                        logger.info(f"  Bandwidth: {self.bandwidth_gbps:.1f} GB/s")
                        logger.info(f"  Streams: {self.num_streams}")
                        logger.info(f"  Pinned Memory Pool: {len(self.pinned_pool)} buffers")
                        total_pool_mb = sum(buf.numel() * buf.element_size() for buf in self.pinned_pool.values()) / (1024**2)
                        logger.info(f"  Total Pool Size: {total_pool_mb:.1f} MB")
                        logger.info("=" * 80)
                    else:
                        logger.warning("Ultra High-Speed GPU Bridge: Failed to create context")
                else:
                    logger.warning("Ultra High-Speed GPU Bridge: Failed to initialize")
            else:
                logger.info("Ultra High-Speed GPU Bridge DLL not found, using standard transfer")
        except Exception as e:
            logger.warning(f"Ultra High-Speed GPU Bridge initialization failed: {e}")
        
        self._initialized = True
    
    def _find_dll(self):
        kernel_path = os.environ.get('CUDA_KERNEL_PATH')
        if kernel_path:
            kernel_full_path = Path(kernel_path)
            if kernel_full_path.exists():
                logger.info(f"Using CUDA Kernel from env: {kernel_full_path}")
                return kernel_full_path

        search_paths = [
            Path(__file__).parent / "ultra_transfer_kernel.dll",
            Path(__file__).parent / "high_speed_gpu.dll",
            Path(__file__).parent.parent.parent / "high_speed_gpu.dll",
            Path("high_speed_gpu.dll"),
        ]

        for path in search_paths:
            if path.exists():
                return path
        return None
    
    def _init_pinned_pool(self):
        if self.pool_initialized:
            return

        try:
            import torch
            logger.info("Initializing pinned memory pool...")

            for size_bytes in self.pool_sizes:
                try:
                    num_elements = size_bytes // 4
                    buffer = torch.empty(num_elements, dtype=torch.float32, pin_memory=True)
                    self.pinned_pool[size_bytes] = buffer
                    logger.debug(f"  Allocated {size_bytes / (1024**2):.1f} MB pinned buffer")
                except Exception as e:
                    logger.warning(f"  Failed to allocate {size_bytes / (1024**2):.1f} MB buffer: {e}")

            self.pool_initialized = True
            logger.info(f"Pinned memory pool initialized with {len(self.pinned_pool)} buffers")

        except Exception as e:
            logger.warning(f"Failed to initialize pinned memory pool: {e}")
            self.pinned_pool = {}

    def _get_pinned_buffer(self, size_bytes):
        if not self.pool_initialized or size_bytes <= 0:
            return None

        for pool_size in self.pool_sizes:
            if pool_size >= size_bytes and pool_size in self.pinned_pool:
                return self.pinned_pool[pool_size], pool_size

        return None, 0

    def _create_config(self):
        class HSGPUConfig(ctypes.Structure):
            _fields_ = [
                ("device_id", ctypes.c_int),
                ("max_memory", ctypes.c_size_t),
                ("num_streams", ctypes.c_int),
                ("use_pinned_memory", ctypes.c_int),
                ("enable_profiling", ctypes.c_int)
            ]
        
        config = HSGPUConfig()
        config.device_id = 0
        config.max_memory = 2 * 1024 * 1024 * 1024
        config.num_streams = self.num_streams
        config.use_pinned_memory = 1
        config.enable_profiling = 1
        return config
    
    def _setup_functions(self):
        self.lib.hsgpu_init.restype = ctypes.c_int
        
        self.lib.hsgpu_create_context.argtypes = [ctypes.c_void_p]
        self.lib.hsgpu_create_context.restype = ctypes.c_void_p
        
        self.lib.hsgpu_destroy_context.argtypes = [ctypes.c_void_p]
        self.lib.hsgpu_destroy_context.restype = ctypes.c_int
        
        self.lib.hsgpu_transfer_to_gpu.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t
        ]
        self.lib.hsgpu_transfer_to_gpu.restype = ctypes.c_int
        
        self.lib.hsgpu_transfer_from_gpu.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t
        ]
        self.lib.hsgpu_transfer_from_gpu.restype = ctypes.c_int
        
        self.lib.hsgpu_transfer_to_gpu_async.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int
        ]
        self.lib.hsgpu_transfer_to_gpu_async.restype = ctypes.c_int
        
        self.lib.hsgpu_synchronize_stream.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.hsgpu_synchronize_stream.restype = ctypes.c_int
        
        self.lib.hsgpu_synchronize_all.argtypes = [ctypes.c_void_p]
        self.lib.hsgpu_synchronize_all.restype = ctypes.c_int
    
    def _measure_bandwidth(self):
        try:
            test_size = 1024 * 1024 * 1024
            test_tensor = torch.randn(test_size // 4, dtype=torch.float32).pin_memory()

            if torch.cuda.is_available():
                torch.cuda.synchronize()

                warmup_runs = 3
                for _ in range(warmup_runs):
                    gpu_tensor = test_tensor.cuda(non_blocking=True)
                    torch.cuda.synchronize()
                    del gpu_tensor

                num_runs = 10
                total_time = 0.0

                for _ in range(num_runs):
                    start = torch.cuda.Event(enable_timing=True)
                    end = torch.cuda.Event(enable_timing=True)

                    start.record()
                    gpu_tensor = test_tensor.cuda(non_blocking=True)
                    end.record()
                    torch.cuda.synchronize()

                    elapsed_ms = start.elapsed_time(end)
                    total_time += elapsed_ms
                    del gpu_tensor

                avg_time_ms = total_time / num_runs
                if avg_time_ms > 0:
                    self.bandwidth_gbps = (test_size / (1024**3)) / (avg_time_ms / 1000.0)
                else:
                    self.bandwidth_gbps = 60.0

                del test_tensor
        except Exception as e:
            logger.debug(f"Bandwidth measurement failed: {e}")
            self.bandwidth_gbps = 60.0
    
    def is_enabled(self):
        return self.enabled
    
    def get_bandwidth(self):
        return self.bandwidth_gbps
    
    def transfer_to_gpu(self, tensor: torch.Tensor, device) -> torch.Tensor:
        if not self.enabled or not torch.cuda.is_available():
            return tensor.to(device)

        try:
            if tensor.is_cuda:
                return tensor.to(device)

            if not tensor.is_contiguous():
                tensor = tensor.contiguous()

            kernel_enabled = os.environ.get('ULTRA_BRIDGE_KERNEL') == '1'

            if kernel_enabled and self.lib and hasattr(self.lib, 'ultra_memcpy_async_raw'):
                try:
                    if not tensor.is_pinned():
                        tensor = tensor.pin_memory()

                    result = torch.empty_like(tensor, device=device)
                    stream = torch.cuda.current_stream().cuda_stream

                    ret = self.lib.ultra_memcpy_async_raw(
                        result.data_ptr(),
                        tensor.data_ptr(),
                        tensor.numel() * tensor.element_size(),
                        1,
                        stream
                    )

                    if ret == 0:
                        torch.cuda.synchronize()
                        return result
                except Exception as e:
                    logger.debug(f"CUDA kernel transfer failed: {e}")

            size_bytes = tensor.numel() * tensor.element_size()

            if tensor.is_pinned():
                return tensor.to(device, non_blocking=True)

            pool_buffer, pool_size = self._get_pinned_buffer(size_bytes)

            if pool_buffer is not None:
                flat_tensor = tensor.view(-1)
                num_elements = flat_tensor.numel()

                pool_buffer_flat = pool_buffer.view(-1)
                pool_buffer_flat[:num_elements].copy_(flat_tensor)

                result = pool_buffer_flat[:num_elements].to(device, non_blocking=True)

                return result.view_as(tensor)
            else:
                pinned = tensor.pin_memory()
                return pinned.to(device, non_blocking=True)

        except Exception as e:
            logger.debug(f"Ultra high-speed transfer failed, using standard: {e}")
            return tensor.to(device)
    
    def _get_pinned_buffer(self, size_bytes):
        if size_bytes in self.pinned_pool:
            return self.pinned_pool[size_bytes]

        if size_bytes <= self.max_pool_size:
            try:
                buffer = torch.empty(size_bytes // 4, dtype=torch.float32).pin_memory()
                self.pinned_pool[size_bytes] = buffer
                return buffer
            except:
                pass
        return None

    def _transfer_large_tensor(self, tensor: torch.Tensor, device_id: int) -> torch.Tensor:
        device = torch.device(f'cuda:{device_id}')

        total_elements = tensor.numel()
        element_size = tensor.element_size()
        total_bytes = total_elements * element_size

        if total_bytes <= 128 * 1024 * 1024:
            if tensor.is_pinned():
                return tensor.to(device, non_blocking=True)
            else:
                pinned = tensor.pin_memory()
                result = pinned.to(device, non_blocking=True)
                torch.cuda.synchronize(device)
                return result

        chunk_size = 1024 * 1024 * 1024
        num_chunks = max(1, (total_bytes + chunk_size - 1) // chunk_size)
        elements_per_chunk = (total_elements + num_chunks - 1) // num_chunks

        result = torch.empty_like(tensor, device=device)

        flat_tensor = tensor.view(-1)
        flat_result = result.view(-1)

        num_active_streams = min(self.num_streams, num_chunks)
        streams = [torch.cuda.Stream(device=device) for _ in range(num_active_streams)]
        events = [torch.cuda.Event() for _ in range(num_active_streams)]

        for i in range(num_chunks):
            stream_idx = i % num_active_streams
            start_idx = i * elements_per_chunk
            end_idx = min((i + 1) * elements_per_chunk, total_elements)

            chunk = flat_tensor[start_idx:end_idx]

            if i >= num_active_streams:
                events[stream_idx].wait()

            with torch.cuda.stream(streams[stream_idx]):
                if chunk.is_pinned():
                    flat_result[start_idx:end_idx].copy_(chunk, non_blocking=True)
                else:
                    pinned_chunk = chunk.pin_memory()
                    flat_result[start_idx:end_idx].copy_(pinned_chunk, non_blocking=True)
                events[stream_idx].record(streams[stream_idx])

        for stream in streams:
            stream.synchronize()

        return result.view_as(tensor)
    
    def transfer_from_gpu(self, tensor: torch.Tensor) -> torch.Tensor:
        if not self.enabled or not tensor.is_cuda:
            return tensor.cpu()

        try:
            return tensor.to('cpu', non_blocking=True)

        except Exception as e:
            logger.debug(f"Ultra high-speed transfer failed, using standard: {e}")
            return tensor.cpu()
    
    def _transfer_large_from_gpu(self, tensor: torch.Tensor) -> torch.Tensor:
        total_elements = tensor.numel()
        element_size = tensor.element_size()
        total_bytes = total_elements * element_size

        chunk_size = 512 * 1024 * 1024

        if total_bytes <= chunk_size:
            result = torch.empty_like(tensor, device='cpu').pin_memory()
            result.copy_(tensor, non_blocking=True)
            torch.cuda.synchronize(tensor.device)
            return result

        num_chunks = (total_bytes + chunk_size - 1) // chunk_size
        elements_per_chunk = chunk_size // element_size

        result = torch.empty_like(tensor, device='cpu').pin_memory()

        flat_tensor = tensor.view(-1)
        flat_result = result.view(-1)

        device = tensor.device
        num_active_streams = min(self.num_streams, num_chunks)
        streams = [torch.cuda.Stream(device=device) for _ in range(num_active_streams)]

        for i in range(num_chunks):
            stream_idx = i % num_active_streams
            start_idx = i * elements_per_chunk
            end_idx = min((i + 1) * elements_per_chunk, total_elements)

            with torch.cuda.stream(streams[stream_idx]):
                flat_result[start_idx:end_idx].copy_(flat_tensor[start_idx:end_idx], non_blocking=True)

        for stream in streams:
            stream.synchronize()

        return result.view_as(tensor)
    
    def __del__(self):
        if self.ctx and self.lib:
            try:
                self.lib.hsgpu_destroy_context(self.ctx)
            except:
                pass

_bridge = UltraHighSpeedBridge()

def is_ultra_high_speed_enabled():
    return _bridge.is_enabled()

def get_transfer_bandwidth():
    return _bridge.get_bandwidth()

def cpu_to_gpu_ultra(tensor, device):
    return _bridge.transfer_to_gpu(tensor, device)

def gpu_to_cpu_ultra(tensor):
    return _bridge.transfer_from_gpu(tensor)

