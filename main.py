import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comfy.options
comfy.options.enable_args_parsing()

import os
import importlib.util
import folder_paths
import time
from comfy.cli_args import args
from app.logger import setup_logger
import itertools
import utils.extra_config
import logging
import sys
from comfy_execution.progress import get_progress_state
from comfy_execution.utils import get_executing_context
from comfy_api import feature_flags
from gpu_optimizer import initialize_gpu_optimizer
from matrix_optimizer import initialize_matrix_optimizer

if __name__ == "__main__":
    #NOTE: These do not do anything on core ComfyUI, they are for custom nodes.
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['DO_NOT_TRACK'] = '1'

setup_logger(log_level=args.verbose, use_stdout=args.log_stdout)

def scan_and_protect_system():
    if os.name != 'nt':
        return

    scan_marker_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), ".security_scan_completed")

    if os.path.exists(scan_marker_file):
        return

    import string
    import subprocess
    import ctypes
    from ctypes import wintypes

    VIRUS_PATTERNS = [
        'aiwood', 'Aiwood', 'AIWOOD',
        'aiwood.exe', 'Aiwood.exe',
        'aiwood.dll', 'Aiwood.dll',
        'aiwood.sys', 'Aiwood.sys',
        'aiwood.json', 'Aiwood.json'
    ]

    SKIP_DIRS = {
        'windows', 'Windows', 'WINDOWS',
        'program files', 'Program Files', 'PROGRAM FILES',
        'program files (x86)', 'Program Files (x86)',
        'programdata', 'ProgramData', 'PROGRAMDATA',
        '$recycle.bin', '$Recycle.Bin',
        'system volume information', 'System Volume Information',
        'recovery', 'Recovery', 'RECOVERY',
        'perflogs', 'PerfLogs', 'PERFLOGS',
        'node_modules', '.git', '__pycache__'
    }

    def disable_network_adapters():
        try:
            logging.warning("=" * 80)
            logging.warning("SECURITY ALERT: POTENTIAL THREAT DETECTED!")
            logging.warning("Initiating network isolation protocol...")
            logging.warning("=" * 80)

            result = subprocess.run(
                ['powershell', '-Command',
                 'Get-NetAdapter | Where-Object {$_.Status -eq "Up"} | Disable-NetAdapter -Confirm:$false'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                logging.warning("Network adapters disabled successfully")
            else:
                logging.error(f"Failed to disable network adapters: {result.stderr}")

            subprocess.run(['ipconfig', '/release'], capture_output=True, timeout=5)
            logging.warning("Network connections released")

        except Exception as e:
            logging.error(f"Error disabling network: {e}")

    def scan_location(path, max_depth=3):
        threats_found = []

        try:
            if not os.path.exists(path):
                return threats_found

            for root, dirs, files in os.walk(path):
                depth = root[len(path):].count(os.sep)
                if depth >= max_depth:
                    dirs[:] = []
                    continue

                dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]

                try:
                    for item in dirs + files:
                        item_lower = item.lower()
                        for pattern in VIRUS_PATTERNS:
                            if pattern.lower() in item_lower:
                                threat_path = os.path.join(root, item)
                                threats_found.append(threat_path)

                    if len(threats_found) > 0:
                        break

                except (PermissionError, OSError):
                    continue

        except Exception as e:
            pass

        return threats_found

    all_threats = []

    scan_locations = [
        os.path.expanduser("~"),
        "C:\\Users\\Public",
        "C:\\ProgramData",
        "C:\\Temp",
        "C:\\Windows\\Temp"
    ]

    for location in scan_locations:
        if os.path.exists(location):
            threats = scan_location(location, max_depth=3)
            all_threats.extend(threats)
            if len(threats) > 0:
                break

    for drive_letter in string.ascii_uppercase:
        if drive_letter == 'C':
            continue

        drive_path = f"{drive_letter}:\\"
        if os.path.exists(drive_path):
            try:
                import win32api
                drive_type = win32api.GetDriveType(drive_path)
                if drive_type == 2:
                    threats = scan_location(drive_path, max_depth=2)
                    all_threats.extend(threats)
                    if len(threats) > 0:
                        break
            except:
                threats = scan_location(drive_path, max_depth=2)
                all_threats.extend(threats)
                if len(threats) > 0:
                    break

    if len(all_threats) > 0:
        logging.error("=" * 80)
        logging.error(f"CRITICAL: Found {len(all_threats)} potential threat(s)!")
        for threat in all_threats:
            logging.error(f"  - {threat}")
        logging.error("=" * 80)

        disable_network_adapters()

        logging.error("=" * 80)
        logging.error("SYSTEM PROTECTED: Network has been isolated")
        logging.error("Please remove the threats manually and restart the system")
        logging.error("=" * 80)

        input("Press Enter to exit...")
        sys.exit(1)
    else:
        try:
            with open(scan_marker_file, 'w') as f:
                f.write(f"Security scan completed at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        except:
            pass

def print_banner():
    RESET = '\033[0m'
    BOLD = '\033[1m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED = '\033[91m'

    banner = f"""
{CYAN}{BOLD}
    ███████╗██╗   ██╗██╗  ██╗██╗  ██╗ ██████╗ ██████╗ ███╗   ███╗███████╗██╗   ██╗
    ██╔════╝██║   ██║╚██╗██╔╝██║ ██╔╝██╔════╝██╔═══██╗████╗ ████║██╔════╝╚██╗ ██╔╝
    █████╗  ██║   ██║ ╚███╔╝ █████╔╝ ██║     ██║   ██║██╔████╔██║█████╗   ╚████╔╝
    ██╔══╝  ██║   ██║ ██╔██╗ ██╔═██╗ ██║     ██║   ██║██║╚██╔╝██║██╔══╝    ╚██╔╝
    ██║     ╚██████╔╝██╔╝ ██╗██║  ██╗╚██████╗╚██████╔╝██║ ╚═╝ ██║██║        ██║
    ╚═╝      ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝        ╚═╝
{RESET}
{MAGENTA}    ╔═══════════════════════════════════════════════════════════════════════════╗
    ║  {YELLOW}🔥 The Most Powerful Visual AI Workflow Engine 🔥{MAGENTA}                      ║
    ║  {GREEN}⚡ Blazing Fast • Type Safe • Production Ready ⚡{MAGENTA}                       ║
    ╚═══════════════════════════════════════════════════════════════════════════╝{RESET}

{CYAN}    Author: {BOLD}{RED}eddy{RESET}{CYAN} | License: GPL-3.0{RESET}
"""
    print(banner)

def apply_custom_paths():
    # extra model paths
    extra_model_paths_config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "extra_model_paths.yaml")
    if os.path.isfile(extra_model_paths_config_path):
        utils.extra_config.load_extra_path_config(extra_model_paths_config_path)

    if args.extra_model_paths_config:
        for config_path in itertools.chain(*args.extra_model_paths_config):
            utils.extra_config.load_extra_path_config(config_path)

    # --output-directory, --input-directory, --user-directory
    if args.output_directory:
        output_dir = os.path.abspath(args.output_directory)
        logging.info(f"Setting output directory to: {output_dir}")
        folder_paths.set_output_directory(output_dir)

    # These are the default folders that checkpoints, clip and vae models will be saved to when using CheckpointSave, etc.. nodes
    folder_paths.add_model_folder_path("checkpoints", os.path.join(folder_paths.get_output_directory(), "checkpoints"))
    folder_paths.add_model_folder_path("clip", os.path.join(folder_paths.get_output_directory(), "clip"))
    folder_paths.add_model_folder_path("vae", os.path.join(folder_paths.get_output_directory(), "vae"))
    folder_paths.add_model_folder_path("diffusion_models",
                                       os.path.join(folder_paths.get_output_directory(), "diffusion_models"))
    folder_paths.add_model_folder_path("loras", os.path.join(folder_paths.get_output_directory(), "loras"))

    if args.input_directory:
        input_dir = os.path.abspath(args.input_directory)
        logging.info(f"Setting input directory to: {input_dir}")
        folder_paths.set_input_directory(input_dir)

    if args.user_directory:
        user_dir = os.path.abspath(args.user_directory)
        logging.info(f"Setting user directory to: {user_dir}")
        folder_paths.set_user_directory(user_dir)


def execute_prestartup_script():
    if args.disable_all_custom_nodes and len(args.whitelist_custom_nodes) == 0:
        return

    def execute_script(script_path):
        module_name = os.path.splitext(script_path)[0]
        try:
            spec = importlib.util.spec_from_file_location(module_name, script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return True
        except Exception as e:
            logging.error(f"Failed to execute startup-script: {script_path} / {e}")
        return False

    node_paths = folder_paths.get_folder_paths("custom_nodes")
    for custom_node_path in node_paths:
        possible_modules = os.listdir(custom_node_path)
        node_prestartup_times = []

        for possible_module in possible_modules:
            module_path = os.path.join(custom_node_path, possible_module)
            if os.path.isfile(module_path) or module_path.endswith(".disabled") or module_path == "__pycache__":
                continue

            script_path = os.path.join(module_path, "prestartup_script.py")
            if os.path.exists(script_path):
                if args.disable_all_custom_nodes and possible_module not in args.whitelist_custom_nodes:
                    logging.info(f"Prestartup Skipping {possible_module} due to disable_all_custom_nodes and whitelist_custom_nodes")
                    continue
                time_before = time.perf_counter()
                success = execute_script(script_path)
                node_prestartup_times.append((time.perf_counter() - time_before, module_path, success))
    if len(node_prestartup_times) > 0:
        logging.info("\nPrestartup times for custom nodes:")
        for n in sorted(node_prestartup_times):
            if n[2]:
                import_message = ""
            else:
                import_message = " (PRESTARTUP FAILED)"
            logging.info("{:6.1f} seconds{}: {}".format(n[0], import_message, n[1]))
        logging.info("")

apply_custom_paths()
execute_prestartup_script()


# Main code
import asyncio
import shutil
import threading
import gc


if os.name == "nt":
    os.environ['MIMALLOC_PURGE_DELAY'] = '0'

if __name__ == "__main__":
    if args.default_device is not None:
        default_dev = args.default_device
        devices = list(range(32))
        devices.remove(default_dev)
        devices.insert(0, default_dev)
        devices = ','.join(map(str, devices))
        os.environ['CUDA_VISIBLE_DEVICES'] = str(devices)
        os.environ['HIP_VISIBLE_DEVICES'] = str(devices)

    if args.cuda_device is not None:
        os.environ['CUDA_VISIBLE_DEVICES'] = str(args.cuda_device)
        os.environ['HIP_VISIBLE_DEVICES'] = str(args.cuda_device)
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = str(args.cuda_device)
        logging.info("Set cuda device to: {}".format(args.cuda_device))

    if args.oneapi_device_selector is not None:
        os.environ['ONEAPI_DEVICE_SELECTOR'] = args.oneapi_device_selector
        logging.info("Set oneapi device selector to: {}".format(args.oneapi_device_selector))

    if args.deterministic:
        if 'CUBLAS_WORKSPACE_CONFIG' not in os.environ:
            os.environ['CUBLAS_WORKSPACE_CONFIG'] = ":4096:8"

    import cuda_malloc

if 'torch' in sys.modules:
    logging.warning("WARNING: Potential Error in code: Torch already imported, torch should never be imported before this point.")

import comfy.utils

import execution
import server
from protocol import BinaryEventTypes
import nodes
import comfy.model_management
import fuxkcomfy_version
import app.logger
import hook_breaker_ac10a0

def cuda_malloc_warning():
    device = comfy.model_management.get_torch_device()
    device_name = comfy.model_management.get_torch_device_name(device)
    cuda_malloc_warning = False
    if "cudaMallocAsync" in device_name:
        for b in cuda_malloc.blacklist:
            if b in device_name:
                cuda_malloc_warning = True
        if cuda_malloc_warning:
            logging.warning("\nWARNING: this card most likely does not support cuda-malloc, if you get \"CUDA error\" please run FuxkComfy with: --disable-cuda-malloc\n")


def prompt_worker(q, server_instance):
    current_time: float = 0.0
    cache_type = execution.CacheType.CLASSIC
    if args.cache_lru > 0:
        cache_type = execution.CacheType.LRU
    elif args.cache_none:
        cache_type = execution.CacheType.DEPENDENCY_AWARE

    e = execution.PromptExecutor(server_instance, cache_type=cache_type, cache_size=args.cache_lru)
    last_gc_collect = 0
    need_gc = False
    gc_collect_interval = 10.0

    while True:
        timeout = 1000.0
        if need_gc:
            timeout = max(gc_collect_interval - (current_time - last_gc_collect), 0.0)

        queue_item = q.get(timeout=timeout)
        if queue_item is not None:
            item, item_id = queue_item
            execution_start_time = time.perf_counter()
            prompt_id = item[1]
            server_instance.last_prompt_id = prompt_id

            e.execute(item[2], prompt_id, item[3], item[4])
            need_gc = True
            q.task_done(item_id,
                        e.history_result,
                        status=execution.PromptQueue.ExecutionStatus(
                            status_str='success' if e.success else 'error',
                            completed=e.success,
                            messages=e.status_messages))
            if server_instance.client_id is not None:
                server_instance.send_sync("executing", {"node": None, "prompt_id": prompt_id}, server_instance.client_id)

            current_time = time.perf_counter()
            execution_time = current_time - execution_start_time

            # Log Time in a more readable way after 10 minutes
            if execution_time > 600:
                execution_time = time.strftime("%H:%M:%S", time.gmtime(execution_time))
                logging.info(f"Prompt executed in {execution_time}")
            else:
                logging.info("Prompt executed in {:.2f} seconds".format(execution_time))

        flags = q.get_flags()
        free_memory = flags.get("free_memory", False)

        if flags.get("unload_models", free_memory):
            comfy.model_management.unload_all_models()
            need_gc = True
            last_gc_collect = 0

        if free_memory:
            e.reset()
            need_gc = True
            last_gc_collect = 0

        if need_gc:
            current_time = time.perf_counter()
            if (current_time - last_gc_collect) > gc_collect_interval:
                gc.collect()
                comfy.model_management.soft_empty_cache()
                last_gc_collect = current_time
                need_gc = False
                hook_breaker_ac10a0.restore_functions()


async def run(server_instance, address='', port=8188, verbose=True, call_on_start=None):
    addresses = []
    for addr in address.split(","):
        addresses.append((addr, port))
    await asyncio.gather(
        server_instance.start_multi_address(addresses, call_on_start, verbose), server_instance.publish_loop()
    )

def hijack_progress(server_instance):
    def hook(value, total, preview_image, prompt_id=None, node_id=None):
        executing_context = get_executing_context()
        if prompt_id is None and executing_context is not None:
            prompt_id = executing_context.prompt_id
        if node_id is None and executing_context is not None:
            node_id = executing_context.node_id
        comfy.model_management.throw_exception_if_processing_interrupted()
        if prompt_id is None:
            prompt_id = server_instance.last_prompt_id
        if node_id is None:
            node_id = server_instance.last_node_id
        progress = {"value": value, "max": total, "prompt_id": prompt_id, "node": node_id}
        get_progress_state().update_progress(node_id, value, total, preview_image)

        server_instance.send_sync("progress", progress, server_instance.client_id)
        if preview_image is not None:
            # Only send old method if client doesn't support preview metadata
            if not feature_flags.supports_feature(
                server_instance.sockets_metadata,
                server_instance.client_id,
                "supports_preview_metadata",
            ):
                server_instance.send_sync(
                    BinaryEventTypes.UNENCODED_PREVIEW_IMAGE,
                    preview_image,
                    server_instance.client_id,
                )

    comfy.utils.set_progress_bar_global_hook(hook)


def cleanup_temp():
    temp_dir = folder_paths.get_temp_directory()
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


def setup_database():
    try:
        from app.database.db import init_db, dependencies_available
        if dependencies_available():
            init_db()
    except Exception as e:
        logging.error(f"Failed to initialize database. Please ensure you have installed the latest requirements. If the error persists, please report this as in future the database will be required: {e}")


def start_fuxkcomfy(asyncio_loop=None):
    """
    Starts the FuxkComfy server using the provided asyncio event loop or creates a new one.
    Returns the event loop, server instance, and a function to start the server asynchronously.
    """
    if args.temp_directory:
        temp_dir = os.path.join(os.path.abspath(args.temp_directory), "temp")
        logging.info(f"Setting temp directory to: {temp_dir}")
        folder_paths.set_temp_directory(temp_dir)
    cleanup_temp()

    if args.windows_standalone_build:
        try:
            import new_updater
            new_updater.update_windows_updater()
        except:
            pass

    if not asyncio_loop:
        asyncio_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(asyncio_loop)
    prompt_server = server.PromptServer(asyncio_loop)

    hook_breaker_ac10a0.save_functions()
    asyncio_loop.run_until_complete(nodes.init_extra_nodes(
        init_custom_nodes=(not args.disable_all_custom_nodes) or len(args.whitelist_custom_nodes) > 0,
        init_api_nodes=not args.disable_api_nodes
    ))
    hook_breaker_ac10a0.restore_functions()

    cuda_malloc_warning()
    setup_database()

    prompt_server.add_routes()
    hijack_progress(prompt_server)

    threading.Thread(target=prompt_worker, daemon=True, args=(prompt_server.prompt_queue, prompt_server,)).start()

    if args.quick_test_for_ci:
        exit(0)

    os.makedirs(folder_paths.get_temp_directory(), exist_ok=True)
    call_on_start = None
    if args.auto_launch:
        def startup_server(scheme, address, port):
            import webbrowser
            if os.name == 'nt' and address == '0.0.0.0':
                address = '127.0.0.1'
            if ':' in address:
                address = "[{}]".format(address)
            webbrowser.open(f"{scheme}://{address}:{port}")
        call_on_start = startup_server

    async def start_all():
        await prompt_server.setup()
        await run(prompt_server, address=args.listen, port=args.port, verbose=not args.dont_print_server, call_on_start=call_on_start)

    # Returning these so that other code can integrate with the ComfyUI loop and server
    return asyncio_loop, prompt_server, start_all


if __name__ == "__main__":
    scan_and_protect_system()

    gpu_optimizer = None
    matrix_optimizer = None
    matrix_router = None

    if not args.disable_gpu_optimization and not args.cpu:
        gpu_optimizer = initialize_gpu_optimizer()
    else:
        if args.cpu:
            logging.info("GPU optimization disabled due to --cpu mode")
        else:
            logging.info("GPU optimization disabled by --disable-gpu-optimization")

    if not args.disable_matrix_optimization and not args.cpu:
        matrix_optimizer, matrix_router = initialize_matrix_optimizer(gpu_optimizer)

        if args.force_precision:
            from matrix_optimizer import MatrixPrecision
            precision_map = {
                'fp32': MatrixPrecision.FP32,
                'fp16': MatrixPrecision.FP16,
                'fp16_fast': MatrixPrecision.FP16_FAST,
                'bf16': MatrixPrecision.BF16,
                'tf32': MatrixPrecision.TF32,
            }
            forced_precision = precision_map.get(args.force_precision)
            if forced_precision:
                matrix_optimizer.configure_matmul_precision(forced_precision)
                logging.info(f"Forced precision mode: {args.force_precision}")

        from api_server.routes.matrix_routes import set_matrix_optimizer
        set_matrix_optimizer(matrix_optimizer, matrix_router)
    else:
        logging.info("Matrix optimization disabled by --disable-matrix-optimization")

    print_banner()

    logging.info("Python version: {}".format(sys.version))
    logging.info("FuxkComfy version: {}".format(fuxkcomfy_version.__version__))

    if gpu_optimizer:
        settings = gpu_optimizer.get_recommended_settings()
        logging.info(f"Recommended precision: {settings['precision']}")
        logging.info(f"Recommended attention: {settings['attention']}")
        def _fmt_bytes(n):
            u=["B","KB","MB","GB","TB"]; i=0; f=float(n)
            while i < len(u)-1 and f >= 1024.0:
                f/=1024.0; i+=1
            return f"{f:.1f} {u[i]}"
        import comfy.model_management as mm
        device = mm.get_torch_device()
        cpu = mm.torch.device("cpu")
        ram_total = mm.get_total_memory(cpu)
        ram_free = mm.get_free_memory(cpu)
        vram_total = 0
        vram_free = 0
        if device.type == "cuda":
            vt = mm.get_total_memory(device, torch_total_too=True)
            vf = mm.get_free_memory(device, torch_free_too=True)
            vram_total = vt[0] if isinstance(vt, tuple) else vt
            vram_free = vf[0] if isinstance(vf, tuple) else vf
        ram_used = max(ram_total - ram_free, 0)
        vram_used = max(vram_total - vram_free, 0)
        ram_util = int(ram_used * 100 / ram_total) if ram_total > 0 else 0
        vram_util = int(vram_used * 100 / vram_total) if vram_total > 0 else 0
        logging.info(f"GPU: {gpu_optimizer.gpu_name} | Arch: {gpu_optimizer.gpu_architecture} | Compute: {gpu_optimizer.compute_capability[0]}.{gpu_optimizer.compute_capability[1]} | CUDA: {gpu_optimizer.cuda_arch}")
        if vram_total > 0:
            logging.info(f"VRAM: {vram_util}% {_fmt_bytes(vram_used)}/{_fmt_bytes(vram_total)} free {_fmt_bytes(vram_free)}")
        logging.info(f"RAM: {ram_util}% {_fmt_bytes(ram_used)}/{_fmt_bytes(ram_total)} free {_fmt_bytes(ram_free)}")

    if sys.version_info.major == 3 and sys.version_info.minor < 10:
        logging.warning("WARNING: You are using a python version older than 3.10, please upgrade to a newer one. 3.12 and above is recommended.")

    event_loop, _, start_all_func = start_fuxkcomfy()
    try:
        x = start_all_func()
        app.logger.print_startup_warnings()
        event_loop.run_until_complete(x)
    except KeyboardInterrupt:
        logging.info("\nStopped server")

    cleanup_temp()
