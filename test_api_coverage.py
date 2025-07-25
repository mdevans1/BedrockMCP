import json
import pytest
from pathlib import Path

OPENAPI_ENDPOINTS_PATH = Path("openapi_endpoints.json")
MCP_FUNCTIONS_PATH = Path("mcp_functions.json")

def load_openapi_operation_ids():
    with open(OPENAPI_ENDPOINTS_PATH, "r", encoding="utf-8") as f:
        endpoints = json.load(f)
    return set(ep["operationId"] for ep in endpoints)

def load_mcp_function_operation_ids():
    with open(MCP_FUNCTIONS_PATH, "r", encoding="utf-8") as f:
        functions = json.load(f)
    # Use operationId from docstring if present, else function name
    opids = set()
    for func in functions:
        if func.get("operationId"):
            opids.add(func["operationId"])
        else:
            opids.add(func["name"])
    return opids

def test_openapi_coverage():
    openapi_ops = load_openapi_operation_ids()
    mcp_ops = load_mcp_function_operation_ids()

    missing_funcs = openapi_ops - mcp_ops
    extra_funcs = mcp_ops - openapi_ops

    if missing_funcs:
        print("Unmapped OpenAPI operationIds:", missing_funcs)
    if extra_funcs:
        print("Functions with no matching OpenAPI operationId:", extra_funcs)

    assert not missing_funcs, f"Unmapped OpenAPI operationIds: {missing_funcs}"
    assert not extra_funcs, f"Functions with no matching OpenAPI operationId: {extra_funcs}" 