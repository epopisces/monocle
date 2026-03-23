"""Quick test runner that writes results to a file."""
import subprocess, sys, os

os.chdir(r"e:\development\_agents\monocle")

result = subprocess.run(
    [sys.executable, "-m", "pytest",
     "monocle/tests/",
     "--tb=short", "--no-header", "-q"],
    capture_output=True,
    text=True,
    cwd=r"e:\development\_agents\monocle",
)

output = result.stdout + "\n---STDERR---\n" + result.stderr[-500:]
with open(r"e:\development\_agents\monocle\test_run_result.txt", "w", encoding="utf-8") as f:
    f.write(f"Exit code: {result.returncode}\n")
    f.write(output)

# Print summary lines
for line in output.splitlines():
    if any(x in line for x in ["passed", "failed", "error", "PASSED", "FAILED", "FAILED"]):
        print(line)
print(f"\nExit code: {result.returncode}")
