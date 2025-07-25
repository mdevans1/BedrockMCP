import ast
import sys
import json
from pathlib import Path
import re

MCP_SERVER_PATH = Path("bedrock_mcp_server.py")

OPID_RE = re.compile(r"OpenAPI operationId:\s*([\w_]+)")

def extract_operation_id(docstring):
    if not docstring:
        return None
    for line in docstring.splitlines():
        m = OPID_RE.search(line)
        if m:
            return m.group(1)
    return None

def extract_mcp_functions(py_path):
    with open(py_path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=str(py_path))
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.decorator_list:
                continue
            has_mcp_tool = any(
                (isinstance(d, ast.Name) and d.id == "mcp_tool_testable") or
                (isinstance(d, ast.Call) and getattr(d.func, "id", None) == "mcp_tool_testable")
                for d in node.decorator_list
            )
            if not has_mcp_tool:
                continue
            arg_names = [a.arg for a in node.args.args]
            docstring = ast.get_docstring(node)
            operation_id = extract_operation_id(docstring)
            functions.append({
                "name": node.name,
                "args": arg_names,
                "docstring": docstring,
                "operationId": operation_id,
                "lineno": node.lineno
            })
    return functions

def main():
    py_path = sys.argv[1] if len(sys.argv) > 1 else MCP_SERVER_PATH
    functions = extract_mcp_functions(py_path)
    print(json.dumps(functions, indent=2))

if __name__ == "__main__":
    main() 