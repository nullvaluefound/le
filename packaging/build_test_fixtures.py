"""Real native old-version and failing-upgrade executables, used only in tests."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
output = root / 'build/test-fixtures'
output.mkdir(parents=True, exist_ok=True)
for name in ['old-version', 'failed-upgrade']:
    if os.name == 'nt':
        source = output / (name + '.py')
        text = 'import sys\nfrom pathlib import Path\n'
        if name == 'failed-upgrade':
            text += 'if Path(sys.executable).name.lower() == "le.exe":\n    raise SystemExit(23)\n'
        text += 'print("le installer test fixture 0.9.0")\n'
        source.write_text(text, encoding='utf-8')
        with tempfile.TemporaryDirectory(prefix='le-fixture-build-') as temporary:
            subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--noupx',
                            '--name', name, '--distpath', str(output), '--workpath', temporary,
                            '--specpath', temporary, str(source)], check=True)
    else:
        source = output / (name + '.c')
        text = '#include <stdio.h>\n#include <string.h>\nint main(int argc,char **argv){'
        if name == 'failed-upgrade':
            text += 'if(!strstr(argv[0],"le-install.")) return 23;'
        text += 'puts("le installer test fixture 0.9.0");return 0;}\n'
        source.write_text(text, encoding='utf-8')
        subprocess.run(['cc', '-O2', '-o', str(output / name), str(source)], check=True)
