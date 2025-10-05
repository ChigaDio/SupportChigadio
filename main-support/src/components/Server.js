// server.js
const WebSocket = require('ws');
const dgram = require('dgram');
const server = dgram.createSocket('udp4');
const wss = new WebSocket.Server({ port: 41234 });

server.on('error', (err) => {
  console.error(`UDP server error: ${err.stack}`);
  server.close();
});

server.on('message', (msg, rinfo) => {
  const data = JSON.parse(msg.toString());
  wss.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(JSON.stringify(data));
    }
  });
});

server.on('listening', () => {
  const address = server.address();
  console.log(`UDP server listening on ${address.address}:${address.port}`);
});

server.bind(41234);