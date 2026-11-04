#!/usr/bin/env python3
"""Run host regressions once; the original firmware UI is checked separately."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
results = []
with tempfile.TemporaryDirectory(prefix='a7m3-tests-') as temp:
    for source in sorted((ROOT / 'tests').glob('test-*.c')):
        binary = Path(temp) / source.stem
        build = subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary), '-ldl', '-lm'], cwd=ROOT, capture_output=True, text=True)
        if build.returncode:
            results.append({'test': source.name, 'build_exit_code': build.returncode, 'output': build.stdout + build.stderr})
            continue
        run = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True, timeout=60)
        results.append({'test': source.name, 'exit_code': run.returncode, 'output': run.stdout + run.stderr})
    for source in sorted((ROOT / 'tests').glob('test-*.py')):
        run = subprocess.run([sys.executable, str(source)], cwd=ROOT, capture_output=True, text=True, timeout=60)
        results.append({'test': source.name, 'exit_code': run.returncode, 'output': run.stdout + run.stderr})
failed = [item for item in results if item.get('build_exit_code', item.get('exit_code', 1))]
report = {'passed': not failed, 'tests': results, 'failed': len(failed), 'firmware_ui_verified': False}
output = ROOT / 'evidence/host-tests.json'
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps(report, indent=2) + '\n')
for item in results:
    print(('FAIL' if item.get('build_exit_code', item.get('exit_code', 1)) else 'PASS'), item['test'])
    if item in failed:
        print(item['output'])
print(output)
sys.exit(bool(failed))
