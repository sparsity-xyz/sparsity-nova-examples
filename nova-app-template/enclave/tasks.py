"""
=============================================================================
Background Tasks (tasks.py)
=============================================================================

Define your periodic background jobs here.

┌─────────────────────────────────────────────────────────────────────────────┐
│  MODIFY THIS FILE                                                           │
│  Add your own background tasks / cron jobs here.                            │
└─────────────────────────────────────────────────────────────────────────────┘

How it works:
    - background_task() is called every 5 minutes by the scheduler
    - You can access app_state and odyn after init() is called
    - Modify the interval in app.py if needed

Example use cases:
    - Auto-save state to S3
    - Periodic data sync
    - Heartbeat / health reporting
    - Scheduled on-chain transactions
"""

import os
import logging
from typing import Optional

# Type hint for Odyn (actual import would cause circular dependency)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from odyn import Odyn

logger = logging.getLogger("nova-app.tasks")

# =============================================================================
# Shared References (set by app.py during startup)
# =============================================================================
app_state: Optional[dict] = None
odyn: Optional["Odyn"] = None


def init(state_ref: dict, odyn_ref: "Odyn"):
    """
    Initialize the tasks module with shared references.
    
    Called by app.py during startup. Do not call directly.
    
    Args:
        state_ref: Reference to app_state dict
        odyn_ref: Reference to Odyn instance
    """
    global app_state, odyn
    app_state = state_ref
    odyn = odyn_ref
    logger.info("Tasks module initialized")


# =============================================================================
# Your Background Tasks (MODIFY BELOW)
# =============================================================================

def background_task():
    """
    Main background task - runs every 5 minutes.
    
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  MODIFY THIS FUNCTION                                                   │
    │  Add your own periodic logic here.                                      │
    └─────────────────────────────────────────────────────────────────────────┘
    
    Available resources:
        - app_state["data"]  → Your persistent application data
        - odyn.eth_address() → TEE's Ethereum address
        - odyn.s3_put/s3_get → S3 storage operations
        - odyn.save_state()  → Save JSON state to S3
        - odyn.sign_tx()     → Sign Ethereum transactions
    """
    if app_state is None:
        logger.warning("Tasks not initialized yet")
        return
    
    # --- Example: Track task execution ---
    app_state["cron_counter"] = app_state.get("cron_counter", 0) + 1
    app_state["last_cron_run"] = os.popen("date").read().strip()
    
    logger.info(f"Cron job #{app_state['cron_counter']} at {app_state['last_cron_run']}")
    
    # --- Example: Auto-save state every interval ---
    try:
        if app_state.get("initialized") and odyn:
            success = odyn.save_state(app_state.get("data", {}), "app_state.json")
            if success:
                logger.info("Auto-saved state to S3")
            else:
                logger.warning("State save returned False")
    except Exception as e:
        logger.error(f"Cron auto-save failed: {e}")
    
    # --- Add your own logic below ---
    # Example: Send heartbeat to on-chain contract
    # Example: Fetch external data and update state
    # Example: Trigger periodic computations

