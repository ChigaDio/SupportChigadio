import asyncio
import websockets
import json

# List to keep track of connected WebSocket clients
connected_clients = set()

# WebSocket server to handle clients (Unity C# and React)
async def handle_websocket(websocket):
    # Register client
    connected_clients.add(websocket)
    print(f"Client connected. Total clients: {len(connected_clients)}")
    
    try:
        # Listen for messages from the client (e.g., from Unity)
        async for message in websocket:
            try:
                # Parse incoming message as JSON (from Unity's SendLog)
                data = json.loads(message)
                print(f"Received message: {data}")
                
                # Forward the message to all other connected clients (e.g., React)
                if connected_clients:
                    await broadcast_message(data)
                    
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON message: {e}")
                # Optionally, send an error back to the sender
                await websocket.send(json.dumps({"error": "Invalid JSON"}))
            except Exception as e:
                print(f"Error handling message: {e}")
                
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    finally:
        # Unregister client
        connected_clients.remove(websocket)
        print(f"Client disconnected. Total clients: {len(connected_clients)}")

# Broadcast message to all connected WebSocket clients (except the sender)
async def broadcast_message(message):
    if connected_clients:
        # Create a list of tasks to send to all clients
        tasks = []
        for client in list(connected_clients):
            try:
                tasks.append(client.send(json.dumps(message)))
            except:
                # If send fails, remove the client
                connected_clients.discard(client)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

# Start the WebSocket server
async def start_websocket_server():
    server = await websockets.serve(handle_websocket, "localhost", 8765)
    print("WebSocket server started on ws://localhost:8765")
    print("Waiting for clients (Unity and React)...")
    await server.wait_closed()

# Main function
async def main():
    await start_websocket_server()
    
def mainServer():
    asyncio.run(start_websocket_server())
