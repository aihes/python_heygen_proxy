from flask import Flask, request, Response
from flask_sockets import Sockets
import websockets.sync.client as websockets_client
import requests
import logging
import sys
from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler
from datetime import datetime
import json
import ssl
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置参数
PROXY_HOST = 'localhost'
PROXY_PORT = 8766
HTTP_TARGET_URI = 'https://api.heygen.com'  # HTTP目标服务器地址
WS_TARGET_URI = 'wss://api.heygen.com/v1/ws'  # WebSocket目标服务器地址

app = Flask(__name__)
sockets = Sockets(app)

def connect_to_ws_target(client_id, max_retries=3, retry_delay=1):
    """尝试连接到目标WebSocket服务器"""
    for attempt in range(max_retries):
        try:
            return websockets_client.connect(WS_TARGET_URI)
        except Exception as e:
            if attempt < max_retries - 1:
                delay = retry_delay * (attempt + 1)
                logger.warning(f"Client {client_id}: Failed to connect to target server (attempt {attempt + 1}/{max_retries}). Retrying in {delay}s... Error: {str(e)}")
                time.sleep(delay)
            else:
                logger.error(f"Client {client_id}: Failed to connect to target server after {max_retries} attempts")
                raise

@sockets.route('/v1/ws')
def handle_websocket(ws):
    """处理WebSocket连接"""
    client_id = id(ws)
    logger.info(f"New WebSocket client connected. ID: {client_id}")
    target_ws = None
    
    if not ws.closed:
        try:
            # 连接到目标服务器
            logger.info(f"Client {client_id}: Connecting to Heygen WebSocket server")
            target_ws = connect_to_ws_target(client_id)
            logger.info(f"Client {client_id}: Connected to Heygen successfully")
            
            while not ws.closed:
                # 接收客户端消息
                message = ws.receive()
                if message is None:
                    break
                
                # 记录并转发客户端消息到目标服务器
                logger.info(f"Client {client_id} -> Heygen: {message}")
                target_ws.send(message)
                
                # 等待并转发目标服务器响应
                try:
                    response = target_ws.recv()
                    logger.info(f"Heygen -> Client {client_id}: {response}")
                    ws.send(response)
                except Exception as e:
                    logger.error(f"Error receiving from Heygen: {str(e)}")
                    break
                    
        except Exception as e:
            logger.error(f"Client {client_id}: Error occurred: {str(e)}")
        finally:
            logger.info(f"Client {client_id}: Connection terminated")
            if target_ws:
                target_ws.close()

@app.route('/help')
def help_page():
    """帮助页面，显示API代理服务器的使用说明"""
    return f"""
    <html>
        <head>
            <title>API Proxy Help</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    line-height: 1.6;
                }}
                code {{
                    background-color: #f4f4f4;
                    padding: 2px 5px;
                    border-radius: 3px;
                }}
                .endpoint {{
                    margin: 20px 0;
                    padding: 15px;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                }}
            </style>
        </head>
        <body>
            <h1>API Proxy Service Documentation</h1>
            
            <div class="endpoint">
                <h2>HTTP Endpoints</h2>
                <p>所有 HTTP 请求都会被转发到 Heygen API 服务器：</p>
                <code>{HTTP_TARGET_URI}</code>
                <p>示例：</p>
                <ul>
                    <li>GET {HTTP_TARGET_URI}/your-endpoint</li>
                    <li>POST {HTTP_TARGET_URI}/your-endpoint</li>
                </ul>
            </div>

            <div class="endpoint">
                <h2>WebSocket Endpoint</h2>
                <p>WebSocket 连接会被转发到 Heygen WebSocket 服务器：</p>
                <code>{WS_TARGET_URI}</code>
                <p>本地WebSocket连接地址：</p>
                <code>ws://{PROXY_HOST}:{PROXY_PORT}/v1/ws</code>
            </div>

            <div class="endpoint">
                <h2>代理服务器信息</h2>
                <ul>
                    <li>服务器地址：<code>http://{PROXY_HOST}:{PROXY_PORT}</code></li>
                    <li>所有API请求都会保持原始路径转发</li>
                    <li>支持所有HTTP方法（GET, POST, PUT, DELETE等）</li>
                    <li>自动转发请求头和请求体</li>
                </ul>
            </div>
        </body>
    </html>
    """

@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def proxy_http(path):
    """处理所有HTTP请求"""
    target_url = f"{HTTP_TARGET_URI}/{path}"
    client_ip = request.remote_addr
    method = request.method
    
    logger.info(f"HTTP {method} request from {client_ip}: /{path} -> {target_url}")
    
    try:
        # 转发原始请求头
        headers = {key: value for key, value in request.headers.items()
                  if key.lower() not in ['host', 'content-length']}
        
        # 发送请求到目标服务器
        response = requests.request(
            method=method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            verify=True  # SSL验证
        )
        
        # 创建代理响应
        proxy_response = Response(
            response.content,
            response.status_code,
            dict(response.headers)
        )
        
        return proxy_response
        
    except Exception as e:
        logger.error(f"Error proxying HTTP request: {str(e)}")
        return Response(
            json.dumps({'error': str(e)}),
            status=500,
            content_type='application/json'
        )

@app.route('/')
def index():
    """重定向到帮助页面"""
    return help_page()

if __name__ == '__main__':
    logger.info(f"Starting proxy server on http://{PROXY_HOST}:{PROXY_PORT}")
    logger.info(f"HTTP requests will be forwarded to: {HTTP_TARGET_URI}")
    logger.info(f"WebSocket connections will be forwarded to: {WS_TARGET_URI}")
    logger.info(f"Visit http://{PROXY_HOST}:{PROXY_PORT}/help for documentation")
    
    server = pywsgi.WSGIServer(
        (PROXY_HOST, PROXY_PORT),
        app,
        handler_class=WebSocketHandler
    )
    server.serve_forever()
