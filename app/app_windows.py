import subprocess
import sys
import winreg

from common import PlatformAdapter, run_app, run_command


def refresh_windows_proxy_settings():
    command = (
        "$signature='[DllImport(\"wininet.dll\", SetLastError = true)] "
        "public static extern bool InternetSetOption(IntPtr hInternet, int dwOption, IntPtr lpBuffer, int dwBufferLength);';"
        "$type=Add-Type -MemberDefinition $signature -Name WinInet -Namespace Native -PassThru;"
        "$type::InternetSetOption([IntPtr]::Zero, 39, [IntPtr]::Zero, 0) | Out-Null;"
        "$type::InternetSetOption([IntPtr]::Zero, 37, [IntPtr]::Zero, 0) | Out-Null;"
    )

    run_command(
        ["powershell", "-NoProfile", "-Command", command],
        timeout=10,
        windows_no_window=True,
    )


class WindowsPlatform(PlatformAdapter):
    binary_name = "olcrtc.exe"

    def start_process(self, args: list[str], log_file):
        return subprocess.Popen(
            args,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def kill_existing_client(self):
        run_command(["taskkill", "/F", "/IM", "olcrtc.exe"], timeout=10, windows_no_window=True)

    def enable_system_proxy(self, socks_host: str, socks_port: int, network_service: str):
        proxy_server = f"socks={socks_host}:{socks_port}"

        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, proxy_server)

        refresh_windows_proxy_settings()

    def disable_system_proxy(self, network_service: str):
        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)

        refresh_windows_proxy_settings()

    def is_port_listening(self, port: int) -> bool:
        code, output = run_command(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue",
            ],
            timeout=3,
            windows_no_window=True,
        )

        return bool(output.strip())


if __name__ == "__main__":
    run_app(WindowsPlatform(), "windows")