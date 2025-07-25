import json
import sys
from pathlib import Path

OPENAPI_PATH = Path("openapi.json")

def extract_endpoints(openapi_path):
    with open(openapi_path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    endpoints = []
    paths = spec.get("paths", {})
    for path, methods in paths.items():
        for method, details in methods.items():
            # Only consider HTTP methods
            if method.lower() not in {"get", "post", "put", "delete", "patch", "options", "head"}:
                continue
            operation_id = details.get("operationId")
            if not operation_id:
                continue  # skip endpoints without operationId
            endpoints.append({
                "path": path,
                "method": method.lower(),
                "operationId": operation_id
            })
    return endpoints

def main():
    openapi_path = sys.argv[1] if len(sys.argv) > 1 else OPENAPI_PATH
    endpoints = extract_endpoints(openapi_path)
    print(json.dumps(endpoints, indent=2))

if __name__ == "__main__":
    main() 