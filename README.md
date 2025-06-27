# Bedrock Server Manager MCP Server

A comprehensive Model Context Protocol (MCP) server that provides natural language access to [Bedrock Server Manager](https://github.com/EnviousData/BedrockServerManager) functionality. This server enables you to manage your Minecraft Bedrock Edition servers through AI assistants like Claude Desktop using simple conversational commands.

## 🚀 Features

### Server Management
- **Server Lifecycle**: Start, stop, restart, and monitor server status
- **Server Installation**: Install new servers with custom configurations
- **Server Updates**: Update servers to specific versions or latest releases
- **Server Validation**: Verify server integrity and configuration

### Player & World Management
- **Allowlist Management**: Add/remove players from server allowlists
- **Player Permissions**: View and manage player permission levels
- **World Operations**: Reset worlds, export/import world files, install custom worlds
- **Global Player Lists**: Manage global player lists across servers

### Backup & Restore
- **Automated Backups**: Create server and world backups on demand
- **Backup Management**: List, prune, and manage backup files
- **Restore Operations**: Restore servers from specific backup files
- **Export/Import**: Export worlds and import custom content

### Advanced Features
- **Add-on Management**: Install and manage Bedrock add-ons
- **Plugin Control**: Enable/disable plugins, reload configurations, trigger events
- **Scheduled Tasks**: Create and manage cron jobs (Linux/macOS) or Windows tasks
- **System Monitoring**: View system information and server process details
- **Configuration Management**: Update server properties and service configurations

## 📋 Prerequisites

- Python 3.8 or higher
- Access to a running [Bedrock Server Manager](https://github.com/EnviousData/BedrockServerManager) instance
- Valid credentials for your Bedrock Server Manager

## 🛠️ Installation

### 1. Clone or Download
```bash
git clone <repository-url>
cd BedrockMCP
```

### 2. Create Virtual Environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
Create a `.env` file in the project root:

```env
# Required: Your Bedrock Server Manager API endpoint
BEDROCK_API_BASE=http://localhost:11325

# Required: Authentication credentials
BEDROCK_SERVER_MANAGER_USERNAME=your_username
BEDROCK_SERVER_MANAGER_PASSWORD=your_password

# Optional: Enable debug output for API responses
BEDROCK_DEBUG=false
```

**Configuration Notes:**
- The default Bedrock Server Manager port is `11325`
- Replace `localhost` with your server's IP address if running remotely
- Ensure your Bedrock Server Manager instance is running and accessible

## 🎯 Usage

### Standalone Mode
```bash
python bedrock_mcp_server.py
```

Add `--debug` flag for detailed API response logging:
```bash
python bedrock_mcp_server.py --debug
```

### With Claude Desktop

1. **Open Claude Desktop Configuration**
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

2. **Add MCP Server Configuration**
   ```json
   {
     "mcpServers": {
       "bedrock-server-manager": {
         "command": "/path/to/your/BedrockMCP/start_bedrock_mcp.sh",
         "args": []
       }
     }
   }
   ```

3. **Make Start Script Executable** (macOS/Linux)
   ```bash
   chmod +x start_bedrock_mcp.sh
   ```

4. **Update Script Path**
   Edit `start_bedrock_mcp.sh` and update the project path on line 4:
   ```bash
   cd /your/actual/path/to/BedrockMCP
   ```

5. **Restart Claude Desktop**

## 🔧 Available Tools

<details>
<summary><strong>Server Management (8 tools)</strong></summary>

- `get_servers()` - List all servers and their status
- `get_server_status(server_name)` - Get detailed server status
- `start_server(server_name)` - Start a specific server
- `stop_server(server_name)` - Stop a specific server
- `restart_server(server_name)` - Restart a specific server
- `get_server_process_info(server_name)` - Get server process information
- `delete_server(server_name)` - Delete a server permanently
- `install_new_server(server_config)` - Install a new server with configuration

</details>

<details>
<summary><strong>Player & Permissions (6 tools)</strong></summary>

- `get_allowlist(server_name)` - Get server allowlist
- `add_players_to_allowlist(server_name, player_names, ignores_player_limit)` - Add players to allowlist
- `remove_from_allowlist(server_name, player_names)` - Remove players from allowlist
- `get_player_permissions(server_name)` - View player permissions
- `update_player_permissions(server_name, permissions)` - Update player permissions
- `add_players_to_global_list(player_names)` - Add players to global list

</details>

<details>
<summary><strong>Backup & Restore (4 tools)</strong></summary>

- `backup_server(server_name, backup_type, file_to_backup)` - Create server backup
- `restore_server(server_name, restore_type, backup_file)` - Restore from backup
- `list_server_backups(server_name, backup_type)` - List available backups
- `prune_backups(server_name, keep)` - Clean up old backups

</details>

<details>
<summary><strong>World & Content Management (6 tools)</strong></summary>

- `reset_world(server_name)` - Reset server world
- `export_world(server_name)` - Export world files
- `install_world(server_name, filename)` - Install custom world
- `install_addon(server_name, filename)` - Install add-on
- `list_available_worlds()` - List available world files
- `list_available_addons()` - List available add-ons

</details>

<details>
<summary><strong>Configuration & Properties (4 tools)</strong></summary>

- `get_server_properties(server_name)` - Get server configuration
- `update_server_properties(server_name, properties)` - Update server settings
- `get_config_status(server_name)` - Check configuration status
- `configure_service(server_name, service_config)` - Configure service settings

</details>

<details>
<summary><strong>Plugins & Events (4 tools)</strong></summary>

- `get_plugin_statuses()` - List plugin status
- `toggle_plugin(plugin_name, action)` - Enable/disable plugins
- `reload_all_plugins()` - Reload all plugins
- `trigger_plugin_event(event_name, event_data)` - Trigger custom events

</details>

<details>
<summary><strong>Scheduled Tasks (6 tools)</strong></summary>

- `add_cron_job(server_name, job_details)` - Add cron job (Linux/macOS)
- `modify_cron_job(server_name, job_details)` - Modify cron job
- `delete_cron_job(server_name, job_id)` - Delete cron job
- `add_windows_task(server_name, task_details)` - Add Windows task
- `modify_windows_task(server_name, task_name, task_details)` - Modify Windows task
- `delete_windows_task(server_name, task_name)` - Delete Windows task

</details>

<details>
<summary><strong>System & Maintenance (6 tools)</strong></summary>

- `send_command(server_name, command)` - Send console command to server
- `get_system_info()` - Get system information
- `get_server_version(server_name)` - Check server version
- `validate_server(server_name)` - Validate server installation
- `update_server(server_name, version)` - Update server to specific version
- `prune_downloads()` - Clean up download cache

</details>

## 💬 Example Commands

Once configured with Claude Desktop, you can use natural language commands like:

### Server Operations
- *"What servers do I have and what's their status?"*
- *"Start my survival server"*
- *"Stop the creative server and then restart it"*
- *"What's the detailed status of my main server?"*

### Player Management
- *"Who's on the allowlist for my survival server?"*
- *"Add Steve and Alex to the survival server allowlist"*
- *"Remove Bob from the creative server allowlist"*
- *"What are the player permissions on my server?"*

### Server Commands
- *"Send the 'list' command to my survival server"*
- *"Tell all players on the creative server that the server will restart in 5 minutes"*
- *"Change the difficulty to hard on my survival server"*

### Backup Operations
- *"Create a backup of my survival server"*
- *"Show me all backups for the creative server"*
- *"Restore my survival server from yesterday's backup"*
- *"Delete old backups, keeping only the last 5"*

### World Management
- *"Reset the world on my testing server"*
- *"Install the 'skyblock' world on my adventure server"*
- *"Export the world from my survival server"*

### Advanced Operations
- *"Update my main server to the latest version"*
- *"Install the better-spawning addon on all my servers"*
- *"Create a daily backup job for my survival server"*
- *"Show me the system information"*

## 🔍 Troubleshooting

### Connection Issues
1. **Verify Bedrock Server Manager is running**
   ```bash
   curl http://localhost:11325/api/health
   ```

2. **Check credentials in .env file**
   - Ensure username and password are correct
   - Verify BEDROCK_API_BASE URL is accessible

3. **Enable debug mode**
   ```bash
   python bedrock_mcp_server.py --debug
   ```

### Common Problems

**"Unable to fetch servers list"**
- Check if Bedrock Server Manager is running
- Verify network connectivity to the API endpoint
- Confirm authentication credentials

**"Login failed"**
- Double-check username and password in `.env`
- Ensure Bedrock Server Manager allows API access

**Script permission errors (macOS/Linux)**
```bash
chmod +x start_bedrock_mcp.sh
```

## 📝 Dependencies

- **mcp** (>=1.2.0) - Model Context Protocol implementation
- **httpx** (>=0.24.0) - Modern HTTP client for API requests
- **python-dotenv** (>=1.0.0) - Environment variable management

## 🤝 Contributing

This project interfaces with [Bedrock Server Manager](https://github.com/EnviousData/BedrockServerManager). For issues related to the server manager itself, please refer to that project's repository.

## 📄 License

This project is provided as-is for educational and personal use. Please respect the licenses of the underlying Bedrock Server Manager and Minecraft Bedrock Edition. 