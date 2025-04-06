import json
import asyncio
import os
from dotenv import load_dotenv
from work.foundry_bridge_ws import FoundryBridgeWSServer  # server class, not client

# 📁 Config
env_path = os.path.join(os.path.dirname(__file__), 'config', '.env')
load_dotenv(dotenv_path=env_path)

TOKEN_FILE = "../assets/token_locations.json"
DEFAULT_TOKEN_IMG = "icons/svg/dice-target.svg"

async def sync_tokens():
    import os
    print(os.getcwd())
    if not os.path.exists(TOKEN_FILE):
        print(f"[❌] Missing token data: {TOKEN_FILE}")
        return

    with open(TOKEN_FILE, "r") as f:
        data = json.load(f)

    bridge = FoundryBridgeWSServer()
    asyncio.create_task(bridge.start())  # start the server in background

    # Give Foundry time to connect
    await asyncio.sleep(2)

    for scene_name, tokens in data.items():
        print(f"📄 Scene: {scene_name}")
        for token_name, coords in tokens.items():
            print(f"  ⬆️ Placing: {token_name} → {coords}")
            await bridge.place_named_token(
                scene_name=scene_name,
                token_name=token_name,
                coords=coords
            )

    print("\n✅ All tokens synced to Foundry via WebSocket.")

    # Keep the server alive to handle further commands
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(sync_tokens())
