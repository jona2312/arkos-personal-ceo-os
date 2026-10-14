"""Build a byte-reproducible, allowlisted ZIP from committed Git blobs only."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def build(output):
    sha = git('rev-parse', 'HEAD').decode().strip()
    spec = json.loads(git('show', f'{sha}:packaging/windows-pilot.json'))
    payload = {}
    for name in spec['files']:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or name in payload:
            raise ValueError('Invalid or duplicate package path')
        mode = git('ls-tree', sha, '--', name).decode().split()[0]
        if mode != '100644':
            raise ValueError('Only regular committed files are allowed')
        payload[name] = git('show', f'{sha}:{name}')
    manifest = dict(schema_version=1, version=spec['version'], source_commit=sha,
                    dependencies=spec['dependencies'], cloud_enabled=False,
                    files=[dict(path=n, bytes=len(b), sha256=hashlib.sha256(b).hexdigest())
                           for n, b in sorted(payload.items())])
    payload['MANIFEST.json'] = (json.dumps(manifest, indent=2, ensure_ascii=True) + '\n').encode()
    payload['SHA256SUMS.txt'] = ''.join(
        f'{hashlib.sha256(b).hexdigest()}  {n}\n' for n, b in sorted(payload.items())).encode()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"arkos-windows-pilot-{spec['version']}-{sha[:12]}.zip"
    # Stored entries avoid zlib-version differences across Linux and Windows.
    with archive.open('xb') as stream, zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as z:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{checksum}  {archive.name}\n', encoding='ascii', newline='\n')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(build(parser.parse_args().output))
