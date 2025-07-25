import json
import sys
import httpx

DEFAULT_SERVER = "localhost"
DEFAULT_PORT = 11325


def fetch_openapi_spec(server: str, port: int) -> dict:
    """Fetch the OpenAPI specification from the running server."""
    url = f"http://{server}:{port}/api/openapi.json"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


def extract_endpoints(spec: dict):
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
    server = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SERVER
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT
    spec = fetch_openapi_spec(server, port)
    endpoints = extract_endpoints(spec)
    print(json.dumps(endpoints, indent=2))

if __name__ == "__main__":
    main() 