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
    1. Sends credentials to the login endpoint
    2. Stores the JWT token in the global access_token variable
    3. Returns True if login was successful, False otherwise
    
    Returns:
        bool: True if login successful and token obtained, False otherwise
    """
    global access_token
    
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "username": USERNAME,
        "password": PASSWORD
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BEDROCK_API_BASE}/api/login",
                headers=headers,
                json=data,
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

@mcp.tool()
async def get_servers() -> str:
    """Retrieve a formatted list of all Bedrock servers and their current status.
    
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

@mcp.tool()
async def get_server_status(server_name: str) -> str:
    """Get detailed status information for a specific Bedrock server.
    
    This function retrieves and formats:
    - Process information (PID, CPU, Memory, Uptime) if running
    - Process status
    
    Args:
        server_name: Name of the server to check
    
    Returns:
        str: Formatted string containing server status information.
             Returns error message if unable to fetch status.
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/status")
    if not data:
        return f"Unable to fetch status for server {server_name}."
    
    # The API returns data in the format:
    # {
    #     "status": "success",
    #     "process_info": {
    #         "pid": 12345,
    #         "cpu_percent": 10.5,
    #         "memory_mb": 512.5,
    #         "uptime": "1:00:00"
    #     }
    # }
    # OR if not running:
    # {
    #     "status": "success", 
    #     "process_info": null,
    #     "message": "Server 'name' is not running."
    # }
    
    process_info = data.get("process_info")
    if process_info is None:
        # Server is not running
        message = data.get("message", f"Server {server_name} is not running.")
        return f"Server Status for {server_name}:\nRunning: No\n{message}"
    
    # Build a detailed status report for running server
    status_report = [
        f"Server Status for {server_name}:",
        f"Running: Yes",
        f"PID: {process_info.get('pid', 'Unknown')}",
        f"CPU Usage: {process_info.get('cpu_percent', 'Unknown')}%",
        f"Memory Usage: {process_info.get('memory_mb', 'Unknown')} MB",
        f"Uptime: {process_info.get('uptime', 'Unknown')}"
    ]
    
    return "\n".join(status_report)

@mcp.tool()
async def start_server(server_name: str) -> str:
    """Initiate the startup sequence for a specific Bedrock server.
    
    This function:
    1. Sends a start command to the server
    2. Returns success/failure message
    
    Args:
        server_name: Name of the server to start
    
    Returns:
        str: Success message if command sent successfully,
             Error message if command fails
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/start", method="POST")
    if not data:
        return f"Failed to start server {server_name}."
    return data.get("message", f"Server {server_name} start command sent successfully.")

@mcp.tool()
async def stop_server(server_name: str) -> str:
    """Initiate the shutdown sequence for a specific Bedrock server.
    
    This function:
    1. Sends a stop command to the server
    2. Returns success/failure message
    
    Args:
        server_name: Name of the server to stop
    
    Returns:
        str: Success message if command sent successfully,
             Error message if command fails
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/stop", method="POST")
    if not data:
        return f"Failed to stop server {server_name}."
    return data.get("message", f"Server {server_name} stop command sent successfully.")

@mcp.tool()
async def restart_server(server_name: str) -> str:
    """Perform a complete restart of a specific Bedrock server.
    
    This function:
    1. Sends a restart command to the server
    2. Returns success/failure message
    
    Args:
        server_name: Name of the server to restart
    
    Returns:
        str: Success message if command sent successfully,
             Error message if command fails
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/restart", method="POST")
    if not data:
        return f"Failed to restart server {server_name}."
    return data.get("message", f"Server {server_name} restart command sent successfully.")

@mcp.tool()
async def send_command(server_name: str, command: str) -> str:
    """Execute a command on a specific Bedrock server's console.
    
    This function:
    1. Sends the command to the server's console
    2. Returns the command's response
    
    Args:
        server_name: Name of the server to send command to
        command: The exact command string to execute
    
    Returns:
        str: Command response from the server,
             Error message if command fails
    """
    data = await make_bedrock_request(
        f"/api/server/{server_name}/send_command",
        method="POST",
        data={"command": command}
    )
    if not data:
        return f"Failed to send command to server {server_name}."
    return f"Command response: {data.get('data', 'No response')}"

@mcp.tool()
async def get_allowlist(server_name: str) -> str:
    """Retrieve the current allowlist (whitelist) for a specific server.
    
    This function:
    1. Fetches the allowlist from the server
    2. Returns the formatted list of allowed players
    
    Args:
        server_name: Name of the server to get allowlist for
    
    Returns:
        str: Formatted string containing the allowlist,
             Error message if unable to fetch allowlist
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/allowlist/get")
    if not data:
        return f"Unable to fetch allowlist for server {server_name}."
    
    allowlist = data.get("allowlist", [])
    if not allowlist:
        return f"Allowlist for {server_name} is empty."
    
    player_list = [f"Allowlist for {server_name}:"]
    for player in allowlist:
        player_list.append(f"  - {player}")
    
    return "\n".join(player_list)

@mcp.tool()
async def add_players_to_allowlist(server_name: str, player_names: list[str], ignores_player_limit: bool = False) -> str:
    """Add one or more players to the allowlist of a Bedrock server.
    
    This function:
    1. Sends a command to add players to the allowlist
    2. Returns success/failure message
    
    Args:
        server_name: Name of the server to modify the allowlist for
        player_names: List of player names (gamertags) to add
        ignores_player_limit: Whether to set ignoresPlayerLimit flag for added players. Defaults to False
        
    Returns:
        str: Formatted string with the result of the action.
    """
    data = {
        "players": player_names,
        "ignoresPlayerLimit": ignores_player_limit
    }
    response = await make_bedrock_request(
        f"/api/server/{server_name}/allowlist/add", 
        method="POST", 
        data=data
    )
    if not response:
        return f"Failed to add players to allowlist for server {server_name}."
        
    return response.get("message", "Add players to allowlist command sent.")

@mcp.tool()
async def remove_from_allowlist(server_name: str, player_names: list[str]) -> str:
    """Remove one or more players from a server's allowlist (whitelist).
    
    This function:
    1. Sends request to remove players from allowlist
    2. Returns success/failure message with details
    
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
    
    # Format the response with details if available
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

@mcp.tool()
async def update_server_properties(server_name: str, properties: dict) -> str:
    """Update configuration properties for a specific server.
    
    This function:
    1. Sends updated properties to the server
    2. Returns success/failure message
    
    Args:
        server_name: Name of the server to update
        properties: Dictionary of property names and their new values.
                   Only predefined allowed keys can be modified (e.g., server-name, 
                   level-name, gamemode, difficulty, max-players, etc.)
    
    Returns:
        str: Success message if properties updated successfully,
             Error message if update fails
    """
    data = await make_bedrock_request(
        f"/api/server/{server_name}/properties/set",
        method="POST",
        data=properties
    )
    if not data:
        return f"Failed to update properties for server {server_name}."
    return data.get("message", "Server properties updated successfully.")

@mcp.tool()
async def backup_server(server_name: str, backup_type: str = "world", file_to_backup: Optional[str] = None) -> str:
    """Trigger a backup for a specific Bedrock server.
    
    This function:
    1. Sends a backup command for the server with specified type
    2. Returns success/failure message
    
    Args:
        server_name: Name of the server to backup
        backup_type: Type of backup ('world', 'config', or 'all'). Defaults to 'world'
        file_to_backup: Required if backup_type is 'config'. Relative path within server directory
        
    Returns:
        str: Formatted string with the result of the backup action.
    """
    # Validate backup_type
    valid_types = ["world", "config", "all"]
    if backup_type not in valid_types:
        return f"Invalid backup_type '{backup_type}'. Must be one of: {valid_types}"
    
    # Build request data
    data = {"backup_type": backup_type}
    
    # Add file_to_backup if specified for config backup
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

@mcp.tool()
async def restore_server(server_name: str, restore_type: str, backup_file: Optional[str] = None) -> str:
    """Restore a server from a backup.
    
    Args:
        server_name: Name of the server to restore
        restore_type: Type of restore ('world', 'config', or 'all')
        backup_file: Required for 'world' and 'config' restore types. Relative path to backup file
    
    Returns:
        str: Status message about the restore operation
    """
    # Validate restore_type
    valid_types = ["world", "config", "all"]
    if restore_type not in valid_types:
        return f"Invalid restore_type '{restore_type}'. Must be one of: {valid_types}"
    
    # Build request data
    data = {"restore_type": restore_type}
    
    # Add backup_file if required
    if restore_type in ["world", "config"]:
        if not backup_file:
            return f"backup_file is required when restore_type is '{restore_type}'"
        data["backup_file"] = backup_file
    
    response = await make_bedrock_request(
        f"/api/server/{server_name}/restore/action",
        method="POST",
        data=data
    )
    if not response:
        return f"Failed to restore server '{server_name}' with type '{restore_type}'."
    
    return f"Server '{server_name}' restore initiated (type: {restore_type}). Status: {response.get('message', 'Unknown')}"

@mcp.tool()
async def get_server_process_info(server_name: str) -> str:
    """Get detailed process information for a running server.
    
    Args:
        server_name: Name of the server to get process info for
    
    Returns:
        str: Formatted process information including PID, memory usage, etc.
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/process_info")
    if not data:
        return f"Unable to fetch process info for server '{server_name}'."
    
    process_info = data.get("process_info", {})
    if not process_info:
        return f"No process information available for server '{server_name}'."
    
    info_parts = [f"Process Info for '{server_name}':"]
    for key, value in process_info.items():
        info_parts.append(f"  {key}: {value}")
    
    return "\n".join(info_parts)

@mcp.tool()
async def list_server_backups(server_name: str, backup_type: str = "world") -> str:
    """List available backup filenames for a server.
    
    Args:
        server_name: Name of the server to list backups for
        backup_type: Type of backup to list ('world', 'config', etc.)
    
    Returns:
        str: Formatted list of backup filenames
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/backups/list/{backup_type}")
    if not data:
        return f"Unable to fetch backup list for server '{server_name}'."
    
    backups = data.get("backups", [])
    if not backups:
        return f"No {backup_type} backups found for server '{server_name}'."
    
    backup_list = [f"{backup_type.title()} backups for '{server_name}':"]
    for backup in backups:
        backup_list.append(f"  - {backup}")
    
    return "\n".join(backup_list)

@mcp.tool()
async def list_available_worlds() -> str:
    """List available world files that can be installed on servers.
    
    Returns:
        str: Formatted list of available world files
    """
    data = await make_bedrock_request("/api/content/worlds")
    if not data:
        return "Unable to fetch available worlds."
    
    worlds = data.get("worlds", [])
    if not worlds:
        return "No world files available."
    
    world_list = ["Available worlds:"]
    for world in worlds:
        world_list.append(f"  - {world}")
    
    return "\n".join(world_list)

@mcp.tool()
async def list_available_addons() -> str:
    """List available addon files that can be installed on servers.
    
    Returns:
        str: Formatted list of available addon files
    """
    data = await make_bedrock_request("/api/content/addons")
    if not data:
        return "Unable to fetch available addons."
    
    addons = data.get("addons", [])
    if not addons:
        return "No addon files available."
    
    addon_list = ["Available addons:"]
    for addon in addons:
        addon_list.append(f"  - {addon}")
    
    return "\n".join(addon_list)

@mcp.tool()
async def reset_world(server_name: str) -> str:
    """Reset (delete) the current world for a server.
    
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

@mcp.tool()
async def add_players_to_global_list(player_names: list[str]) -> str:
    """Add players to the global player list.
    
    Args:
        player_names: List of player names to add to the global list
    
    Returns:
        str: Status message about the add operation
    """
    data = await make_bedrock_request(
        "/api/players/add",
        method="POST",
        data={"player_names": player_names}
    )
    if not data:
        return f"Failed to add players to global list."
    
    return f"Added {len(player_names)} players to global list. Status: {data.get('message', 'Players added successfully')}"

@mcp.tool()
async def get_panorama_image() -> str:
    """Get the custom panorama image.
    
    Returns:
        str: Information about the panorama image
    """
    data = await make_bedrock_request("/api/panorama")
    if not data:
        return "Unable to fetch panorama image information."
    
    return f"Panorama image available. Details: {data.get('message', 'Panorama image retrieved')}"

@mcp.tool()
async def get_plugin_statuses() -> str:
    """Get the status of all plugins.
    
    Returns:
        str: Formatted list of plugin statuses
    """
    data = await make_bedrock_request("/api/plugins")
    if not data:
        return "Unable to fetch plugin statuses."
    
    plugins = data.get("plugins", [])
    if not plugins:
        return "No plugins found."
    
    plugin_list = ["Plugin statuses:"]
    for plugin in plugins:
        name = plugin.get("name", "Unknown")
        status = plugin.get("status", "Unknown")
        plugin_list.append(f"  - {name}: {status}")
    
    return "\n".join(plugin_list)

@mcp.tool()
async def toggle_plugin(plugin_name: str, action: str) -> str:
    """Enable or disable a plugin.
    
    Args:
        plugin_name: Name of the plugin to toggle
        action: Action to perform ('enable' or 'disable')
    
    Returns:
        str: Status message about the plugin toggle operation
    """
    data = await make_bedrock_request(
        f"/api/plugins/{plugin_name}",
        method="POST",
        data={"action": action}
    )
    if not data:
        return f"Failed to {action} plugin '{plugin_name}'."
    
    return f"Plugin '{plugin_name}' {action}d successfully. Status: {data.get('message', f'Plugin {action}d')}"

@mcp.tool()
async def reload_all_plugins() -> str:
    """Reload all plugins.
    
    Returns:
        str: Status message about the reload operation
    """
    data = await make_bedrock_request("/api/plugins/reload", method="POST")
    if not data:
        return "Failed to reload plugins."
    
    return f"All plugins reloaded. Status: {data.get('message', 'Plugins reloaded successfully')}"

@mcp.tool()
async def trigger_plugin_event(event_name: str, event_data: dict = None) -> str:
    """Trigger a custom plugin event.
    
    Args:
        event_name: Name of the event to trigger
        event_data: Optional data to pass with the event
    
    Returns:
        str: Status message about the event trigger operation
    """
    payload = {"event_name": event_name}
    if event_data:
        payload["event_data"] = event_data
    
    data = await make_bedrock_request(
        "/api/plugins/trigger_event",
        method="POST",
        data=payload
    )
    if not data:
        return f"Failed to trigger event '{event_name}'."
    
    return f"Event '{event_name}' triggered successfully. Status: {data.get('message', 'Event triggered')}"

@mcp.tool()
async def get_player_permissions(server_name: str) -> str:
    """Get player permissions for a server.
    
    Args:
        server_name: Name of the server to get permissions for
    
    Returns:
        str: Formatted player permissions information
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/permissions/get")
    if not data:
        return f"Unable to fetch player permissions for server '{server_name}'."
    
    permissions = data.get("permissions", {})
    if not permissions:
        return f"No player permissions found for server '{server_name}'."
    
    perm_list = [f"Player permissions for '{server_name}':"]
    for player, perms in permissions.items():
        perm_list.append(f"  {player}: {perms}")
    
    return "\n".join(perm_list)

@mcp.tool()
async def get_server_version(server_name: str) -> str:
    """Retrieve the installed version of a specific server.
    
    This function:
    1. Fetches the version information from the server
    2. Returns the formatted version string
    
    Args:
        server_name: Name of the server to check
    
    Returns:
        str: Formatted string containing the server version,
             Error message if unable to fetch version
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/version")
    if not data:
        return f"Unable to fetch version for server {server_name}."
    
    # The API returns data in the format:
    # {
    #     "status": "success",
    #     "installed_version": "..."
    # }
    version = data.get("installed_version")
    if not version:
        return f"No version information found for server {server_name}."
    
    return f"Server {server_name} version: {version}"

@mcp.tool()
async def validate_server(server_name: str) -> str:
    """Verify if a server exists and is properly configured.
    
    This function:
    1. Checks server existence and configuration
    2. Returns validation results with optional explanation
    
    Args:
        server_name: Name of the server to validate
    
    Returns:
        str: Formatted string containing validation results and explanation,
             Error message if validation fails
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/validate")
    if not data:
        return f"Unable to validate server {server_name}."
    
    # The API returns data in the format:
    # Success case:
    # {
    #     "status": "success",
    #     "message": "Server '<server_name>' exists and is valid."
    # }
    # Error cases are handled by make_bedrock_request returning None
    
    message = data.get("message", f"Server {server_name} validation completed")
    return message

@mcp.tool()
async def update_server(server_name: str, version: Optional[str] = None) -> str:
    """Update a Bedrock server to the latest or a specified version.
    
    This function:
    1. Sends an update command to the server
    2. Can optionally specify a version to update to
    3. Returns success/failure message
    
    Args:
        server_name: Name of the server to update
        version: Optional version string to update to
    
    Returns:
        str: Formatted string with the result of the update action.
    """
    data = {"action": "update"}
    if version:
        data["version"] = version
        
    response = await make_bedrock_request(
        f"/api/server/{server_name}/update", 
        method="POST", 
        data=data
    )
    if not response:
        return f"Failed to send update command for server {server_name}."
    
    return response.get("message", "Update command sent.")

@mcp.tool()
async def delete_server(server_name: str) -> str:
    """Permanently delete a specific server and its data.
    
    This function:
    1. Sends delete request for the server
    2. Returns success/failure message
    
    Args:
        server_name: Name of the server to delete
    
    Returns:
        str: Success message if server deleted successfully,
             Error message if deletion fails
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/delete", method="DELETE")
    if not data:
        return f"Failed to delete server {server_name}."
    
    # The API returns data in the format:
    # {
    #     "status": "success",
    #     "message": "Server deleted successfully"
    # }
    message = data.get("message", "Server deleted")
    return f"{message} for server {server_name}"

@mcp.tool()
async def prune_backups(server_name: str, keep: Optional[int] = None) -> str:
    """Prune older backups for a specific server.
    
    This function:
    1. Deletes older backups while keeping the specified number of newest ones
    2. Handles world backups, server properties backups, and JSON config backups
    
    Args:
        server_name: Name of the server whose backups to prune
        keep: Optional number of backups to keep (defaults to server config)
    
    Returns:
        str: Success message if pruning completed successfully,
             Error message if pruning fails
    """
    data = await make_bedrock_request(
        f"/api/server/{server_name}/backups/prune",
        method="POST",
        data={"keep": keep} if keep is not None else None
    )
    if not data:
        return f"Failed to prune backups for server {server_name}."
    
    # The API returns data in the format:
    # {
    #     "status": "success",
    #     "message": "Backup pruning completed for server '<server_name>'"
    # }
    return data.get("message", f"Backup pruning completed for server {server_name}")

@mcp.tool()
async def export_world(server_name: str) -> str:
    """Export the world from a specific server.
    
    Args:
        server_name: Name of the server to export world from
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/world/export", method="POST")
    if not data:
        return f"Failed to export world for server {server_name}."
    
    # The API returns data in the format:
    # {
    #     "status": "success",
    #     "message": "World export started successfully",
    #     "data": {
    #         "export_path": "..."  # Optional path where the world was exported
    #     }
    # }
    message = data.get("message", "World export started")
    export_path = data.get("data", {}).get("export_path")
    
    result = f"{message} for server {server_name}"
    if export_path:
        result += f"\nExport path: {export_path}"
    
    return result

@mcp.tool()
async def install_world(server_name: str, filename: str) -> str:
    """Install a world from a .mcworld file to a specific Bedrock server.
    
    This function:
    1. Sends a command to install a world from the specified filename
    2. Returns success/failure message
    
    Args:
        server_name: Name of the server to install the world on
        filename: Relative path to the .mcworld file within the content/worlds directory
        
    Returns:
        str: Formatted string with the result of the world installation.
    """
    data = {"filename": filename}
    response = await make_bedrock_request(
        f"/api/server/{server_name}/world/install", 
        method="POST", 
        data=data
    )
    if not response:
        return f"Failed to install world '{filename}' on server {server_name}."
        
    return response.get("message", f"World '{filename}' install command sent.")

@mcp.tool()
async def install_addon(server_name: str, filename: str) -> str:
    """Install an addon pack (.mcaddon or .mcpack) to a specific Bedrock server.
    
    This function:
    1. Sends a command to install an addon from the specified filename
    2. Returns success/failure message
    
    Args:
        server_name: Name of the server to install the addon on
        filename: Relative path to the .mcaddon or .mcpack file within the content/addons directory
        
    Returns:
        str: Formatted string with the result of the addon installation.
    """
    data = {"filename": filename}
    response = await make_bedrock_request(
        f"/api/server/{server_name}/addon/install", 
        method="POST", 
        data=data
    )
    if not response:
        return f"Failed to install addon '{filename}' on server {server_name}."
        
    return response.get("message", f"Addon '{filename}' install command sent.")

@mcp.tool()
async def get_server_properties(server_name: str) -> str:
    """Get all server properties for a specific server.
    
    This function retrieves all key-value pairs from the server's server.properties file.
    
    Args:
        server_name: Name of the server to get properties for
    
    Returns:
        str: Formatted string containing all server properties.
             Returns error message if unable to fetch properties.
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/properties/get")
    if not data:
        return f"Unable to fetch properties for server {server_name}."
    
    # The API returns data in the format:
    # {
    #     "status": "success",
    #     "properties": {
    #         "server-name": "...",
    #         "gamemode": "...",
    #         "difficulty": "...",
    #         ...
    #     }
    # }
    properties = data.get("properties", {})
    if not properties:
        return f"No properties found for server {server_name}."
    
    # Format properties in a readable way
    property_list = [f"Properties for server {server_name}:"]
    for key, value in sorted(properties.items()):
        property_list.append(f"  {key}: {value}")
    
    return "\n".join(property_list)

@mcp.tool()
async def scan_player_logs() -> str:
    """Scan player logs to detect and record player information.
    
    This function:
    1. Scans server logs for player information
    2. Updates the central players.json file
    
    Returns:
        str: Success message with number of players found,
             Error message if scan fails
    """
    data = await make_bedrock_request("/api/players/scan", method="POST")
    if not data:
        return "Failed to scan player logs."
    
    # The API returns data in the format:
    # {
    #     "status": "success",
    #     "message": "Player scan completed successfully",
    #     "players_found": 123  # Optional count of players found
    # }
    message = data.get("message", "Player scan completed")
    players_found = data.get("players_found")
    
    result = message
    if players_found is not None:
        result += f"\nPlayers found: {players_found}"
    
    return result

@mcp.tool()
async def get_players() -> str:
    """Retrieve a list of all known players from the player logs.
    
    This function retrieves:
    - Player names
    - Player XUIDs
    - Any additional player information (e.g., notes)
    
    Returns:
        str: Formatted string containing all known players.
             Returns error message if unable to fetch players.
    """
    data = await make_bedrock_request("/api/players/get")
    if not data:
        return "Unable to fetch player list."
    
    # The API returns data in the format:
    # {
    #     "status": "success",
    #     "players": [
    #         {
    #             "name": "PlayerOne",
    #             "xuid": "2535414141111111",
    #             "notes": "Main admin"  # Optional
    #         },
    #         ...
    #     ]
    # }
    players = data.get("players", [])
    if not players:
        return "No players found."
    
    # Format the player list
    player_list = ["Known Players:"]
    for player in players:
        player_info = f"Name: {player.get('name', 'Unknown')}"
        player_info += f"\nXUID: {player.get('xuid', 'Unknown')}"
        if "notes" in player:
            player_info += f"\nNotes: {player['notes']}"
        player_list.append(player_info)
    
    return "\n\n".join(player_list)

@mcp.tool()
async def update_player_permissions(server_name: str, permissions: dict) -> str:
    """Update the permission level for players on a Bedrock server.
    
    This function:
    1. Sends updated permission settings to the server
    2. Returns success/failure message
    
    Args:
        server_name: Name of the server
        permissions: Dictionary mapping player XUIDs (strings) to permission levels.
                    Valid levels: 'visitor', 'member', 'operator'
    
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
    
    # The API returns data in the format:
    # {
    #     "status": "success",
    #     "message": "Permissions updated successfully for X player(s) on server '<server_name>'"
    # }
    message = data.get("message", "Player permissions updated")
    return message

@mcp.tool()
async def configure_service(server_name: str, service_config: dict) -> str:
    """Configure OS-level service settings for a specific server.
    
    This function:
    1. Sends service configuration to the server
    2. Returns success/failure message
    
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

@mcp.tool()
async def prune_downloads() -> str:
    """Prune the download cache."""
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

@mcp.tool()
async def install_new_server(server_config: dict) -> str:
    """Install a new Bedrock server with a given configuration.
    
    This function sends a request to install a new server. The server_config
    dictionary should contain all necessary parameters like 'name', 'version', etc.
    
    Args:
        server_config: Dictionary containing the server configuration details.
        
    Returns:
        str: Result of the installation request.
    """
    response = await make_bedrock_request(
        "/api/server/install",
        method="POST",
        data=server_config
    )
    if not response:
        return "Failed to send install new server command."
        
    return response.get("message", "Install new server command sent.")

@mcp.tool()
async def get_system_info() -> str:
    """Get system and application information.
    
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

@mcp.tool()
async def get_config_status(server_name: str) -> str:
    """Get the configuration status for a specific Bedrock server.
    
    This function retrieves:
    - Configuration status string from the server's config file
    
    Args:
        server_name: Name of the server to check
    
    Returns:
        str: Formatted string containing configuration status.
             Returns error message if unable to fetch status.
    """
    data = await make_bedrock_request(f"/api/server/{server_name}/config_status")
    if not data:
        return f"Unable to fetch config status for server {server_name}."
    
    # The API returns data in the format:
    # {
    #     "status": "success",
    #     "config_status": "Installed"
    # }
    config_status = data.get("config_status")
    
    if not config_status:
        return f"Could not determine config status for server {server_name}."
    
    return f"Configuration status for server {server_name}: {config_status}"

# --- Task Scheduler Functions ---

@mcp.tool()
async def add_cron_job(server_name: str, job_details: dict) -> str:
    """Add a new cron job for a server (Linux only).
    
    Args:
        server_name: Name of the server.
        job_details: Dictionary with job details (e.g., {"minute": "0", "hour": "*/6", "day_of_week": "*", "command": "backup"}).
        
    Returns:
        str: Result of the request.
    """
    response = await make_bedrock_request(
        f"/api/server/{server_name}/cron_scheduler/add",
        method="POST",
        data=job_details
    )
    if not response:
        return "Failed to send add cron job command."
    return response.get("message", "Add cron job command sent.")

@mcp.tool()
async def modify_cron_job(server_name: str, job_details: dict) -> str:
    """Modify an existing cron job for a server (Linux only).
    
    Args:
        server_name: Name of the server.
        job_details: Dictionary with job details to modify.
        
    Returns:
        str: Result of the request.
    """
    response = await make_bedrock_request(
        f"/api/server/{server_name}/cron_scheduler/modify",
        method="POST",
        data=job_details
    )
    if not response:
        return "Failed to send modify cron job command."
    return response.get("message", "Modify cron job command sent.")

@mcp.tool()
async def delete_cron_job(server_name: str, job_id: str) -> str:
    """Delete a cron job for a server (Linux only).
    
    Args:
        server_name: Name of the server.
        job_id: The ID of the cron job to delete.
        
    Returns:
        str: Result of the request.
    """
    data = {"job_id": job_id}
    response = await make_bedrock_request(
        f"/api/server/{server_name}/cron_scheduler/delete",
        method="DELETE",
        data=data
    )
    if not response:
        return "Failed to send delete cron job command."
    return response.get("message", "Delete cron job command sent.")

@mcp.tool()
async def add_windows_task(server_name: str, task_details: dict) -> str:
    """Add a new Windows Task for a server (Windows only).
    
    Args:
        server_name: Name of the server.
        task_details: Dictionary with task details.
        
    Returns:
        str: Result of the request.
    """
    response = await make_bedrock_request(
        f"/api/server/{server_name}/task_scheduler/add",
        method="POST",
        data=task_details
    )
    if not response:
        return "Failed to send add windows task command."
    return response.get("message", "Add windows task command sent.")

@mcp.tool()
async def get_windows_task_details(server_name: str, task_name: str) -> str:
    """Get details of a Windows Task for a server (Windows only).
    
    Args:
        server_name: Name of the server.
        task_name: The name of the task.
        
    Returns:
        str: Task details or error message.
    """
    response = await make_bedrock_request(
        f"/api/server/{server_name}/task_scheduler/details",
        method="POST",
        data={"task_name": task_name}
    )
    if not response:
        return "Failed to get windows task details."
    return json.dumps(response.get("data", {}), indent=2)

@mcp.tool()
async def modify_windows_task(server_name: str, task_name: str, task_details: dict) -> str:
    """Modify a Windows Task for a server (Windows only).
    
    Args:
        server_name: Name of the server.
        task_name: The name of the task to modify.
        task_details: Dictionary with the updated task details.
        
    Returns:
        str: Result of the request.
    """
    response = await make_bedrock_request(
        f"/api/server/{server_name}/task_scheduler/task/{task_name}",
        method="PUT",
        data=task_details
    )
    if not response:
        return "Failed to send modify windows task command."
    return response.get("message", "Modify windows task command sent.")

@mcp.tool()
async def delete_windows_task(server_name: str, task_name: str) -> str:
    """Delete a Windows Task for a server (Windows only).
    
    Args:
        server_name: Name of the server.
        task_name: The name of the task to delete.
        
    Returns:
        str: Result of the request.
    """
    response = await make_bedrock_request(
        f"/api/server/{server_name}/task_scheduler/task/{task_name}",
        method="DELETE"
    )
    if not response:
        return "Failed to send delete windows task command."
    return response.get("message", "Delete windows task command sent.")

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio') 