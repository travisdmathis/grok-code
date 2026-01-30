"""Test execution tools for Python/JS/TS/lint."""

from pathlib import Path
from typing import Dict, List
import subprocess
import re
from .base import Tool
from .file_ops import mark_file_read  # Reuse if needed

def detect_lang(scope: str) -> str:
    \"\"\"Detect language from scope/dir.\"\"\"
    if 'test' in scope or Path(scope).glob('test_*.py'):
        return 'py'
    if Path(scope).glob('*.js') or Path(scope).glob('*.ts'):
        return 'js'
    return 'unknown'

def get_test_cmd(lang: str, scope: str) -> List[str]:
    if lang == 'py':
        return ['pytest', scope, '--tb=short', '-v', '--no-header']
    elif lang == 'js':
        return ['npm', 'test', '--', scope] if Path('package.json').exists() else ['jest', scope]
    elif lang == 'lint':
        return ['ruff', 'check', scope] if Path('.').glob('pyproject.toml') else ['eslint', scope]
    return []

def parse_summary(output: str) -> str:
    \"\"\"Parse test/lint summary.\"\"\"
    py_match = re.search(r'(\\d+) passed(?:, (\\d+) failed)?(?:, (\\d+) skipped)?', output)
    if py_match:
        passed, failed, skipped = py_match.groups()
        failed = failed or 0
        skipped = skipped or 0
        return f"{passed} passed, {failed} failed, {skipped} skipped"
    return "Unknown format"

class TestRunTool(Tool):
    @property
    def name(self) -> str:
        return "test_run"

    @property
    def description(self) -> str:
        return \"\"\"Run tests or lint in scope (auto-detect py/js/lint).

Params:
- scope: dir/pattern e.g. 'tests/', 'src/**/*.py'
- lang: 'py'/'js'/'lint'/'auto' (default)

Returns summary + failures.
        \"\"\"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "default": "tests/"},
                "lang": {"type": "string", "enum": ["auto", "py", "js", "lint"], "default": "auto"},
            },
            "required": [],
        }

    async def execute(self, scope: str = "tests/", lang: str = "auto") -> str:
        lang = detect_lang(scope) if lang == "auto" else lang
        cmd = get_test_cmd(lang, scope)
        if not cmd:
            return f"No test runner for {lang} in {scope}"
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=Path.cwd())
            summary = parse_summary(res.stdout)
            failures = res.stderr or res.stdout if res.returncode else ""
            mark_file_read(scope)  # Treat as 'read'
            return f"Test {lang} {scope}: {summary}\\n\\n{failures[:2000]}{'...' if len(failures)>2000 else ''}"
        except subprocess.TimeoutExpired:
            return "Test timeout (120s)"
        except Exception as e:
            return f"Test error: {e}"