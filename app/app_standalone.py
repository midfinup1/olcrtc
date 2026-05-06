import subprocess

from common import PlatformAdapter, run_app, run_command


class MacOSPlatform(PlatformAdapter):
    binary_name = "BareBoneVPN"

    def start_process(self, args: list[str], log_file):
        return subprocess.Popen(
            args,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )

    def kill_existing_client(self):
        run_command(["pkill", "-f", "BareBoneVPN.*-mode.*cnc"], timeout=5)
        run_command(["pkill", "-f", "BareBoneVPN"], timeout=5)

    def enable_system_proxy(self, socks_host: str, socks_port: int, network_service: str):
        code1, out1 = run_command(
            [
                "networksetup",
                "-setsocksfirewallproxy",
                network_service,
                socks_host,
                str(socks_port),
            ],
            timeout=20,
        )

        code2, out2 = run_command(
            [
                "networksetup",
                "-setsocksfirewallproxystate",
                network_service,
                "on",
            ],
            timeout=20,
        )

        if code1 != 0 or code2 != 0:
            raise RuntimeError(out1 + out2)

    def disable_system_proxy(self, network_service: str):
        code, output = run_command(
            [
                "networksetup",
                "-setsocksfirewallproxystate",
                network_service,
                "off",
            ],
            timeout=20,
        )

        if code != 0:
            raise RuntimeError(output)

    def is_port_listening(self, port: int) -> bool:
        code, output = run_command(
            [
                "lsof",
                f"-iTCP:{port}",
                "-sTCP:LISTEN",
            ],
            timeout=3,
        )

        return bool(output.strip())


if __name__ == "__main__":
    run_app(MacOSPlatform(), "macos")