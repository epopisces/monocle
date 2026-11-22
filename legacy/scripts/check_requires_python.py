"""
scripts/check_requires_python.py

Check all installed packages for Python version compatibility.
Prints packages whose Requires-Python constraint excludes the current interpreter.
"""
import importlib.metadata
import sys

import packaging.specifiers
import packaging.version

py_str = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
py_ver = packaging.version.Version(py_str)

print(f"Python: {py_str}\n")

issues = []
ok = []
for dist in importlib.metadata.distributions():
    name = dist.metadata["Name"]
    version = dist.metadata["Version"]
    rp = dist.metadata.get("Requires-Python", "")
    if not rp:
        continue
    try:
        spec = packaging.specifiers.SpecifierSet(rp)
        if py_ver not in spec:
            issues.append((name, version, rp))
        else:
            ok.append((name, version, rp))
    except Exception as e:
        print(f"PARSE ERROR: {name}=={version}: {e}")

if issues:
    print("INCOMPATIBLE packages:")
    for name, version, rp in sorted(set(issues)):
        print(f"  {name}=={version}  Requires-Python: {rp}")
else:
    print("No incompatibilities found — all packages satisfy Requires-Python for this interpreter.")

print(f"\n({len(ok)} packages with Requires-Python are compatible, {len(issues)} incompatible)")
