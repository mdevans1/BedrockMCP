import subprocess
import sys

EXTRACT_OPENAPI = [sys.executable, "extract_openapi_endpoints.py"]
EXTRACT_MCP = [sys.executable, "extract_mcp_functions.py"]
OPENAPI_JSON = "openapi_endpoints.json"
MCP_JSON = "mcp_functions.json"
COVERAGE_TEST = "test_api_coverage.py"


def run_and_save(cmd, outfile):
    print(f"Running: {' '.join(cmd)} > {outfile}")
    with open(outfile, "w", encoding="utf-8") as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(f"Error running {' '.join(cmd)}:")
        print(result.stderr)
        sys.exit(result.returncode)


DEFAULT_SERVER = "localhost"
DEFAULT_PORT = 11325


def main():
    server = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SERVER
    port = sys.argv[2] if len(sys.argv) > 2 else str(DEFAULT_PORT)
    run_and_save(EXTRACT_OPENAPI + [server, port], OPENAPI_JSON)
    run_and_save(EXTRACT_MCP, MCP_JSON)
    print(f"\nRunning pytest on {COVERAGE_TEST}...\n")
    code = subprocess.call([sys.executable, "-m", "pytest", COVERAGE_TEST])
    sys.exit(code)


if __name__ == "__main__":
    main() 