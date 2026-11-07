"""Collect the actual licenses of the interpreter and bundled dependencies."""
import importlib.metadata
import os
from pathlib import Path
import sys
import sysconfig


def notices(root):
    sections = [('le — MIT', (root / 'LICENSE').read_text(encoding='utf-8'))]
    candidates = [Path(os.environ['PYTHON_LICENSE_FILE'])] if os.environ.get('PYTHON_LICENSE_FILE') else []
    candidates += [Path(sys.base_prefix) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE',
                   Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt', Path(sysconfig.get_path('stdlib')) / 'LICENSE']
    python_license = next((path for path in candidates if path.is_file()), None)
    if python_license is None:
        raise ValueError('Set PYTHON_LICENSE_FILE to the actual interpreter license text; it must accompany the bundled runtime.')
    sections.append(('Python ' + sys.version.split()[0], python_license.read_text(encoding='utf-8')))
    for package in ['colorama', 'pyinstaller']:
        distribution = importlib.metadata.distribution(package)
        paths = [path for path in distribution.files if any(word in str(path).lower() for word in ['license', 'copying']) and str(path).lower().endswith(('.txt', '.md'))]
        if not paths:
            raise ValueError('Missing bundled dependency license: ' + package)
        for path in paths:
            sections.append((package + ' ' + distribution.version + ' — ' + Path(str(path)).name,
                             Path(distribution.locate_file(path)).read_text(encoding='utf-8')))
    return '\n\n'.join(title + '\n' + '=' * len(title) + '\n\n' + text for title, text in sections) + '\n'
