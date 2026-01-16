"""
=============================================================================
User Routes (routes.py)
=============================================================================

Define your custom API endpoints here.

┌─────────────────────────────────────────────────────────────────────────────┐
│  MODIFY THIS FILE                                                           │
│  Add your own API endpoints and business logic here.                        │
└─────────────────────────────────────────────────────────────────────────────┘

How it works:
    - All routes are prefixed with /api (e.g., /api/echo)
    - You can access app_state and odyn after init() is called
    - Use FastAPI's standard decorators (@router.get, @router.post, etc.)

Example endpoints included:
    - POST /api/echo  → Echo back a message with TEE address
    - GET  /api/info  → Get app info and state keys
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

# Type hint for Odyn (actual import would cause circular dependency)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from odyn import Odyn

logger = logging.getLogger("nova-app.routes")

# =============================================================================
# Shared References (set by app.py during startup)
# =============================================================================
app_state: Optional[dict] = None
odyn: Optional["Odyn"] = None


def init(state_ref: dict, odyn_ref: "Odyn"):
    """
    Initialize the routes module with shared references.
    
    Called by app.py during startup. Do not call directly.
    
    Args:
        state_ref: Reference to app_state dict
        odyn_ref: Reference to Odyn instance
    """
    global app_state, odyn
    app_state = state_ref
    odyn = odyn_ref
    logger.info("Routes module initialized")


# =============================================================================
# Router Configuration
# =============================================================================
# All routes will be prefixed with /api
# Example: @router.get("/hello") → GET /api/hello
router = APIRouter(prefix="/api", tags=["user"])


# =============================================================================
# Your API Endpoints (MODIFY BELOW)
# =============================================================================

# --- Request/Response Models ---
class EchoRequest(BaseModel):
    """Request model for echo endpoint."""
    message: str

class EchoResponse(BaseModel):
    """Response model for echo endpoint."""
    reply: str
    tee_address: Optional[str] = None


# --- Example Endpoints ---

@router.post("/echo", response_model=EchoResponse)
def echo_example(req: EchoRequest):
    """
    Example endpoint: Echo back a message.
    
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  REPLACE THIS WITH YOUR OWN LOGIC                                       │
    └─────────────────────────────────────────────────────────────────────────┘
    
    Available resources:
        - app_state["data"]  → Your persistent application data
        - odyn.eth_address() → TEE's Ethereum address
        - odyn.state_save()  → Save encrypted state to S3
        - odyn.sign_tx()     → Sign Ethereum transactions
    """
    try:
        address = odyn.eth_address() if odyn else "unknown"
    except:
        address = "unavailable"
    
    return EchoResponse(
        reply=f"Echo: {req.message}",
        tee_address=address
    )


@router.get("/info")
def get_info():
    """
    Example endpoint: Get app info.
    
    Returns the current state keys stored in the application.
    """
    return {
        "app": "Nova App Template",
        "state_keys": list(app_state.get("data", {}).keys()) if app_state else []
    }


# =============================================================================
# Add Your Own Endpoints Below
# =============================================================================

# @router.post("/your-endpoint")
# def your_endpoint(req: YourRequestModel):
#     """Your custom logic here."""
#     pass
