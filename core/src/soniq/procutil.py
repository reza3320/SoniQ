"""
procutil.py — cancellable, streamable child processes.

Used by the download path so the tray session can (a) show live progress
by hooking the child's output lines and (b) cancel the running job.
Cancellation sets a flag that callers check to stop retry loops.
"""

import subprocess
import threading

_lock = threading.Lock()
_active = set()
_cancel = threading.Event()
_line_hook = None


def set_line_hook(hook):
    """Register fn(line: str) called for every child output line (or None)."""
    global _line_hook
    _line_hook = hook


def clear_cancel():
    _cancel.clear()


def cancel_requested() -> bool:
    return _cancel.is_set()


def cancel_active():
    """Terminate every child process started via run_cmd()."""
    _cancel.set()
    with _lock:
        procs = list(_active)
    for proc in procs:
        try:
            proc.terminate()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def run_cmd(cmd, timeout=None):
    """Run *cmd*, stream its output lines to the line hook, stay cancellable.

    Returns an object with .returncode and .stdout (all output merged;
    .stderr is always ""). Raises subprocess.TimeoutExpired on timeout.
    """
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    with _lock:
        _active.add(proc)

    lines = []

    def pump():
        try:
            for raw in proc.stdout:
                line = raw.rstrip("\r\n")
                lines.append(line)
                hook = _line_hook
                if hook:
                    try:
                        hook(line)
                    except Exception:
                        pass
        except Exception:
            pass

    pump_thread = threading.Thread(target=pump, daemon=True)
    pump_thread.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.terminate()
        except Exception:
            pass
        raise
    finally:
        pump_thread.join(timeout=5)
        with _lock:
            _active.discard(proc)

    result = CmdResult(proc.returncode, "\n".join(lines))
    return result


class CmdResult:
    """Small stand-in for subprocess.CompletedProcess (returncode/stdout)."""

    def __init__(self, returncode: int, stdout: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""
