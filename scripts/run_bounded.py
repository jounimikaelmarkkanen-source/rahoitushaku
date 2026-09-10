"""Run an integration-test process with a hard timeout (also works on macOS)."""
import subprocess
import sys

try:
    result = subprocess.run(sys.argv[2:], timeout=int(sys.argv[1]), check=False)
    sys.exit(result.returncode)
except subprocess.TimeoutExpired:
    print("Integration-test process timed out; test resources will be cleaned up.", file=sys.stderr)
    sys.exit(124)
