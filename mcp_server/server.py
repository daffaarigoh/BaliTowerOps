from mcp.server.mcpserver import MCPServer
from mcp_server.tools import (
    calculate_safety_stock,
    calculate_reorder_quantity,
    get_low_stock_items,
    get_specific_item_stock,
    get_best_vendors,
    get_all_vendors_for_item,
    get_all_inventory_items
)

# Initialize the MCP Server
mcp = MCPServer("BaliTowerOps-MCP")

@mcp.tool()
def safety_stock(min_threshold: int) -> int:
    """Calculate the safety stock needed for an item."""
    return calculate_safety_stock(min_threshold)

@mcp.tool()
def reorder_quantity(current_stock: int, max_threshold: int) -> int:
    """Calculate the optimal reorder quantity for an item."""
    return calculate_reorder_quantity(current_stock, max_threshold)

@mcp.tool()
def fetch_low_stock(tenant_id: str = "ALL") -> list[dict]:
    """Retrieve items with stock below the minimum threshold."""
    return get_low_stock_items(tenant_id)

@mcp.tool()
def fetch_item_stock(item_name: str, tenant_id: str = "ALL") -> list[dict]:
    """Retrieve specific items matching a given name."""
    return get_specific_item_stock(item_name, tenant_id)

@mcp.tool()
def fetch_best_vendor(item_id: str, tenant_id: str = "ALL") -> dict:
    """Find the best vendor for a given item_id."""
    res = get_best_vendors(item_id, tenant_id)
    return res if res else {}

@mcp.tool()
def fetch_vendors_for_item(item_id: str, tenant_id: str = "ALL") -> list[dict]:
    """Get all available vendors offering a specific item."""
    return get_all_vendors_for_item(item_id, tenant_id)

@mcp.tool()
def fetch_all_inventory(tenant_id: str = "ALL") -> list[dict]:
    """Retrieve all inventory items from DuckDB."""
    return get_all_inventory_items(tenant_id)

if __name__ == "__main__":
    mcp.run()
