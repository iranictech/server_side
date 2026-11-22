"""Build all Gold CSS, JS and image assets without changing other themes."""
from pathlib import Path
from shutil import copy2


def build():
    gold_dir = Path(__file__).resolve().parent
    static_root = gold_dir.parents[1] / 'static' / 'gold'
    assets = gold_dir / 'assets'
    for source in sorted(assets.rglob('*')):
        if not source.is_file():
            continue
        relative = source.relative_to(assets)
        if relative.as_posix() == 'css/chrome_patch.css':
            continue
        destination = static_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        copy2(source, destination)
    print('Gold assets built successfully.')
