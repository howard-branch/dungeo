import asyncio
import websockets
import json

class FoundryBridgeWSServer:
    def __init__(self, host="localhost", port=8765):
        self.clients = set()
        self.host = host
        self.port = port

    async def handler(self, websocket):
        self.clients.add(websocket)
        print(f"[🟢] Client connected: {websocket.remote_address}")
        try:
            while True:
                await asyncio.sleep(1)
        except websockets.exceptions.ConnectionClosed:
            print(f"[🔌] Client disconnected: {websocket.remote_address}")
        finally:
            self.clients.remove(websocket)

    async def send(self, payload):
        if not self.clients:
            print("[⚠️] No Foundry client connected. Command not sent.")
            return

        message = json.dumps(payload)
        for client in self.clients:
            try:
                await client.send(message)
                print(f"[➡️] Sent to Foundry: {message}")
            except Exception as e:
                print(f"[❌] Failed to send to {client.remote_address}: {e}")

    async def place_named_token(self, scene_name, token_name, coords, img="icons/svg/mystery-man.svg"):
        await self.send({
            "command": "placeToken",
            "sceneName": scene_name,
            "tokenName": token_name,
            "coords": coords,
            "img": img
        })

    async def move_token(self, token_name, scene_name, x, y):
        await self.send({
            "command": "moveToken",
            "sceneName": scene_name,
            "tokenName": token_name,
            "coords": [x, y]
        })

    async def send_custom_command(self, command_dict):
        await self.send(command_dict)

    async def start(self):
        print(f"[🌐] Starting Foundry WebSocket server at ws://{self.host}:{self.port}")
        async with websockets.serve(self.handler, self.host, self.port):
            await asyncio.Future()  # run forever

# Optional: run server directly for testing
if __name__ == "__main__":
    bridge = FoundryBridgeWSServer()
    asyncio.run(bridge.start())
