"""Run the native updater while preserving inputs and a bounded change receipt."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

root = Path.cwd()
source = root / '.github/scripts/update_docker_python_versions.py'
spec = importlib.util.spec_from_file_location('native_docker_update', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
dockerfiles = sorted(root.glob('docker/**/Dockerfile'))
targets = module.target_files(dockerfiles)
before = {str(p.relative_to(root)): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'text': p.read_text()} for p in targets}
available = module.fetch_available_versions()
current = module.discover_tracked_versions(dockerfiles)
replacements = module.build_replacement_map(current, available)
capture = {'native_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'available_versions': available, 'tracked_versions': current, 'replacements': replacements, 'before': before, 'input_origin': 'Original successful-run source tree plus fresh real CPython tag response; not an identical historical network replay', 'model_calls': 0}
Path('docker-input-capture.json').write_text(json.dumps(capture, indent=2) + '\n')
# Reuse the single preserved API response; native main and text transformation stay unchanged.
module.fetch_available_versions = lambda: available
sys.argv = [str(source), '--write']
if module.main() != 0:
    raise RuntimeError('Native updater failed')
changes = []
for p in targets:
    name = str(p.relative_to(root))
    text = p.read_text()
    if hashlib.sha256(p.read_bytes()).hexdigest() != before[name]['sha256']:
        changes.append({'path': name, 'content': text, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
tracked = subprocess.check_output(['git', 'diff', '--name-only'], text=True).splitlines()
if set(tracked) != {c['path'] for c in changes}:
    raise RuntimeError('Unexpected changes outside native target set')
Path('docker-update-result.json').write_text(json.dumps({'status': 'changes' if changes else 'noop', 'changes': changes, 'tracked_diff_paths': tracked, 'replacements': replacements, 'model_calls': 0}, indent=2) + '\n')
