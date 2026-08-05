"""Launch and manage the dedicated Electron capture window."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


OUTPUT_PRESETS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}
DEFAULT_OUTPUT_RATIO = "9:16"


def get_output_dimensions(ratio: str) -> tuple[int, int]:
    return OUTPUT_PRESETS.get(ratio, OUTPUT_PRESETS[DEFAULT_OUTPUT_RATIO])


class ElectronOutputWindow:
    def __init__(self, app_directory: Path | None = None) -> None:
        self.app_directory = (app_directory or Path(__file__).resolve().parent).resolve()
        self.process: subprocess.Popen[bytes] | None = None
        self.control_port: int | None = None
        self._started_at = 0.0

    @property
    def is_running(self) -> bool:
        if self.control_port:
            try:
                with urlopen(f"http://127.0.0.1:{self.control_port}/status", timeout=0.2) as response:
                    return response.status == 200
            except OSError:
                pass
        if self.process and self.process.poll() is None:
            return True
        return bool(self._started_at and time.monotonic() - self._started_at < 20.0)

    @staticmethod
    def _get_free_control_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _packaged_executable(self) -> Path | None:
        candidates = [
            self.app_directory / "TikTokLiveOutput.exe",
            self.app_directory / "electron_output" / "dist" / "TikTokLiveOutput.exe",
            Path(__file__).resolve().parent / "electron_output" / "dist" / "TikTokLiveOutput.exe",
        ]
        return next((candidate for candidate in candidates if candidate.is_file()), None)

    def _launch_command(self) -> tuple[list[str], Path]:
        executable = self._packaged_executable()
        if executable:
            return [str(executable)], executable.parent

        project_dir = Path(__file__).resolve().parent / "electron_output"
        electron_cmd = project_dir / "node_modules" / ".bin" / "electron.cmd"
        if electron_cmd.is_file():
            return [str(electron_cmd), str(project_dir)], project_dir

        raise FileNotFoundError(
            "Không tìm thấy TikTokLiveOutput.exe. Hãy chạy build_exe.ps1 hoặc npm install trong electron_output."
        )

    def start(self, overlay_url: str, ratio: str = DEFAULT_OUTPUT_RATIO) -> None:
        parsed = urlparse(overlay_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("Electron output chỉ chấp nhận Browser Overlay nội bộ (localhost).")

        self.stop()
        width, height = get_output_dimensions(ratio)
        self.control_port = self._get_free_control_port()
        command, cwd = self._launch_command()
        command.extend(
            [
                "--url", overlay_url,
                "--ratio", ratio,
                "--width", str(width),
                "--height", str(height),
                "--control-port", str(self.control_port),
            ]
        )
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.process = subprocess.Popen(command, cwd=cwd, creationflags=creationflags)
        self._started_at = time.monotonic()

    def restart(self, overlay_url: str, ratio: str) -> None:
        self.start(overlay_url, ratio)

    def stop(self) -> None:
        process = self.process
        self.process = None
        control_port = self.control_port
        self.control_port = None
        self._started_at = 0.0
        if control_port:
            try:
                with urlopen(f"http://127.0.0.1:{control_port}/close", timeout=1):
                    pass
            except OSError:
                pass
        if not process or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
