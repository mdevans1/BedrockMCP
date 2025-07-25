from typing import Any, Optional
import os
import json
import httpx
import argparse
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Parse command line arguments
parser = argparse.ArgumentParser(description='Bedrock MCP Server')
parser.add_argument('--debug', action='store_true', help='Enable debug output for API responses')
args, unknown_args = parser.parse_known_args()

# Global debug flag
DEBUG_RESPONSES = args.debug or os.getenv("BEDROCK_DEBUG", "").lower() in ("true", "1", "yes")

# Initialize FastMCP server
mcp = FastMCP("bedrock-server-manager")

# Patch for test discovery: decorator that sets _is_mcp_tool
from functools import wraps

def mcp_tool_testable(*args, **kwargs):
    def decorator(func):
        decorated = mcp.tool(*args, **kwargs)(func)
        decorated._is_mcp_tool = True
        return decorated
    return decorator

# Constants
BEDROCK_API_BASE = os.getenv("BEDROCK_API_BASE", "")  # Default port is 11325
USERNAME = os.getenv("BEDROCK_SERVER_MANAGER_USERNAME", "")
PASSWORD = os.getenv("BEDROCK_SERVER_MANAGER_PASSWORD", "")

# Global token storage
access_token = None

def debug_response(response: httpx.Response) -> None:
    """Print detailed debug information about an HTTP response.
    
    This function prints:
    - HTTP status code
    - Response headers
    - Response body (as JSON if possible, otherwise as text)
    
    Args:
        response: The httpx.Response object to debug
    """
    if not DEBUG_RESPONSES:
        return
        
    print(f"[DEBUG] Response Status: {response.status_code}")
    print(f"[DEBUG] Response Headers: {dict(response.headers)}")
    try:
        print(f"[DEBUG] Response Body: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"[DEBUG] Response Body: {response.text}")

async def login() -> bool:
    """Authenticate with the Bedrock Server Manager API and obtain a JWT token.
    
    This function:
    1. Sends credentials to the /auth/token endpoint (form data)
    2. Stores the JWT token in the global access_token variable
    3. Returns True if login was successful, False otherwise
    
    Returns:
        bool: True if login successful and token obtained, False otherwise
    """
    global access_token
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "username": USERNAME,
        "password": PASSWORD
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BEDROCK_API_BASE}/auth/token",
                headers=headers,
                data=data,
                timeout=30.0
            )
            debug_response(response)
            response.raise_for_status()
            result = response.json()
            access_token = result.get("access_token")
            return bool(access_token)
        except Exception as e:
            print(f"Login failed: {str(e)}")
            return False

async def make_bedrock_request(endpoint: str, method: str = "GET", data: Optional[dict] = None) -> dict[str, Any] | None:
    """Make an authenticated request to the Bedrock Server Manager API.
    
    This function:
    1. Ensures a valid JWT token exists (logs in if needed)
    2. Makes the HTTP request with proper headers
    3. Handles 401 errors by attempting to re-login
    4. Returns the JSON response or None if request fails
    
    Args:
        endpoint: API endpoint to call (e.g. "/api/servers")
        method: HTTP method ("GET", "POST", "PUT", "DELETE")
        data: Optional request body data for POST/PUT requests
    
    Returns:
        dict | None: JSON response data if successful, None if request fails
    """
    global access_token
    
    # Ensure we have a valid token
    if not access_token and not await login():
        return None
        
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = f"{BEDROCK_API_BASE}{endpoint}"
    
    print(f"\nMaking {method} request to {url}")
    if data:
        print(f"Request data: {json.dumps(data, indent=2)}")
    
    async with httpx.AsyncClient() as client:
        try:
            if method == "GET":
                response = await client.get(url, headers=headers, timeout=30.0)
            elif method == "POST":
                response = await client.post(url, headers=headers, json=data, timeout=30.0)
            elif method == "PUT":
                response = await client.put(url, headers=headers, json=data, timeout=30.0)
            elif method == "DELETE":
                response = await client.delete(url, headers=headers, timeout=30.0)
            else:
                return None
                
            # If we get a 401, try to login again and retry once
            if response.status_code == 401:
                print("Received 401, attempting to login again...")
                if await login():
                    headers["Authorization"] = f"Bearer {access_token}"
                    if method == "GET":
                        response = await client.get(url, headers=headers, timeout=30.0)
                    elif method == "POST":
                        response = await client.post(url, headers=headers, json=data, timeout=30.0)
                    elif method == "PUT":
                        response = await client.put(url, headers=headers, json=data, timeout=30.0)
                    elif method == "DELETE":
                        response = await client.delete(url, headers=headers, timeout=30.0)
                else:
                    return None
            
            debug_response(response)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error making request to {url}: {str(e)}")
            return None

@mcp_tool_testable()
async def get_servers() -> str:
    """Retrieve a formatted list of all Bedrock servers and their current status.
    OpenAPI operationId: get_servers_list_api_route_api_servers_get
    
    This function:
    1. Fetches the list of servers from the API
    2. Formats each server's information including:
       - Server name
       - Current status
       - Version
    
    Returns:
        str: Formatted string containing server information, one server per line.
             Returns error message if unable to fetch servers.
    """
    data = await make_bedrock_request("/api/servers")
    if not data:
        return "Unable to fetch servers list."
    
    # The API returns data in the format:
    # {
    #     "status": "success",
    #     "servers": [
    #         {
    #             "name": "server_name",
    #             "status": "RUNNING/STOPPED/UNKNOWN",
    #             "version": "1.20.40.01"
    #         }
    #     ],
    #     "message": "Optional error message for partial success"
    # }
    servers = data.get("servers", [])
    if not servers:
        return "No servers found."
    
    # Format the server list
    server_list = []
    for server in servers:
        server_info = f"Server: {server.get('name', 'Unknown')}\n"
        server_info += f"  Status: {server.get('status', 'Unknown')}\n"
        server_info += f"  Version: {server.get('version', 'Unknown')}"
        server_list.append(server_info)
    
    result = "\n".join(server_list)
    
    # Add any partial success message if present
    if "message" in data:
        result += f"\n\nNote: {data['message']}"
    
    return result

# 17. get_server_status: No matching OpenAPI endpoint. Add operationId to docstring for OpenAPI mapping.
@mcp_tool_testable()
async def get_server_status(server_name: str) -> str:
    """Get server running status using 'data.running' from the response as per OpenAPI spec.
    OpenAPI operationId: get_server_running_status_api_route_api_server__server_name__status_get
    Args:
        server_name: Name of the server to check
    Returns:
        str: Status message about whether the server is running
    """
    url = f"{BEDROCK_API_BASE}/api/server/{server_name}/status"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            data = response.json()
            running = data.get("data", {}).get("running")
            if running is True:
                return f"Server '{server_name}' is running."
            elif running is False:
                return f"Server '{server_name}' is not running."
            else:
                return f"Could not determine running status for server '{server_name}'."
        except Exception as e:
            return f"Unable to fetch status for server '{server_name}': {str(e)}"

# 30. remove_from_allowlist: No matching OpenAPI endpoint. Add operationId to docstring for OpenAPI mapping.
@mcp_tool_testable()
async def remove_from_allowlist(server_name: str, player_names: list[str]) -> str:
    """Remove one or more players from a server's allowlist (whitelist).
    OpenAPI operationId: remove_allowlist_players_api_route_api_server__server_name__allowlist_remove_delete
    Args:
        server_name: Name of the server
        player_names: List of player names to remove from allowlist
    Returns:
        str: Success message with details of removed/not found players,
             Error message if operation fails
    """
    data = {"players": player_names}
    response = await make_bedrock_request(
        f"/api/server/{server_name}/allowlist/remove",
        method="DELETE",
        data=data
    )
    if not response:
        return f"Failed to remove players from allowlist for server {server_name}."
    details = response.get("details", {})
    message = response.get("message", "Remove from allowlist command sent.")
    if details:
        removed = details.get("removed", [])
        not_found = details.get("not_found", [])
        result_parts = [message]
        if removed:
            result_parts.append(f"Successfully removed: {', '.join(removed)}")
        if not_found:
            result_parts.append(f"Not found in allowlist: {', '.join(not_found)}")
        return "\n".join(result_parts)
    return message

# 42. update_server_properties: No matching OpenAPI endpoint. Add operationId to docstring for OpenAPI mapping.
@mcp_tool_testable()
async def update_server_properties(server_name: str, properties: dict) -> str:
    """Update configuration properties for a specific server.
    OpenAPI operationId: configure_properties_api_route_api_server__server_name__properties_set_post
    Args:
        server_name: Name of the server to update
        properties: Dictionary of property names and their new values.
    Returns:
        str: Success message if properties updated successfully,
             Error message if update fails
    """
    data = await make_bedrock_request(
        f"/api/server/{server_name}/properties/set",
        method="POST",
        data={"properties": properties}
    )
    if not data:
        return f"Failed to update properties for server {server_name}."
    return data.get("message", "Server properties updated successfully.")

# 6. backup_server: No matching OpenAPI endpoint. Add operationId to docstring for OpenAPI mapping.
@mcp_tool_testable()
async def backup_server(server_name: str, backup_type: str = "world", file_to_backup: Optional[str] = None) -> str:
    """Trigger a backup for a specific Bedrock server.
    OpenAPI operationId: backup_action_api_route_api_server__server_name__backup_action_post
    Args:
        server_name: Name of the server to backup
        backup_type: Type of backup ('world', 'config', or 'all'). Defaults to 'world'
        file_to_backup: Required if backup_type is 'config'. Relative path within server directory
    Returns:
        str: Formatted string with the result of the backup action.
    """
    valid_types = ["world", "config", "all"]
    if backup_type not in valid_types:
        return f"Invalid backup_type '{backup_type}'. Must be one of: {valid_types}"
    data = {"backup_type": backup_type}
    if backup_type == "config":
        if not file_to_backup:
            return "file_to_backup is required when backup_type is 'config'"
        data["file_to_backup"] = file_to_backup
    response = await make_bedrock_request(
        f"/api/server/{server_name}/backup/action", 
        method="POST",
        data=data
    )
    if not response:
        return f"Failed to send {backup_type} backup command for server {server_name}."
    return response.get("message", f"{backup_type.title()} backup command sent.")

# 31. restore_server: No matching OpenAPI endpoint. Add operationId to docstring for OpenAPI mapping.
@mcp_tool_testable()
async def restore_server(server_name: str, restore_type: str, backup_file: str = None) -> str:
    """Restore a server from a backup using the correct types and payload as per OpenAPI spec.
    OpenAPI operationId: restore_action_api_route_api_server__server_name__restore_action_post
    Args:
        server_name: Name of the server to restore
        restore_type: Type of restore ('world', 'properties', 'allowlist', 'permissions', 'all')
        backup_file: Required for all types except 'all'
    Returns:
        str: Status message about the restore operation
    """
    valid_types = ["world", "properties", "allowlist", "permissions", "all"]
    if restore_type not in valid_types:
        return f"Invalid restore_type '{restore_type}'. Must be one of: {valid_types}"
    payload = {"restore_type": restore_type}
    if restore_type != "all":
        if not backup_file:
            return f"backup_file is required when restore_type is '{restore_type}'"
        payload["backup_file"] = backup_file
    response = await make_bedrock_request(
        f"/api/server/{server_name}/restore/action",
        method="POST",
        data=payload
    )
    if not response:
        return f"Failed to restore server '{server_name}' with type '{restore_type}'."
    return json.dumps(response, indent=2)

# 16. get_server_process_info: No matching OpenAPI endpoint. Add operationId to docstring for OpenAPI mapping.
@mcp_tool_testable()
async def get_server_process_info(server_name: str) -> str:
    """Get detailed process information for a running server.
    OpenAPI operationId: server_process_info_api_route_api_server__server_name__process_info_get
    Args:
        server_name: Name of the server to get process info for
    Returns:
        str: Formatted process information including PID, memory usage, etc.
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/process_info")
    if not data:
        return f"Unable to fetch process info for server '{server_name}'."
    process_info = data.get("data", {}).get("process_info", {})
    if not process_info:
        return f"No process information available for server '{server_name}'."
    info_parts = [f"Process Info for '{server_name}':"]
    for key, value in process_info.items():
        info_parts.append(f"  {key}: {value}")
    return "\n".join(info_parts)

@mcp_tool_testable()
async def list_server_backups(server_name: str, backup_type: str = "world") -> str:
    """List available backup filenames for a server using the correct endpoint path as per OpenAPI spec.
    OpenAPI operationId: list_server_backups_api_route_api_server__server_name__backup_list__backup_type__get
    Args:
        server_name: Name of the server to list backups for
        backup_type: Type of backup to list ('world', 'config', etc.)
    Returns:
        str: Formatted list of backup filenames or error message
    """
    url = f"{BEDROCK_API_BASE}/api/server/{server_name}/backup/list/{backup_type}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            data = response.json()
            backups = data.get("backups", [])
            if not backups:
                return f"No {backup_type} backups found for server '{server_name}'."
            backup_list = [f"{backup_type.title()} backups for '{server_name}':"]
            for backup in backups:
                backup_list.append(f"  - {backup}")
            return "\n".join(backup_list)
        except Exception as e:
            return f"Unable to fetch backup list for server '{server_name}': {str(e)}"

@mcp_tool_testable()
async def reset_world(server_name: str) -> str:
    """Reset (delete) the current world for a server.
    OpenAPI operationId: reset_world_api_route_api_server__server_name__world_reset_delete
    Args:
        server_name: Name of the server to reset the world for
    Returns:
        str: Status message about the reset operation
    """
    data = await make_bedrock_request(
        f"/api/server/{server_name}/world/reset",
        method="DELETE"
    )
    if not data:
        return f"Failed to reset world for server '{server_name}'."
    
    return f"World reset for server '{server_name}'. Status: {data.get('message', 'World reset successfully')}"

# 38. trigger_plugin_event: No matching OpenAPI endpoint. Add operationId to docstring for OpenAPI mapping.
# @mcp_tool_testable()
# async def trigger_plugin_event(event_name: str, event_data: dict = None) -> str:
#     """Trigger a custom plugin event.
#     OpenAPI operationId: trigger_event_api_route_api_plugins_trigger_event_post
#     Args:
#         event_name: Name of the event to trigger
#         event_data: Optional data to pass with the event
#     Returns:
#         str: Status message about the event trigger operation
#     """
#     payload = {"event_name": event_name}
#     if event_data:
#         payload["event_data"] = event_data
    
#     data = await make_bedrock_request(
#         "/api/plugins/trigger_event",
#         method="POST",
#         data=payload
#     )
#     if not data:
#         return f"Failed to trigger event '{event_name}'."
    
#     return f"Event '{event_name}' triggered successfully. Status: {data.get('message', 'Event triggered')}"

@mcp_tool_testable()
async def trigger_plugin_event_payload(event_name: str, payload: dict = None) -> str:
    """Trigger a custom plugin event via /api/plugins/trigger_event (POST), using {"event_name": ..., "payload": ...}.
    OpenAPI operationId: trigger_event_api_route_api_plugins_trigger_event_post
    Args:
        event_name: Name of the event to trigger
        payload: Optional dictionary payload for the event
    Returns:
        str: Status message about the event trigger operation
    """
    url = f"{BEDROCK_API_BASE}/api/plugins/trigger_event"
    data = {"event_name": event_name}
    if payload is not None:
        data["payload"] = payload
    headers = {"Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            result = response.json()
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Failed to trigger plugin event: {str(e)}"

# 13. get_player_permissions: No matching OpenAPI endpoint. Add operationId to docstring for OpenAPI mapping.
@mcp_tool_testable()
async def get_player_permissions(server_name: str) -> str:
    """Get player permissions for a server using 'data.permissions' as a list per OpenAPI spec.
    OpenAPI operationId: get_server_permissions_api_route_api_server__server_name__permissions_get_get
    Args:
        server_name: Name of the server to get permissions for
    Returns:
        str: Formatted player permissions information or error message
    """
    url = f"{BEDROCK_API_BASE}/api/server/{server_name}/permissions/get"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            data = response.json()
            permissions = data.get("data", {}).get("permissions", [])
            if not permissions:
                return f"No player permissions found for server '{server_name}'."
            perm_list = [f"Player permissions for '{server_name}':"]
            for perm in permissions:
                name = perm.get("name", "Unknown")
                xuid = perm.get("xuid", "Unknown")
                level = perm.get("permission_level", "Unknown")
                perm_list.append(f"  {name} (XUID: {xuid}): {level}")
            return "\n".join(perm_list)
        except Exception as e:
            return f"Unable to fetch player permissions for server '{server_name}': {str(e)}"

# 40. update_player_permissions: No matching OpenAPI endpoint. Add operationId to docstring for OpenAPI mapping.
@mcp_tool_testable()
async def update_player_permissions(server_name: str, permissions: list[dict]) -> str:
    """Update the permission level for players on a Bedrock server.
    OpenAPI operationId: configure_permissions_api_route_api_server__server_name__permissions_set_put
    Args:
        server_name: Name of the server
        permissions: List of permission objects, each with xuid, name, and permission_level
    Returns:
        str: Success message if permissions updated successfully,
             Error message if update fails
    """
    data = await make_bedrock_request(
        f"/api/server/{server_name}/permissions/set",
        method="PUT",
        data={"permissions": permissions}
    )
    if not data:
        return f"Failed to update player permissions for server {server_name}."
    message = data.get("message", "Player permissions updated")
    return message

# 7. configure_service: Extra param in function. Add docstring note.
@mcp_tool_testable()
async def configure_service(server_name: str, service_config: dict) -> str:
    """Configure OS-level service settings for a specific server.
    NOTE: 'service_config' is not in the OpenAPI spec; this function is for internal use or future API expansion.
    Args:
        server_name: Name of the server
        service_config: Dictionary of service settings to configure
    Returns:
        str: Success message if service configured successfully,
             Error message if configuration fails
    """
    data = await make_bedrock_request(
        f"/api/server/{server_name}/service",
        method="POST",
        data={"service_config": service_config}
    )
    if not data:
        return f"Failed to configure service settings for server {server_name}."
    
    # The API returns data in the format:
    # {
    #     "status": "success",
    #     "message": "Service settings configured successfully"
    # }
    message = data.get("message", "Service settings configured")
    return f"{message} for server {server_name}"

# 43. update_service_settings: Extra param in function. Add docstring note.
@mcp_tool_testable()
async def update_service_settings(server_name: str, autoupdate: bool = None, autostart: bool = None) -> str:
    """Update service settings for a server via /api/server/{server_name}/service/update (POST).
    OpenAPI operationId: configure_service_api_route_api_server__server_name__service_update_post
    NOTE: 'autoupdate' and 'autostart' are required by the OpenAPI spec as the request body properties.
    Args:
        server_name: Name of the server
        autoupdate: Optional, enable/disable autoupdate
        autostart: Optional, enable/disable autostart
    Returns:
        str: Status message about the update operation
    """
    url = f"{BEDROCK_API_BASE}/api/server/{server_name}/service/update"
    payload = {}
    if autoupdate is not None:
        payload["autoupdate"] = autoupdate
    if autostart is not None:
        payload["autostart"] = autostart
    if not payload:
        return "At least one of autoupdate or autostart must be provided."
    headers = {"Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            result = response.json()
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Failed to update service settings: {str(e)}"

@mcp_tool_testable()
async def prune_downloads() -> str:
    """Prune the download cache.
    OpenAPI operationId: prune_downloads_api_route_api_downloads_prune_post
    """
    data = await make_bedrock_request("/api/downloads/prune", method="POST")
    if not data:
        return "Failed to prune download cache."
    
    # The API returns data in the format:
    # {
    #     "status": "success",
    #     "message": "Download cache pruned successfully",
    #     "data": {
    #         "freed_space": "123.45 MB"  # Optional amount of space freed
    #     }
    # }
    message = data.get("message", "Download cache pruned")
    freed_space = data.get("data", {}).get("freed_space")
    
    result = message
    if freed_space:
        result += f"\nFreed space: {freed_space}"
    
    return result

# 22. install_new_server: No matching OpenAPI endpoint. Remove decorator if not an API endpoint.
# REMOVED: async def install_new_server(server_config: dict) -> str: ...

@mcp_tool_testable()
async def get_system_info() -> str:
    """Get system and application information.
    OpenAPI operationId: get_system_info_api_route_api_info_get
    
    This function retrieves:
    - Operating system type
    - Application version
    
    Returns:
        str: Formatted string containing system and application information.
             Returns error message if unable to fetch information.
    """
    data = await make_bedrock_request("/api/info")
    if not data:
        return "Unable to fetch system information."
    
    # The API returns data in the format:
    # {
    #     "status": "success",
    #     "data": {
    #         "os_type": "Linux/Windows/Darwin",
    #         "app_version": "3.2.1"
    #     }
    # }
    info = data.get("data", {})
    if not info:
        return "No system information found."
    
    return f"System Information:\nOS Type: {info.get('os_type', 'Unknown')}\nApp Version: {info.get('app_version', 'Unknown')}"

# 10. get_config_status: No matching OpenAPI endpoint. Add operationId to docstring for OpenAPI mapping.
@mcp_tool_testable()
async def get_config_status(server_name: str) -> str:
    """Get the configuration status for a specific Bedrock server.
    OpenAPI operationId: get_server_config_status_api_route_api_server__server_name__config_status_get
    Args:
        server_name: Name of the server to check
    Returns:
        str: Formatted string containing configuration status.
             Returns error message if unable to fetch status.
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/config_status")
    if not data:
        return f"Unable to fetch config status for server {server_name}."
    config_status = data.get("data", {}).get("config_status")
    if not config_status:
        return f"Could not determine config status for server {server_name}."
    return f"Configuration status for server {server_name}: {config_status}"

# --- Task Scheduler Functions ---

# 1. add_cron_job: No matching OpenAPI endpoint. Remove decorator if not an API endpoint.
# REMOVED: async def add_cron_job(server_name: str, job_details: dict) -> str: ...

# 2. add_players: Extra param in function. Add docstring note.
@mcp_tool_testable()
async def add_players(players: list[str]) -> str:
    """Add players to the global player list via /api/players/add, using {"players": ["PlayerOne:123xuid", ...]} payload as per spec.
    OpenAPI operationId: add_players_api_route_api_players_add_post
    Args:
        players: List of player strings in 'gamertag:xuid' format
        NOTE: 'players' is required by the OpenAPI spec as the request body property.
    Returns:
        str: Status message about the add operation
    """
    url = f"{BEDROCK_API_BASE}/api/players/add"
    payload = {"players": players}
    headers = {"Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            result = response.json()
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Failed to add players: {str(e)}"

# 3. add_players_to_allowlist: No matching OpenAPI endpoint. Add operationId to docstring for OpenAPI mapping.
@mcp_tool_testable()
async def add_players_to_allowlist(server_name: str, player_names: list[str], ignores_player_limit: bool = False) -> str:
    """Add one or more players to a server's allowlist (whitelist).
    OpenAPI operationId: add_to_allowlist_api_route_api_server__server_name__allowlist_add_post
    Args:
        server_name: Name of the server
        player_names: List of player names to add to allowlist
        ignores_player_limit: Whether to set ignoresPlayerLimit for these players
    Returns:
        str: Success message with details of added players,
             Error message if operation fails
    """
    data = {"players": player_names, "ignoresPlayerLimit": ignores_player_limit}
    response = await make_bedrock_request(
        f"/api/server/{server_name}/allowlist/add",
        method="POST",
        data=data
    )
    if not response:
        return f"Failed to add players to allowlist for server {server_name}."
    message = response.get("message", "Add to allowlist command sent.")
    added_count = response.get("added_count")
    result = message
    if added_count is not None:
        result += f"\nPlayers added: {added_count}"
    return result

# 4. add_players_to_global_list: No matching OpenAPI endpoint. This function is not exposed as an API tool.
# REMOVED: async def add_players_to_global_list(player_names: list[str]) -> str: ...

# 5. add_windows_task: No matching OpenAPI endpoint. Remove decorator if not an API endpoint.
# REMOVED: async def add_windows_task(server_name: str, task_details: dict) -> str: ...

# 26. modify_cron_job: No matching OpenAPI endpoint. Remove decorator if not an API endpoint.
# REMOVED: async def modify_cron_job(server_name: str, job_details: dict) -> str: ...

# 8. delete_cron_job: No matching OpenAPI endpoint. Remove decorator if not an API endpoint.
# REMOVED: async def delete_cron_job(server_name: str, job_id: str) -> str: ...

# 19. get_windows_task_details: No matching OpenAPI endpoint. Remove decorator if not an API endpoint.
# REMOVED: async def get_windows_task_details(server_name: str, task_name: str) -> str: ...

# 27. modify_windows_task: No matching OpenAPI endpoint. Remove decorator if not an API endpoint.
# REMOVED: async def modify_windows_task(server_name: str, task_name: str, task_details: dict) -> str: ...

# 9. delete_windows_task: No matching OpenAPI endpoint. Remove decorator if not an API endpoint.
# REMOVED: async def delete_windows_task(server_name: str, task_name: str) -> str: ...

@mcp_tool_testable()
async def api_logout() -> str:
    """Logout via /auth/logout endpoint as per OpenAPI spec.
    OpenAPI operationId: logout_auth_logout_get
    Returns:
        str: Success or error message
    """
    url = f"{BEDROCK_API_BASE}/auth/logout"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            return "Logout successful."
        except Exception as e:
            return f"Logout failed: {str(e)}"

@mcp_tool_testable()
async def get_all_settings() -> str:
    """Get all global application settings via /api/settings (GET).
    OpenAPI operationId: get_all_settings_api_route_api_settings_get
    """
    url = f"{BEDROCK_API_BASE}/api/settings"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            result = response.json()
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Failed to get settings: {str(e)}"

# 36. set_setting: Extra param in function. Add docstring note.
@mcp_tool_testable()
async def set_setting(key: str, value: Any) -> str:
    """Set a specific global application setting via /api/settings (POST).
    OpenAPI operationId: set_setting_api_route_api_settings_post
    NOTE: 'key' and 'value' are required by the OpenAPI spec as the request body properties.
    Args:
        key: The dot-notation key of the setting (e.g., 'web.port').
        value: The new value for the setting.
    Returns:
        str: JSON response from the API or error message
    """
    url = f"{BEDROCK_API_BASE}/api/settings"
    payload = {"key": key, "value": value}
    headers = {"Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            result = response.json()
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Failed to set setting: {str(e)}"

@mcp_tool_testable()
async def get_themes() -> str:
    """Get available themes via /api/themes (GET).
    OpenAPI operationId: get_themes_api_route_api_themes_get
    """
    url = f"{BEDROCK_API_BASE}/api/themes"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            result = response.json()
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Failed to get themes: {str(e)}"

@mcp_tool_testable()
async def reload_settings() -> str:
    """Reload global application settings via /api/settings/reload (POST).
    OpenAPI operationId: reload_settings_api_route_api_settings_reload_post
    """
    url = f"{BEDROCK_API_BASE}/api/settings/reload"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            result = response.json()
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Failed to reload settings: {str(e)}"

# 33. select_restore_backup_type: Extra param in function. Add docstring note.
@mcp_tool_testable()
async def select_restore_backup_type(server_name: str, restore_type: str) -> str:
    """Select a restore type for a server via /api/server/{server_name}/restore/select_backup_type (POST).
    OpenAPI operationId: handle_restore_select_backup_type_api_api_server__server_name__restore_select_backup_type_post
    NOTE: 'restore_type' is required by the OpenAPI spec as the request body property.
    Args:
        server_name: Name of the server
        restore_type: Type of restore (e.g., 'world', 'properties', etc.)
    Returns:
        str: JSON response from the API or error message
    """
    url = f"{BEDROCK_API_BASE}/api/server/{server_name}/restore/select_backup_type"
    payload = {"restore_type": restore_type}
    headers = {"Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            result = response.json()
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Failed to select restore backup type: {str(e)}"

# 20. get_world_icon: Extra param in function. Add docstring note.
@mcp_tool_testable()
async def get_world_icon(server_name: str, save_path: str = None) -> str:
    """Fetch the world icon image for a server via /api/server/{server_name}/world/icon (GET).
    OpenAPI operationId: serve_world_icon_api_api_server__server_name__world_icon_get
    NOTE: 'save_path' is not in the OpenAPI spec; this is an optional convenience for local saving.
    Args:
        server_name: Name of the server
        save_path: Optional path to save the image file
    Returns:
        str: Status message about the fetch operation
    """
    url = f"{BEDROCK_API_BASE}/api/server/{server_name}/world/icon"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            if save_path:
                with open(save_path, "wb") as f:
                    f.write(response.content)
                return f"World icon image saved to {save_path}"
            return "World icon image fetched successfully (binary data not shown)."
        except Exception as e:
            return f"Failed to fetch world icon: {str(e)}"

# 12. get_panorama_image_file: Extra param in function. Add docstring note.
@mcp_tool_testable()
async def get_panorama_image_file(save_path: str = None) -> str:
    """Fetch the panorama image via /api/panorama (GET).
    OpenAPI operationId: serve_custom_panorama_api_api_panorama_get
    NOTE: 'save_path' is not in the OpenAPI spec; this is an optional convenience for local saving.
    Args:
        save_path: Optional path to save the image file
    Returns:
        str: Status message about the fetch operation
    """
    url = f"{BEDROCK_API_BASE}/api/panorama"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            if save_path:
                with open(save_path, "wb") as f:
                    f.write(response.content)
                return f"Panorama image saved to {save_path}"
            return "Panorama image fetched successfully (binary data not shown)."
        except Exception as e:
            return f"Failed to fetch panorama image: {str(e)}"

# 35. set_plugin_enabled: Extra param in function. Add docstring note.
@mcp_tool_testable()
async def set_plugin_enabled(plugin_name: str, enabled: bool) -> str:
    """Enable or disable a plugin via /api/plugins/{plugin_name} (POST), using {"enabled": bool} payload.
    OpenAPI operationId: set_plugin_status_api_route_api_plugins__plugin_name__post
    NOTE: 'plugin_name' is required by the OpenAPI spec as a path parameter.
    Args:
        plugin_name: Name of the plugin
        enabled: True to enable, False to disable
    Returns:
        str: Status message about the plugin toggle operation
    """
    url = f"{BEDROCK_API_BASE}/api/plugins/{plugin_name}"
    payload = {"enabled": enabled}
    headers = {"Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            result = response.json()
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Failed to set plugin enabled: {str(e)}"

# 24. list_available_addons: No matching OpenAPI endpoint. Add operationId to docstring for OpenAPI mapping.
@mcp_tool_testable()
async def list_available_addons() -> str:
    """List available addon files that can be installed on servers, using the 'files' key as per OpenAPI spec.
    OpenAPI operationId: list_addons_api_route_api_content_addons_get
    """
    url = f"{BEDROCK_API_BASE}/api/content/addons"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            debug_response(response)
            response.raise_for_status()
            data = response.json()
            files = data.get("files", [])
            if not files:
                return "No addon files available."
            addon_list = ["Available addons:"]
            for addon in files:
                addon_list.append(f"  - {addon}")
            return "\n".join(addon_list)
        except Exception as e:
            return f"Unable to fetch available addons: {str(e)}"

@mcp_tool_testable()
async def start_server(server_name: str) -> str:
    """Start a server instance.
    OpenAPI operationId: start_server_route_api_server__server_name__start_post
    Args:
        server_name: Name of the server to start
    Returns:
        str: Status message about the start operation
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/start", method="POST")
    if not data:
        return f"Failed to start server {server_name}."
    return data.get("message", f"Start command sent for server {server_name}.")

@mcp_tool_testable()
async def stop_server(server_name: str) -> str:
    """Stop a running server instance.
    OpenAPI operationId: stop_server_route_api_server__server_name__stop_post
    Args:
        server_name: Name of the server to stop
    Returns:
        str: Status message about the stop operation
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/stop", method="POST")
    if not data:
        return f"Failed to stop server {server_name}."
    return data.get("message", f"Stop command sent for server {server_name}.")

@mcp_tool_testable()
async def restart_server(server_name: str) -> str:
    """Restart a server instance.
    OpenAPI operationId: restart_server_route_api_server__server_name__restart_post
    Args:
        server_name: Name of the server to restart
    Returns:
        str: Status message about the restart operation
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/restart", method="POST")
    if not data:
        return f"Failed to restart server {server_name}."
    return data.get("message", f"Restart command sent for server {server_name}.")

@mcp_tool_testable()
async def send_command(server_name: str, command: str) -> str:
    """Send a command to a running server instance.
    OpenAPI operationId: send_command_route_api_server__server_name__send_command_post
    Args:
        server_name: Name of the server
        command: Command string to send
    Returns:
        str: Status message about the command execution
    """
    payload = {"command": command}
    data = await make_bedrock_request(f"/api/server/{server_name}/send_command", method="POST", data=payload)
    if not data:
        return f"Failed to send command to server {server_name}."
    message = data.get("message", "Command sent.")
    details = data.get("details")
    result = message
    if details:
        result += f"\nDetails: {details}"
    return result

@mcp_tool_testable()
async def install_server(server_name: str, server_version: str = "LATEST", overwrite: bool = False, server_zip_path: str = None) -> str:
    """Install a new Bedrock server instance.
    OpenAPI operationId: install_server_api_route_api_server_install_post
    Args:
        server_name: Name for the new server
        server_version: Version to install (e.g., 'LATEST', '1.20.10.01', 'CUSTOM')
        overwrite: If true, delete existing server data if server_name conflicts
        server_zip_path: Absolute path to a custom server ZIP file (required if server_version is 'CUSTOM')
    Returns:
        str: Status message about the installation
    """
    payload = {
        "server_name": server_name,
        "server_version": server_version,
        "overwrite": overwrite
    }
    if server_zip_path is not None:
        payload["server_zip_path"] = server_zip_path
    data = await make_bedrock_request("/api/server/install", method="POST", data=payload)
    if not data:
        return f"Failed to install server {server_name}."
    return json.dumps(data, indent=2)

@mcp_tool_testable()
async def get_allowlist(server_name: str) -> str:
    """Retrieve the allowlist for a specific server.
    OpenAPI operationId: get_allowlist_api_route_api_server__server_name__allowlist_get_get
    Args:
        server_name: Name of the server
    Returns:
        str: List of allowlisted players or error message
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/allowlist/get")
    if not data:
        return f"Unable to fetch allowlist for server {server_name}."
    players = data.get("players", [])
    if not players:
        return f"No allowlist entries found for server {server_name}."
    result = [f"Allowlist for server {server_name}:"]
    for player in players:
        name = player.get("name", "Unknown")
        xuid = player.get("xuid", "Unknown")
        ignores = player.get("ignoresPlayerLimit", False)
        result.append(f"  {name} (XUID: {xuid}) - IgnoresPlayerLimit: {ignores}")
    return "\n".join(result)

@mcp_tool_testable()
async def list_worlds() -> str:
    """List available .mcworld template files.
    OpenAPI operationId: list_worlds_api_route_api_content_worlds_get
    Returns:
        str: List of available world files or error message
    """
    data = await make_bedrock_request("/api/content/worlds")
    if not data:
        return "Unable to fetch available worlds."
    files = data.get("files", [])
    if not files:
        return "No world files available."
    result = ["Available worlds:"]
    for world in files:
        result.append(f"  - {world}")
    return "\n".join(result)

@mcp_tool_testable()
async def get_plugins_status() -> str:
    """Retrieve the statuses and metadata of all discovered plugins.
    OpenAPI operationId: get_plugins_status_api_route_api_plugins_get
    Returns:
        str: Plugin status information or error message
    """
    data = await make_bedrock_request("/api/plugins")
    if not data:
        return "Unable to fetch plugin status information."
    plugins = data.get("data", {})
    if not plugins:
        return "No plugins found."
    result = ["Plugins status:"]
    for name, info in plugins.items():
        enabled = info.get("enabled", False)
        desc = info.get("description", "")
        version = info.get("version", "")
        result.append(f"  {name}: Enabled={enabled}, Version={version}, Description={desc}")
    return "\n".join(result)

@mcp_tool_testable()
async def reload_plugins() -> str:
    """Reload all plugins in the system.
    OpenAPI operationId: reload_plugins_api_route_api_plugins_reload_put
    Returns:
        str: Status message about the reload operation
    """
    data = await make_bedrock_request("/api/plugins/reload", method="PUT")
    if not data:
        return "Failed to reload plugins."
    return data.get("message", "Plugins reloaded.")

@mcp_tool_testable()
async def get_custom_zips() -> str:
    """Get a list of available custom server ZIP files.
    OpenAPI operationId: get_custom_zips_api_downloads_list_get
    Returns:
        str: List of custom ZIP files or error message
    """
    data = await make_bedrock_request("/api/downloads/list")
    if not data:
        return "Unable to fetch custom ZIP files."
    files = data.get("files", [])
    if not files:
        return "No custom ZIP files available."
    result = ["Custom ZIP files:"]
    for f in files:
        result.append(f"  - {f}")
    return "\n".join(result)

# --- MISSING API ENDPOINTS IMPLEMENTATION ---

@mcp_tool_testable()
async def update_server(server_name: str) -> str:
    """Update a server instance to the latest version.
    OpenAPI operationId: update_server_route_api_server__server_name__update_post
    Args:
        server_name: Name of the server to update
    Returns:
        str: Status message about the update operation
    Example:
        await update_server("MyServer")
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/update", method="POST")
    if not data:
        return f"Failed to update server '{server_name}'."
    return data.get("message", f"Update command sent for server {server_name}.")

@mcp_tool_testable()
async def delete_server(server_name: str) -> str:
    """Delete a server instance and its data.
    OpenAPI operationId: delete_server_route_api_server__server_name__delete_delete
    Args:
        server_name: Name of the server to delete
    Returns:
        str: Status message about the delete operation
    Example:
        await delete_server("MyServer")
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/delete", method="DELETE")
    if not data:
        return f"Failed to delete server '{server_name}'."
    return data.get("message", f"Delete command sent for server {server_name}.")

@mcp_tool_testable()
async def get_server_properties(server_name: str) -> str:
    """Get server.properties for a specific server as a dictionary.
    OpenAPI operationId: get_server_properties_api_route_api_server__server_name__properties_get_get
    Args:
        server_name: Name of the server
    Returns:
        str: Properties as JSON or error message
    Example:
        await get_server_properties("MyServer")
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/properties/get")
    if not data:
        return f"Unable to fetch properties for server '{server_name}'."
    if data.get("status") != "success":
        return data.get("message", "Failed to get properties.")
    props = data.get("properties", {})
    return json.dumps(props, indent=2) if props else "No properties found."

@mcp_tool_testable()
async def prune_backups(server_name: str) -> str:
    """Prune old backups for a specific server.
    OpenAPI operationId: prune_backups_api_route_api_server__server_name__backups_prune_post
    Args:
        server_name: Name of the server
    Returns:
        str: Status message about the prune operation
    Example:
        await prune_backups("MyServer")
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/backups/prune", method="POST")
    if not data:
        return f"Failed to prune backups for server '{server_name}'."
    return data.get("message", "Backup prune command sent.")

@mcp_tool_testable()
async def install_world(server_name: str, filename: str) -> str:
    """Install a world from a .mcworld file to a server.
    OpenAPI operationId: install_world_api_route_api_server__server_name__world_install_post
    Args:
        server_name: Name of the server
        filename: Name of the .mcworld file to install
    Returns:
        str: Status message about the install operation
    Example:
        await install_world("MyServer", "MyWorld.mcworld")
    """
    payload = {"filename": filename}
    data = await make_bedrock_request(f"/api/server/{server_name}/world/install", method="POST", data=payload)
    if not data:
        return f"Failed to install world '{filename}' for server '{server_name}'."
    return data.get("message", f"World install command sent for {server_name}.")

@mcp_tool_testable()
async def export_world(server_name: str) -> str:
    """Export the active world of a server to a .mcworld file.
    OpenAPI operationId: export_world_api_route_api_server__server_name__world_export_post
    Args:
        server_name: Name of the server
    Returns:
        str: Status message about the export operation
    Example:
        await export_world("MyServer")
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/world/export", method="POST")
    if not data:
        return f"Failed to export world for server '{server_name}'."
    return data.get("message", f"World export command sent for {server_name}.")

@mcp_tool_testable()
async def install_addon(server_name: str, filename: str) -> str:
    """Install an addon from a .mcaddon or .mcpack file to a server.
    OpenAPI operationId: install_addon_api_route_api_server__server_name__addon_install_post
    Args:
        server_name: Name of the server
        filename: Name of the addon file to install
    Returns:
        str: Status message about the install operation
    Example:
        await install_addon("MyServer", "CoolAddon.mcaddon")
    """
    payload = {"filename": filename}
    data = await make_bedrock_request(f"/api/server/{server_name}/addon/install", method="POST", data=payload)
    if not data:
        return f"Failed to install addon '{filename}' for server '{server_name}'."
    return data.get("message", f"Addon install command sent for {server_name}.")

@mcp_tool_testable()
async def get_server_version(server_name: str) -> str:
    """Get the installed version of a specific server.
    OpenAPI operationId: get_server_version_api_route_api_server__server_name__version_get
    Args:
        server_name: Name of the server
    Returns:
        str: Version string or error message
    Example:
        await get_server_version("MyServer")
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/version")
    if not data:
        return f"Unable to fetch version for server '{server_name}'."
    version = data.get("data", {}).get("version")
    if not version:
        return f"No version information found for server '{server_name}'."
    return f"Server '{server_name}' version: {version}"

@mcp_tool_testable()
async def validate_server(server_name: str) -> str:
    """Validate if a server installation exists and is minimally correct.
    OpenAPI operationId: validate_server_api_route_api_server__server_name__validate_get
    Args:
        server_name: Name of the server
    Returns:
        str: Validation result message
    Example:
        await validate_server("MyServer")
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/validate")
    if not data:
        return f"Unable to validate server '{server_name}'."
    return data.get("message", "Validation result unavailable.")

@mcp_tool_testable()
async def scan_players() -> str:
    """Scan all server logs to update the central player database.
    OpenAPI operationId: scan_players_api_route_api_players_scan_post
    Returns:
        str: Scan summary or error message
    Example:
        await scan_players()
    """
    data = await make_bedrock_request("/api/players/scan", method="POST")
    if not data:
        return "Failed to scan players."
    return data.get("message", "Player scan completed.")

@mcp_tool_testable()
async def get_all_players() -> str:
    """Get the list of all known players from the central player database.
    OpenAPI operationId: get_all_players_api_route_api_players_get_get
    Returns:
        str: List of players as JSON or error message
    Example:
        await get_all_players()
    """
    data = await make_bedrock_request("/api/players/get")
    if not data:
        return "Unable to fetch player list."
    players = data.get("players", [])
    if not players:
        return "No players found."
    return json.dumps(players, indent=2)

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio') 