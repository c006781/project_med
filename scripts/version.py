# version.py
import sys
from pathlib import Path

VERSION_FILE = Path(__file__).parent.parent / "VERSION"

def read_version():
    return VERSION_FILE.read_text().strip()

def write_version(ver):
    VERSION_FILE.write_text(ver + "\n")

def bump(part):
    ver = read_version()
    major, minor, patch = map(int, ver.split('.'))
    if part == 'major':
        major += 1
        minor = 0
        patch = 0
    elif part == 'minor':
        minor += 1
        patch = 0
    elif part == 'patch':
        patch += 1
    else:
        print("Usage: patch | minor | major")
        sys.exit(1)
    new_ver = f"{major}.{minor}.{patch}"
    write_version(new_ver)
    print(f"Version bumped to {new_ver}")
    return new_ver

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python version.py {patch|minor|major}")
        sys.exit(1)
    bump(sys.argv[1])