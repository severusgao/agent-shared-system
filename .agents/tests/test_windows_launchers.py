from __future__ import annotations

import re
import unittest
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    ROOT / "scripts" / "windows-skill-sync.cmd",
    ROOT / "scripts" / "windows-mcp-sync.cmd",
)
WSL_WRAPPER = ROOT / "scripts" / "windows-wsl-shared-sync.cmd"


class WindowsLauncherTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'PowerShell launcher behavior runs on Windows')
    def test_skill_launcher_does_not_retry_failed_operation(self) -> None:
        shell = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'PowerShell/7/pwsh.exe'
        if not shell.is_file():
            self.skipTest('PowerShell 7 unavailable')
        for name in ('windows-skill-sync.cmd', 'deploy-cloud-skills-windows.cmd'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fake = root / 'fake-python.ps1'
                fake.write_text("if ($args -contains '-c') { exit 0 }\nAdd-Content -LiteralPath $env:CALL_LOG -Value task\nexit 17\n", encoding='utf-8')
                text = (ROOT / 'scripts' / name).read_text(encoding='utf-8')
                helper = text[text.index('$env:PYTHONDONTWRITEBYTECODE'):text.index('$scriptDir =')]
                driver = root / 'driver.ps1'
                driver.write_text("function Get-Command { param($Name, $ErrorAction) [pscustomobject]@{ Name='py.exe'; Source=$env:FAKE_PYTHON } }\n" + helper + "\ntry { Invoke-Python -Arguments @('task.py'); exit 0 } catch { Write-Output $_; exit 1 }", encoding='utf-8')
                env = dict(os.environ, FAKE_PYTHON=str(fake), CALL_LOG=str(root / 'calls.txt'))
                result = subprocess.run([str(shell), '-NoProfile', '-File', str(driver)], env=env, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((root / 'calls.txt').read_text().splitlines(), ['task'])
                self.assertIn('not retried', result.stdout)

    def test_launchers_probe_python_commands_before_invocation(self) -> None:
        for script in (ROOT / "scripts" / "windows-mcp-sync.cmd",):
            text = script.read_text(encoding="utf-8")
            self.assertIn(
                "Get-Command py -ErrorAction SilentlyContinue",
                text,
                script.name,
            )
            self.assertIn(
                "Get-Command python -ErrorAction SilentlyContinue",
                text,
                script.name,
            )
            self.assertIn(
                "Get-Command python3 -ErrorAction SilentlyContinue",
                text,
                script.name,
            )
            self.assertLess(
                text.index("Get-Command py"),
                text.index("& py -3"),
                script.name,
            )
            self.assertIn(
                'throw "No usable Python interpreter found',
                text,
                script.name,
            )
            self.assertRegex(
                text,
                re.compile(
                    r"if \(\$py\) \{\s*& py -3 @Arguments\s*\$code = \$LASTEXITCODE",
                    re.MULTILINE,
                ),
                script.name,
            )
            self.assertRegex(
                text,
                re.compile(
                    r"if \(\$python\) \{\s*& python @Arguments\s*\$code = \$LASTEXITCODE",
                    re.MULTILINE,
                ),
                script.name,
            )
            self.assertRegex(
                text,
                re.compile(
                    r"if \(\$python3\) \{\s*& python3 @Arguments\s*\$code = \$LASTEXITCODE",
                    re.MULTILINE,
                ),
                script.name,
            )
            py_probe = text.index("$py = Get-Command py")
            py_guard = text.index("if ($py) {")
            py_call = text.index("& py -3 @Arguments")
            self.assertLess(py_probe, py_guard, script.name)
            self.assertLess(py_guard, py_call, script.name)

    def test_launchers_do_not_contain_obsolete_windows_vault_path(self) -> None:
        for script in SCRIPTS:
            text = script.read_text(encoding="utf-8")
            self.assertNotIn(r"E:\备份\\", text, script.name)

    def test_windows_wsl_wrapper_uses_dynamic_path_discovery(self) -> None:
        text = WSL_WRAPPER.read_text(encoding="utf-8")
        self.assertIn("%USERPROFILE%", text)
        self.assertIn("$env:COMPUTERNAME", text)
        self.assertIn("wsl.exe", text)
        self.assertIn("wslpath", text)
        self.assertIn("--windows-agents-root", text)
        self.assertIn("--windows-shared-skills-root", text)
        self.assertIn("--host-machine", text)
        self.assertNotIn(r"C:\Users\Administrator\iCloudDrive", text)
        self.assertNotIn(r"E:\备份\\", text)
        self.assertNotIn("--install", text)

    def test_windows_wsl_wrapper_separates_plan_commands(self) -> None:
        text = WSL_WRAPPER.read_text(encoding="utf-8")
        self.assertRegex(
            text,
            re.compile(
                r'Get-LinkPlan -LocalPath \$localMcpRoot .* -Label "mcp"\s*\n\s*'
                r'Get-LinkPlan -LocalPath \$localMemoriesRoot',
                re.MULTILINE,
            ),
        )

    def test_windows_wsl_wrapper_normalizes_paths_before_wslpath(self) -> None:
        text = WSL_WRAPPER.read_text(encoding="utf-8")
        self.assertIn("$wslInput = $WindowsPath -replace '\\\\', '/'", text)
        self.assertIn("wslpath -u $wslInput", text)

    def test_windows_wsl_wrapper_requires_linux_absolute_agent_path(self) -> None:
        text = WSL_WRAPPER.read_text(encoding="utf-8")
        self.assertIn("function Normalize-LinuxDirectoryInput", text)
        self.assertIn("Detected WSL user", text)
        self.assertIn("Detected WSL home", text)
        self.assertIn("Linux absolute path inside WSL", text)
        self.assertIn("Do not enter a Windows path or a \\\\wsl.localhost path", text)
        self.assertIn("Normalize-LinuxDirectoryInput -Path $agentSkillsDir", text)


if __name__ == "__main__":
    unittest.main()
