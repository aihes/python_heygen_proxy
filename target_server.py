import asyncio
import websockets
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def target_server(websocket, path):
    client_id = id(websocket)
    logger.info(f"New client connected to target server. ID: {client_id}")
    
    try:
        async for message in websocket:
            logger.info(f"Target server received from client {client_id}: {message}")
            
            # 添加时间戳并返回消息
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            response = f"[{timestamp}] Echo: {message}"
            
            logger.info(f"Target server sending to client {client_id}: {response}")
            await websocket.send(response)
            
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Client {client_id} connection closed")
    except Exception as e:
        logger.error(f"Error with client {client_id}: {str(e)}")
    finally:
        logger.info(f"Client {client_id} connection terminated")

async def main():
    server = await websockets.serve(
        target_server,
        'localhost',
        8765,
        ping_interval=None
    )
    
    logger.info("Target WebSocket server is running on ws://localhost:8765")
    logger.info("Ready to receive messages...")
    
    try:
        await asyncio.Future()  # 保持服务器运行
    except KeyboardInterrupt:
        logger.info("Shutting down target server...")
    finally:
        server.close()
        await server.wait_closed()
        logger.info("Target server shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
