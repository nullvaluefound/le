#!/usr/bin/env python3
import stat
import datetime
import os
import pathlib
import argparse
import enum
import json
import tempfile
from colorama import Fore, Style, init

# Initialize colorama (important for Windows support)
init(autoreset=True)

class FileIcon(enum.Enum):
  # Directories
  FOLDER_CLOSED = "📁"
  FOLDER_OPEN = "📂"

  # Generic Fallback
  GENERIC_FILE = "📄"

  # Code & Development
  PYTHON = "🐍"
  JAVASCRIPT = "🟨"
  HTML = "🌐"
  CSS = "🎨"
  CONFIG = "⚙️"  # .json, .yaml, .ini, .toml
  POWERSHELL = f"⚡{Fore.CYAN+Style.BRIGHT}>"

  # Documents & Data
  SPREADSHEET = "📊"  # .xlsx, .xls, .csv (Perfect for Stock Reports!)
  TEXT = "📝"  # .txt, .md
  PDF = "📕"

  # Media
  IMAGE = "🖼️"  # .png, .jpg, .jpeg, .gif, .svg
  VIDEO = "🎬"  # .mp4, .mkv, .avi
  AUDIO = "🎵"  # .mp3, .wav, .flac

  # Compressed Archives
  ZIP = "🗜️"  # .zip, .tar, .gz, .rar


  # Additional file types
  RUST = "🦀"
  GO = "🐹"
  C_CPP = "🔧"
  CSHARP = "💠"
  JAVA = "☕"
  RUBY = "💎"
  PHP = "🐘"
  SHELL = "🐚"
  WINDOWS_PROGRAM = "🖥️"
  NOTEBOOK = "📓"
  DATABASE = "🗃️"
  DATA = "🧮"
  DOCUMENT = "📘"
  PRESENTATION = "📈"
  LOG = "🧾"
  FONT = "🔤"
  CERTIFICATE = "🔐"
  PACKAGE = "📦"
  LIBRARY = "🧩"
  DISK_IMAGE = "💿"
  KOTLIN = "🟪"
  SWIFT = "🐦"
  DART = "🎯"
  LUA = "🌙"
  R_LANG = "®️"
  SCALA = "🟥"
  PERL = "🐪"
  ELIXIR = "💧"
  ERLANG = "☎️"
  HASKELL = "🧠"
  CLOJURE = "🟢"
  SCIENTIFIC_CODE = "🔬"
  ASSEMBLY = "🔩"
  SOURCE_CODE = "💻"
  WEB_TEMPLATE = "🧱"
  ML_MODEL = "🤖"
  CAD = "📐"
  MODEL_3D = "🧊"
  DESIGN = "✏️"
  EBOOK = "📚"
  TYPESETTING = "📜"
  SUBTITLE = "💬"
  MUSIC_SCORE = "🎼"
  GEOGRAPHIC = "🗺️"
  CALENDAR = "📅"
  EMAIL = "✉️"
  BACKUP = "💾"
  TEMPORARY = "⏳"
  LOCK = "🔒"
  CONTAINER = "🐳"
  BUILD = "🏗️"
  GIT = "🌱"
  README = "📖"
  LICENSE = "⚖️"
  CHANGELOG = "📰"

  @classmethod
  def get_icon(cls, path_item: pathlib.Path) -> str:
    """Extrapolates the correct emoticon based on directory status or file extension."""
    # 1. Handle Directories immediately
    if path_item.is_dir():
      return cls.FOLDER_CLOSED.value

    return cls._for_file(path_item)

  @classmethod
  def _for_file(cls, path_item: pathlib.Path) -> str:
    """Match special filenames before extensions, without another stat call."""
    name = path_item.name.lower()
    icon = _FILENAME_ICONS.get(name)
    if icon is None:
      if name.startswith('.env.'):
        icon = cls.CONFIG
      else:
        prefix, separator, _ = name.partition('.')
        if separator:
          icon = _FILENAME_PREFIX_ICONS.get(prefix)
    if icon is None:
      icon = _SUFFIX_ICONS.get(path_item.suffix.lower(), cls.GENERIC_FILE)
    return icon.value


_SUFFIX_ICONS = {
    ".py": FileIcon.PYTHON,
    ".pyw": FileIcon.PYTHON,
    ".pyc": FileIcon.PYTHON,
    ".ps1": FileIcon.POWERSHELL,
    ".psd1": FileIcon.POWERSHELL,
    ".psm": FileIcon.POWERSHELL,
    ".js": FileIcon.JAVASCRIPT,
    ".ts": FileIcon.JAVASCRIPT,
    ".html": FileIcon.HTML,
    ".htm": FileIcon.HTML,
    ".css": FileIcon.CSS,
    ".json": FileIcon.CONFIG,
    ".yaml": FileIcon.CONFIG,
    ".yml": FileIcon.CONFIG,
    ".ini": FileIcon.CONFIG,
    ".toml": FileIcon.CONFIG,
    ".csv": FileIcon.SPREADSHEET,
    ".xlsx": FileIcon.SPREADSHEET,
    ".xls": FileIcon.SPREADSHEET,
    ".txt": FileIcon.TEXT,
    ".md": FileIcon.TEXT,
    ".pdf": FileIcon.PDF,
    ".png": FileIcon.IMAGE,
    ".jpg": FileIcon.IMAGE,
    ".jpeg": FileIcon.IMAGE,
    ".gif": FileIcon.IMAGE,
    ".svg": FileIcon.IMAGE,
    ".mp4": FileIcon.VIDEO,
    ".mkv": FileIcon.VIDEO,
    ".mp3": FileIcon.AUDIO,
    ".wav": FileIcon.AUDIO,
    ".zip": FileIcon.ZIP,
    ".tar": FileIcon.ZIP,
    ".gz": FileIcon.ZIP,
    ".rar": FileIcon.ZIP,
    # Rust
    ".rs": FileIcon.RUST,
    # Go
    ".go": FileIcon.GO,
    # C Cpp
    ".c": FileIcon.C_CPP,
    ".h": FileIcon.C_CPP,
    ".cpp": FileIcon.C_CPP,
    ".cc": FileIcon.C_CPP,
    ".cxx": FileIcon.C_CPP,
    ".hpp": FileIcon.C_CPP,
    # Csharp
    ".cs": FileIcon.CSHARP,
    ".csx": FileIcon.CSHARP,
    # Java
    ".java": FileIcon.JAVA,
    ".class": FileIcon.JAVA,
    ".jar": FileIcon.JAVA,
    # Ruby
    ".rb": FileIcon.RUBY,
    ".rake": FileIcon.RUBY,
    ".gemspec": FileIcon.RUBY,
    # Php
    ".php": FileIcon.PHP,
    ".phtml": FileIcon.PHP,
    # Shell
    ".sh": FileIcon.SHELL,
    ".bash": FileIcon.SHELL,
    ".zsh": FileIcon.SHELL,
    ".fish": FileIcon.SHELL,
    # Windows Program
    ".bat": FileIcon.WINDOWS_PROGRAM,
    ".cmd": FileIcon.WINDOWS_PROGRAM,
    ".exe": FileIcon.WINDOWS_PROGRAM,
    ".com": FileIcon.WINDOWS_PROGRAM,
    # Notebook
    ".ipynb": FileIcon.NOTEBOOK,
    # Database
    ".db": FileIcon.DATABASE,
    ".sqlite": FileIcon.DATABASE,
    ".sqlite3": FileIcon.DATABASE,
    ".sql": FileIcon.DATABASE,
    # Data
    ".parquet": FileIcon.DATA,
    ".arrow": FileIcon.DATA,
    ".feather": FileIcon.DATA,
    ".avro": FileIcon.DATA,
    ".jsonl": FileIcon.DATA,
    ".ndjson": FileIcon.DATA,
    ".h5": FileIcon.DATA,
    ".hdf5": FileIcon.DATA,
    ".nc": FileIcon.DATA,
    ".npy": FileIcon.DATA,
    ".npz": FileIcon.DATA,
    ".pkl": FileIcon.DATA,
    ".pickle": FileIcon.DATA,
    ".mat": FileIcon.DATA,
    # Document
    ".doc": FileIcon.DOCUMENT,
    ".docx": FileIcon.DOCUMENT,
    ".odt": FileIcon.DOCUMENT,
    ".rtf": FileIcon.DOCUMENT,
    # Presentation
    ".ppt": FileIcon.PRESENTATION,
    ".pptx": FileIcon.PRESENTATION,
    ".odp": FileIcon.PRESENTATION,
    # Log
    ".log": FileIcon.LOG,
    # Font
    ".ttf": FileIcon.FONT,
    ".otf": FileIcon.FONT,
    ".woff": FileIcon.FONT,
    ".woff2": FileIcon.FONT,
    # Certificate
    ".pem": FileIcon.CERTIFICATE,
    ".crt": FileIcon.CERTIFICATE,
    ".cer": FileIcon.CERTIFICATE,
    ".key": FileIcon.CERTIFICATE,
    ".pfx": FileIcon.CERTIFICATE,
    ".p12": FileIcon.CERTIFICATE,
    # Package
    ".msi": FileIcon.PACKAGE,
    ".msix": FileIcon.PACKAGE,
    ".deb": FileIcon.PACKAGE,
    ".rpm": FileIcon.PACKAGE,
    ".apk": FileIcon.PACKAGE,
    ".whl": FileIcon.PACKAGE,
    ".appx": FileIcon.PACKAGE,
    ".appxbundle": FileIcon.PACKAGE,
    ".msixbundle": FileIcon.PACKAGE,
    ".gem": FileIcon.PACKAGE,
    ".nupkg": FileIcon.PACKAGE,
    ".vsix": FileIcon.PACKAGE,
    ".crx": FileIcon.PACKAGE,
    ".xpi": FileIcon.PACKAGE,
    # Library
    ".dll": FileIcon.LIBRARY,
    ".so": FileIcon.LIBRARY,
    ".dylib": FileIcon.LIBRARY,
    ".lib": FileIcon.LIBRARY,
    ".a": FileIcon.LIBRARY,
    ".o": FileIcon.LIBRARY,
    ".pyo": FileIcon.LIBRARY,
    ".wasm": FileIcon.LIBRARY,
    # Disk Image
    ".iso": FileIcon.DISK_IMAGE,
    ".img": FileIcon.DISK_IMAGE,
    ".vhd": FileIcon.DISK_IMAGE,
    ".vhdx": FileIcon.DISK_IMAGE,
    ".vmdk": FileIcon.DISK_IMAGE,
    ".qcow": FileIcon.DISK_IMAGE,
    ".qcow2": FileIcon.DISK_IMAGE,
    ".vdi": FileIcon.DISK_IMAGE,
    ".dmg": FileIcon.DISK_IMAGE,
    # Javascript
    ".jsx": FileIcon.JAVASCRIPT,
    ".tsx": FileIcon.JAVASCRIPT,
    ".mjs": FileIcon.JAVASCRIPT,
    ".cjs": FileIcon.JAVASCRIPT,
    # Css
    ".scss": FileIcon.CSS,
    ".sass": FileIcon.CSS,
    ".less": FileIcon.CSS,
    ".styl": FileIcon.CSS,
    ".stylus": FileIcon.CSS,
    # Config
    ".xml": FileIcon.CONFIG,
    ".cfg": FileIcon.CONFIG,
    ".conf": FileIcon.CONFIG,
    ".properties": FileIcon.CONFIG,
    ".jsonc": FileIcon.CONFIG,
    ".json5": FileIcon.CONFIG,
    ".hcl": FileIcon.CONFIG,
    ".tf": FileIcon.CONFIG,
    ".tfvars": FileIcon.CONFIG,
    ".nix": FileIcon.CONFIG,
    # Spreadsheet
    ".xlsm": FileIcon.SPREADSHEET,
    ".xlsb": FileIcon.SPREADSHEET,
    ".ods": FileIcon.SPREADSHEET,
    ".tsv": FileIcon.SPREADSHEET,
    ".numbers": FileIcon.SPREADSHEET,
    ".tab": FileIcon.SPREADSHEET,
    # Text
    ".rst": FileIcon.TEXT,
    ".adoc": FileIcon.TEXT,
    # Image
    ".webp": FileIcon.IMAGE,
    ".avif": FileIcon.IMAGE,
    ".bmp": FileIcon.IMAGE,
    ".ico": FileIcon.IMAGE,
    ".tif": FileIcon.IMAGE,
    ".tiff": FileIcon.IMAGE,
    ".heic": FileIcon.IMAGE,
    ".apng": FileIcon.IMAGE,
    ".jfif": FileIcon.IMAGE,
    ".jxl": FileIcon.IMAGE,
    ".heif": FileIcon.IMAGE,
    ".raw": FileIcon.IMAGE,
    ".dng": FileIcon.IMAGE,
    ".cr2": FileIcon.IMAGE,
    ".cr3": FileIcon.IMAGE,
    ".nef": FileIcon.IMAGE,
    ".arw": FileIcon.IMAGE,
    # Video
    ".avi": FileIcon.VIDEO,
    ".mov": FileIcon.VIDEO,
    ".webm": FileIcon.VIDEO,
    ".m4v": FileIcon.VIDEO,
    ".mpeg": FileIcon.VIDEO,
    ".mpg": FileIcon.VIDEO,
    ".wmv": FileIcon.VIDEO,
    ".m2ts": FileIcon.VIDEO,
    ".mts": FileIcon.VIDEO,
    ".vob": FileIcon.VIDEO,
    ".ogv": FileIcon.VIDEO,
    ".3gp": FileIcon.VIDEO,
    ".flv": FileIcon.VIDEO,
    # Audio
    ".flac": FileIcon.AUDIO,
    ".ogg": FileIcon.AUDIO,
    ".opus": FileIcon.AUDIO,
    ".aac": FileIcon.AUDIO,
    ".m4a": FileIcon.AUDIO,
    ".aiff": FileIcon.AUDIO,
    ".wma": FileIcon.AUDIO,
    ".aif": FileIcon.AUDIO,
    ".alac": FileIcon.AUDIO,
    ".ape": FileIcon.AUDIO,
    ".amr": FileIcon.AUDIO,
    # Zip
    ".7z": FileIcon.ZIP,
    ".bz2": FileIcon.ZIP,
    ".xz": FileIcon.ZIP,
    ".zst": FileIcon.ZIP,
    ".tgz": FileIcon.ZIP,
    ".tbz2": FileIcon.ZIP,
    ".txz": FileIcon.ZIP,
    ".lz": FileIcon.ZIP,
    ".lzma": FileIcon.ZIP,
    ".lz4": FileIcon.ZIP,
    ".bz": FileIcon.ZIP,
    ".bzip2": FileIcon.ZIP,
    ".cab": FileIcon.ZIP,
    ".z": FileIcon.ZIP,
    # Kotlin
    ".kt": FileIcon.KOTLIN,
    ".kts": FileIcon.KOTLIN,
    # Swift
    ".swift": FileIcon.SWIFT,
    # Dart
    ".dart": FileIcon.DART,
    # Lua
    ".lua": FileIcon.LUA,
    # R Lang
    ".r": FileIcon.R_LANG,
    ".rmd": FileIcon.R_LANG,
    ".rproj": FileIcon.R_LANG,
    ".rds": FileIcon.R_LANG,
    ".rdata": FileIcon.R_LANG,
    # Scala
    ".scala": FileIcon.SCALA,
    ".sc": FileIcon.SCALA,
    # Perl
    ".pl": FileIcon.PERL,
    ".pm": FileIcon.PERL,
    # Elixir
    ".ex": FileIcon.ELIXIR,
    ".exs": FileIcon.ELIXIR,
    # Erlang
    ".erl": FileIcon.ERLANG,
    ".hrl": FileIcon.ERLANG,
    # Haskell
    ".hs": FileIcon.HASKELL,
    ".lhs": FileIcon.HASKELL,
    # Clojure
    ".clj": FileIcon.CLOJURE,
    ".cljs": FileIcon.CLOJURE,
    ".cljc": FileIcon.CLOJURE,
    ".edn": FileIcon.CLOJURE,
    # Scientific Code
    ".jl": FileIcon.SCIENTIFIC_CODE,
    ".f": FileIcon.SCIENTIFIC_CODE,
    ".for": FileIcon.SCIENTIFIC_CODE,
    ".f90": FileIcon.SCIENTIFIC_CODE,
    ".f95": FileIcon.SCIENTIFIC_CODE,
    # Assembly
    ".asm": FileIcon.ASSEMBLY,
    ".s": FileIcon.ASSEMBLY,
    # Source Code
    ".zig": FileIcon.SOURCE_CODE,
    ".nim": FileIcon.SOURCE_CODE,
    ".v": FileIcon.SOURCE_CODE,
    ".ml": FileIcon.SOURCE_CODE,
    ".mli": FileIcon.SOURCE_CODE,
    ".pas": FileIcon.SOURCE_CODE,
    ".fs": FileIcon.SOURCE_CODE,
    ".fsx": FileIcon.SOURCE_CODE,
    # Web Template
    ".vue": FileIcon.WEB_TEMPLATE,
    ".svelte": FileIcon.WEB_TEMPLATE,
    ".astro": FileIcon.WEB_TEMPLATE,
    ".ejs": FileIcon.WEB_TEMPLATE,
    ".hbs": FileIcon.WEB_TEMPLATE,
    ".mustache": FileIcon.WEB_TEMPLATE,
    ".jinja": FileIcon.WEB_TEMPLATE,
    ".jinja2": FileIcon.WEB_TEMPLATE,
    # Ml Model
    ".onnx": FileIcon.ML_MODEL,
    ".pt": FileIcon.ML_MODEL,
    ".pth": FileIcon.ML_MODEL,
    ".safetensors": FileIcon.ML_MODEL,
    ".gguf": FileIcon.ML_MODEL,
    ".tflite": FileIcon.ML_MODEL,
    ".keras": FileIcon.ML_MODEL,
    # Cad
    ".dwg": FileIcon.CAD,
    ".dxf": FileIcon.CAD,
    ".step": FileIcon.CAD,
    ".stp": FileIcon.CAD,
    ".iges": FileIcon.CAD,
    ".igs": FileIcon.CAD,
    ".scad": FileIcon.CAD,
    # Model 3D
    ".obj": FileIcon.MODEL_3D,
    ".stl": FileIcon.MODEL_3D,
    ".fbx": FileIcon.MODEL_3D,
    ".gltf": FileIcon.MODEL_3D,
    ".glb": FileIcon.MODEL_3D,
    ".blend": FileIcon.MODEL_3D,
    ".3mf": FileIcon.MODEL_3D,
    ".usd": FileIcon.MODEL_3D,
    ".usdz": FileIcon.MODEL_3D,
    # Design
    ".psd": FileIcon.DESIGN,
    ".psb": FileIcon.DESIGN,
    ".ai": FileIcon.DESIGN,
    ".eps": FileIcon.DESIGN,
    ".xcf": FileIcon.DESIGN,
    ".kra": FileIcon.DESIGN,
    ".sketch": FileIcon.DESIGN,
    ".fig": FileIcon.DESIGN,
    # Ebook
    ".epub": FileIcon.EBOOK,
    ".mobi": FileIcon.EBOOK,
    ".azw": FileIcon.EBOOK,
    ".azw3": FileIcon.EBOOK,
    ".djvu": FileIcon.EBOOK,
    # Typesetting
    ".tex": FileIcon.TYPESETTING,
    ".bib": FileIcon.TYPESETTING,
    ".typ": FileIcon.TYPESETTING,
    # Subtitle
    ".srt": FileIcon.SUBTITLE,
    ".vtt": FileIcon.SUBTITLE,
    ".ass": FileIcon.SUBTITLE,
    ".ssa": FileIcon.SUBTITLE,
    ".sub": FileIcon.SUBTITLE,
    ".sbv": FileIcon.SUBTITLE,
    # Music Score
    ".mid": FileIcon.MUSIC_SCORE,
    ".midi": FileIcon.MUSIC_SCORE,
    ".musicxml": FileIcon.MUSIC_SCORE,
    ".mxl": FileIcon.MUSIC_SCORE,
    # Geographic
    ".geojson": FileIcon.GEOGRAPHIC,
    ".gpx": FileIcon.GEOGRAPHIC,
    ".kml": FileIcon.GEOGRAPHIC,
    ".kmz": FileIcon.GEOGRAPHIC,
    ".shp": FileIcon.GEOGRAPHIC,
    ".gpkg": FileIcon.GEOGRAPHIC,
    ".osm": FileIcon.GEOGRAPHIC,
    ".mbtiles": FileIcon.GEOGRAPHIC,
    # Calendar
    ".ics": FileIcon.CALENDAR,
    ".ical": FileIcon.CALENDAR,
    ".vcf": FileIcon.CALENDAR,
    # Email
    ".eml": FileIcon.EMAIL,
    ".msg": FileIcon.EMAIL,
    ".mbox": FileIcon.EMAIL,
    ".pst": FileIcon.EMAIL,
    ".ost": FileIcon.EMAIL,
    # Backup
    ".bak": FileIcon.BACKUP,
    ".backup": FileIcon.BACKUP,
    ".old": FileIcon.BACKUP,
    ".orig": FileIcon.BACKUP,
    # Temporary
    ".tmp": FileIcon.TEMPORARY,
    ".temp": FileIcon.TEMPORARY,
    ".part": FileIcon.TEMPORARY,
    ".crdownload": FileIcon.TEMPORARY,
    ".swp": FileIcon.TEMPORARY,
    # Lock
    ".lock": FileIcon.LOCK,
    ".lck": FileIcon.LOCK,
}


_FILENAME_ICONS = {
    "dockerfile": FileIcon.CONTAINER,
    "containerfile": FileIcon.CONTAINER,
    ".dockerignore": FileIcon.CONTAINER,
    "makefile": FileIcon.BUILD,
    "gnumakefile": FileIcon.BUILD,
    "cmakelists.txt": FileIcon.BUILD,
    ".gitignore": FileIcon.GIT,
    ".gitattributes": FileIcon.GIT,
    ".gitmodules": FileIcon.GIT,
    ".env": FileIcon.CONFIG,
    ".editorconfig": FileIcon.CONFIG,
    "readme": FileIcon.README,
    "license": FileIcon.LICENSE,
    "copying": FileIcon.LICENSE,
    "changelog": FileIcon.CHANGELOG,
}

_FILENAME_PREFIX_ICONS = {
    "readme": FileIcon.README,
    "license": FileIcon.LICENSE,
    "copying": FileIcon.LICENSE,
    "changelog": FileIcon.CHANGELOG,
}


class _WindowsOwnerLookup:
    """Read owners without starting PowerShell for every entry (stdlib only)."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes
        advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        pointer = ctypes.c_void_p
        pointer_out = ctypes.POINTER(pointer)
        dword_out = ctypes.POINTER(wintypes.DWORD)

        self.get_security = advapi.GetNamedSecurityInfoW
        self.get_security.argtypes = [wintypes.LPCWSTR, ctypes.c_int,
                                     wintypes.DWORD] + [pointer_out] * 5
        self.get_security.restype = wintypes.DWORD
        self.sid_length = advapi.GetLengthSid
        self.sid_length.argtypes = [pointer]
        self.sid_length.restype = wintypes.DWORD
        self.lookup_sid = advapi.LookupAccountSidW
        self.lookup_sid.argtypes = [wintypes.LPCWSTR, pointer, wintypes.LPWSTR,
                                   dword_out, wintypes.LPWSTR, dword_out, dword_out]
        self.lookup_sid.restype = wintypes.BOOL
        self.free = kernel.LocalFree
        self.free.argtypes = [pointer]
        self.free.restype = pointer
        self.accounts = {}

    def __call__(self, path):
        ctypes = self.ctypes
        sid = ctypes.c_void_p()
        descriptor = ctypes.c_void_p()
        # SE_FILE_OBJECT = 1; OWNER_SECURITY_INFORMATION = 1.
        error = self.get_security(str(path), 1, 1, ctypes.byref(sid),
                                  None, None, None, ctypes.byref(descriptor))
        try:
            if error:
                raise ctypes.WinError(error)
            if not sid:
                raise OSError('The security descriptor has no owner')
            sid_key = ctypes.string_at(sid, self.sid_length(sid))
            if sid_key in self.accounts:
                return self.accounts[sid_key]

            name_size = self.wintypes.DWORD()
            domain_size = self.wintypes.DWORD()
            sid_type = self.wintypes.DWORD()
            self.lookup_sid(None, sid, None, ctypes.byref(name_size),
                            None, ctypes.byref(domain_size), ctypes.byref(sid_type))
            if ctypes.get_last_error() != 122:  # ERROR_INSUFFICIENT_BUFFER
                raise ctypes.WinError(ctypes.get_last_error())
            name = ctypes.create_unicode_buffer(name_size.value)
            domain = ctypes.create_unicode_buffer(domain_size.value)
            if not self.lookup_sid(None, sid, name, ctypes.byref(name_size),
                                   domain, ctypes.byref(domain_size), ctypes.byref(sid_type)):
                raise ctypes.WinError(ctypes.get_last_error())
            owner = f'{domain.value}\\{name.value}' if domain.value else name.value
            # The legacy PowerShell pipe uses the Windows OEM encoding. Fall
            # back for non-ASCII accounts rather than changing its output.
            if not owner.isascii():
                raise OSError('Use legacy encoding for this account name')
            self.accounts[sid_key] = owner
            return owner
        finally:
            if descriptor:
                self.free(descriptor)

  

_SIZE_UNITS = (
    (1024 ** 10, 'NB'), (1024 ** 9, 'BB'), (1024 ** 8, 'YB'),
    (1024 ** 7, 'ZB'), (1024 ** 6, 'EB'), (1024 ** 5, 'PB'),
    (1024 ** 4, 'TB'), (1024 ** 3, 'GB'), (1024 ** 2, 'MB'),
    (1024, 'KB'),
)


def _format_size(size):
    # Strict > thresholds and round() preserve the original boundary output.
    if size > 1024 ** 11:
        return 'Could not calculate size'
    for threshold, unit in _SIZE_UNITS:
        if size > threshold:
            return f'{round(size / threshold, 2)} {unit}'
    return f'{size} B'


class DirectoryTraversal:
    def __init__(self,
                 path_to_dir=os.curdir,
                 recurse=False,
                 is_root=True,
                 dirs_only=False,
                 show_owner=False,
                 show_time=False,
                 show_permissions=False,
                 show_size=False,
                 time_zone='local',
                 max_depth=None):
        self.path_to_dir = pathlib.Path(path_to_dir).resolve()
        self.recurse = recurse
        self.root = is_root
        self.dirs_only = dirs_only  # Default value; can be set later if needed
        self.show_owner = show_owner
        self.show_time = show_time
        self.show_permissions = show_permissions
        self.show_size = show_size
        self.time_zone = time_zone  # Default to local timezone; can be set later if needed
        self.max_depth = max_depth if recurse else None


    def get_file_owner(self, path_obj: pathlib.Path) -> str:
        try:
            return path_obj.owner()  # Works perfectly on Mac/Linux
        except (AttributeError, NotImplementedError):
            if os.name == 'nt':
                # Preserve the legacy Get-Acl behavior for PowerShell patterns,
                # quoted paths, reparse points, and native lookup failures.
                lookup = getattr(self, '_owner_lookup', None)
                candidate = None
                try:
                    if lookup is not False and not any(char in str(path_obj) for char in "'`$[]?*"):
                        attributes = path_obj.lstat().st_file_attributes
                        if not attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                            native_lookup = lookup if lookup is not None else _WindowsOwnerLookup()
                            native_owner = native_lookup(path_obj)
                            if lookup is not None:
                                return native_owner
                            candidate = native_lookup
                except (OSError, AttributeError):
                    pass
                import subprocess
                cmd = f'powershell -Command "(Get-Acl \'{path_obj}\').Owner"'
                res = subprocess.run(cmd, capture_output=True, text=True, shell=True)
                owner = res.stdout.strip()
                if candidate is not None:
                    # Validate once per run: missing PowerShell modules or a
                    # customized environment must keep their original output.
                    self._owner_lookup = candidate if owner == native_owner else False
                return owner
            return "Unknown"
    
    @staticmethod
    def _directory_size(directory, cache):
        """Cache all visited subtree totals without following directory symlinks.

        Keep pathlib's glob semantics, including hidden files, file symlinks,
        and its handling of unreadable directories. Cache only for this run.
        """
        if directory in cache:
            return cache[directory]
        totals = {directory: 0}
        for child in directory.rglob('*'):
            totals.setdefault(child.parent, 0)
            if child.is_file():
                totals[child.parent] += child.stat().st_size
        for path in sorted(totals, key=lambda path: len(path.parts), reverse=True):
            if path != directory:
                totals[path.parent] += totals[path]
        cache.update(totals)
        return totals[directory]

    def traverse(self, counter=0):
        # A fresh cache makes repeated calls reflect changes on disk.
        self.__dict__.pop('_owner_lookup', None)
        self._traverse(counter, {})

    def record_directory(self, output_path):
        """Print and save [{folder: [filename, {subfolder: [...]}]}] as JSON.

        Follow the listing's recursion, depth, and directory-only options.
        The export itself is excluded, and cyclic directory links are leaves.
        Return the same structure that was saved.
        """
        destination = pathlib.Path(output_path).expanduser().resolve()
        if destination.is_dir():
            raise IsADirectoryError(f'JSON output path is a directory: {destination}')
        self.__dict__.pop('_owner_lookup', None)
        children = []
        self._traverse(0, {}, children, destination, {self.path_to_dir})
        structure = [{str(self.path_to_dir): children}]
        self._write_json(destination, structure)
        return structure

    @staticmethod
    def _write_json(destination, structure):
        # Replace only after a complete export, keeping any existing file intact
        # if serializing or writing the new content fails.
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                    mode='w', encoding='utf-8', newline='\n',
                    dir=destination.parent, prefix='.directory-tree-',
                    suffix='.tmp', delete=False) as stream:
                temporary = pathlib.Path(stream.name)
                json.dump(structure, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _traverse(self, counter, size_cache, json_nodes=None,
                  output_path=None, ancestors=None):
        if self.root and counter == 0:
            print(f"{Fore.RED+Style.DIM}================", end=' ')
            print(f"📁  {Fore.LIGHTGREEN_EX+Style.BRIGHT}{self.path_to_dir} {Fore.RED+Style.DIM}================")

        # Root is depth 0; each displayed child is one level deeper.
        if self.recurse and self.max_depth is not None and counter >= self.max_depth:
            return

        tabs = '  ' * counter if self.root else '│  ' * counter
        tree_color = Fore.LIGHTGREEN_EX + Style.BRIGHT
        file_color = Fore.MAGENTA + Style.BRIGHT
        folder_color = Fore.BLUE + Style.BRIGHT
        detail_color = Fore.YELLOW + Style.DIM
        need_stats = self.show_permissions or self.show_time or self.show_size

        # Path.iterdir preserves the original filesystem order. Materialize it
        # once, instead of enumerating the entire directory for every entry.
        items = list(self.path_to_dir.iterdir())
        last_index = len(items) - 1
        for index, item in enumerate(items):
            is_directory = item.is_dir()
            icon = (FileIcon.FOLDER_CLOSED.value if is_directory else
                    FileIcon._for_file(item))
            stats = item.stat() if need_stats else None
            size_part = ''
            if self.show_size:
                size = (self._directory_size(item, size_cache)
                        if is_directory else stats.st_size)
                size_part = f'{detail_color} {_format_size(size)}'

            mod_time = ''
            if self.show_time:
                tz = (datetime.timezone.utc if self.time_zone == 'utc' else
                      datetime.datetime.now().astimezone().tzinfo)
                mod_time = datetime.datetime.fromtimestamp(stats.st_mtime, tz=tz).strftime('%Y-%m-%d %H:%M:%S')

            permissions_part = ''
            if self.show_permissions or self.show_owner or self.show_time:
                permissions = stat.filemode(stats.st_mode) if self.show_permissions else ''
                owner = self.get_file_owner(item) if self.show_owner else ''
                detail = f'{owner}: {permissions}' if self.show_owner and self.show_permissions else owner or permissions
                if self.show_time:
                    # Keep the separator even if an owner lookup returns ''.
                    detail = (f'{mod_time} - {detail}'
                              if self.show_owner or self.show_permissions else mod_time)
                permissions_part = f'{detail_color} {detail}  '

            across = '└──' if index == last_index else '├──'
            if is_directory:
                child_nodes = None
                if json_nodes is not None:
                    child_nodes = []
                    json_nodes.append({str(item): child_nodes})
                # Keep the existing path rendering and individual print calls;
                # Colorama's autoreset also depends on write boundaries.
                print(f'{tree_color}{tabs}{across}', end='')
                print(size_part, end='')
                print(f'{icon}  {folder_color}{pathlib.Path(item.name).resolve()}{os.sep}', end='')
                print(permissions_part)

                if self.recurse:
                    sub_traversal = DirectoryTraversal(
                        item, self.recurse,
                        is_root=self.root and index == last_index,
                        dirs_only=self.dirs_only, show_owner=self.show_owner,
                        show_permissions=self.show_permissions,
                        show_size=self.show_size, show_time=self.show_time,
                        time_zone=self.time_zone, max_depth=self.max_depth)
                    if hasattr(self, '_owner_lookup'):
                        sub_traversal._owner_lookup = self._owner_lookup
                    child_ancestors = None
                    if ancestors is not None:
                        if sub_traversal.path_to_dir in ancestors:
                            continue
                        child_ancestors = ancestors | {sub_traversal.path_to_dir}
                    sub_traversal._traverse(counter + 1, size_cache, child_nodes,
                                            output_path, child_ancestors)
            elif not self.dirs_only:
                if json_nodes is not None and item != output_path:
                    json_nodes.append(item.name)
                print(f'{tree_color}{tabs}{across}', end='')
                print(size_part, end='')
                print(f'{icon}  {file_color}{item.name}', end='')
                print(permissions_part)


def _parse_depth(value):
    try:
        depth = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('depth must be a non-negative integer') from None
    if depth < 0:
        raise argparse.ArgumentTypeError('depth must be a non-negative integer')
    return depth


def parse_arguments():
    parser = argparse.ArgumentParser(description="Directory Tree Printer.")
    # Add arguments to the parser
    # Make this a positional argument that's non-optional
    parser.add_argument('path_to_dir', nargs='?', default='.', type=str, help='Input file path')
    parser.add_argument('-r', '--recurse', action='store_true', default=False, help='Recurse into subdirectories')
    parser.add_argument('-n', '--depth', type=_parse_depth, default=None, help='Limit recursion depth (root is 0; ignored without -r)')
    parser.add_argument('-d', '--only-dirs', action='store_true', default=False, help='Only print directories')
    parser.add_argument('-p', '--show-permissions', action='store_true', default=False, help='Show file permissions')
    parser.add_argument('-o', '--show-owner', action='store_true', default=False, help='Show file owner')
    parser.add_argument('-s','--show-size', action='store_true', default=False, help='Show file size')
    parser.add_argument('-t','--show-time', action='store_true', default=False, help='Show last modified time')
    parser.add_argument('--time-zone', choices=['local','utc'], default='local', help='Show time in UTC or local timezone (ignored if -T/--show-time is not set)')
    parser.add_argument('--output-json', metavar='PATH', type=pathlib.Path, help='Also save the directory hierarchy as JSON to PATH')
    parser.add_argument('-v', '--version', action='version', version='Directory Tree Printer 1.0')
    return parser.parse_args()
 
def main():
    args = parse_arguments()
    traversal = DirectoryTraversal(path_to_dir=args.path_to_dir, 
                                    recurse=args.recurse, 
                                    is_root=True,
                                    dirs_only=args.only_dirs,
                                    show_owner=args.show_owner,
                                    show_permissions=args.show_permissions,
                                    show_size=args.show_size,
                                    show_time=args.show_time,
                                    time_zone=args.time_zone,
                                    max_depth=args.depth
                                )
    if args.output_json is None:
        traversal.traverse()
    else:
        try:
            traversal.record_directory(args.output_json)
        except (OSError, ValueError) as error:
            raise SystemExit(f'Could not export JSON: {error}') from None

if __name__ == "__main__":
    main()
