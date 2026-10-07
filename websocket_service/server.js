require('dotenv').config();
const http = require('http');
const express = require('express');
const cors = require('cors');
const { Server } = require('socket.io');
const Redis = require('ioredis');

const PORT = parseInt(process.env.PORT, 10) || 6001;
const API_KEY = process.env.API_KEY || 'ota_ws_secret_key_2026';
const CORS_ORIGIN = process.env.CORS_ORIGIN || '*';
const REDIS_ENABLED = process.env.REDIS_ENABLED === 'true' || process.env.REDIS_ENABLED === '1';
const REDIS_HOST = process.env.REDIS_HOST || '127.0.0.1';
const REDIS_PORT = parseInt(process.env.REDIS_PORT, 10) || 6379;
const REDIS_PASSWORD = process.env.REDIS_PASSWORD || undefined;
const REDIS_CHANNEL = process.env.REDIS_CHANNEL || 'ota-broadcast';

// ── Express & HTTP Server Setup ──────────────────────────────────────────────
const app = express();
app.use(express.json());
app.use(cors({ origin: CORS_ORIGIN }));

const server = http.createServer(app);

// ── Socket.IO Setup ──────────────────────────────────────────────────────────
const io = new Server(server, {
    cors: {
        origin: CORS_ORIGIN === '*' ? '*' : CORS_ORIGIN.split(',').map(s => s.trim()),
        methods: ['GET', 'POST'],
        credentials: true
    },
    pingTimeout: 30000,
    pingInterval: 25000,
});

// ── State Tracking & Helper Functions ────────────────────────────────────────
let redisStatus = { connected: false, channel: REDIS_CHANNEL, error: null };

function getFormattedTimestamp() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function log(tag, message, payload = null) {
    const time = getFormattedTimestamp();
    if (payload !== null && payload !== undefined) {
        let payloadStr;
        try {
            payloadStr = typeof payload === 'object' ? JSON.stringify(payload) : String(payload);
            if (payloadStr.length > 500) {
                payloadStr = payloadStr.substring(0, 500) + '... (truncated)';
            }
        } catch (_) {
            payloadStr = '[Circular/Unserializable]';
        }
        console.log(`[${time}] [${tag}] ${message} | Payload: ${payloadStr}`);
    } else {
        console.log(`[${time}] [${tag}] ${message}`);
    }
}

function getActiveStats() {
    const sockets = io.sockets.sockets; // Map<SocketId, Socket>
    const totalSockets = sockets ? sockets.size : (io.engine ? io.engine.clientsCount : 0);
    const userIds = new Set();
    let guestCount = 0;

    if (sockets) {
        for (const [_, sock] of sockets) {
            if (sock.data && sock.data.userId) {
                userIds.add(sock.data.userId);
            } else {
                guestCount++;
            }
        }
    }

    return {
        totalSockets,
        uniqueUsersCount: userIds.size,
        activeUserIds: Array.from(userIds),
        guestCount
    };
}

function getStatsSummary() {
    const stats = getActiveStats();
    const userDetail = stats.activeUserIds.length > 0 
        ? ` [User IDs: ${stats.activeUserIds.join(', ')}]` 
        : '';
    return `Active Connections: ${stats.totalSockets} socket(s) | ${stats.uniqueUsersCount} user(s)${userDetail} | ${stats.guestCount} guest(s)`;
}

// ── Helper: Broadcast to specific room(s) or all ─────────────────────────────
function broadcastEvent(roomOrRooms, event, data) {
    if (!event) return { delivered: false, reason: 'Event name is required' };

    let targetRooms = [];
    if (Array.isArray(roomOrRooms)) {
        targetRooms = roomOrRooms.filter(Boolean);
    } else if (roomOrRooms) {
        targetRooms = [roomOrRooms];
    }

    if (targetRooms.length > 0) {
        targetRooms.forEach(room => {
            io.to(room).emit(event, data);
        });
        return { delivered: true, rooms: targetRooms };
    } else {
        // Broadcast to all connected sockets
        io.emit(event, data);
        return { delivered: true, rooms: ['*'] };
    }
}

// ── Socket.IO Client Connection Lifecycle ────────────────────────────────────
io.on('connection', (socket) => {
    const query = socket.handshake.query || {};
    const auth = socket.handshake.auth || {};
    const userId = query.userId || auth.userId || null;

    // Attach userId to socket metadata for live tracking
    socket.data.userId = userId;

    if (userId) {
        const userRoom = `user_${userId}`;
        socket.join(userRoom);
        log('Socket.IO', `🟢 Client connected: ${socket.id} (User: ${userId}, Room: [${userRoom}]) | ${getStatsSummary()}`);
    } else {
        log('Socket.IO', `🟢 Client connected: ${socket.id} (Guest/Unauthenticated) | ${getStatsSummary()}`);
    }

    // ── LOG EVERY MESSAGE / EVENT RECEIVED FROM THIS CLIENT ─────────────────
    socket.onAny((event, ...args) => {
        log('Socket.IO <- Client', `📩 Received event "${event}" from [${socket.id}] (User: ${socket.data.userId || 'guest'}) | ${getStatsSummary()}`, args.length === 1 ? args[0] : args);
    });

    // Allow clients to join custom topic rooms (flights, bookings, etc.)
    socket.on('join', (roomName) => {
        if (roomName && typeof roomName === 'string') {
            socket.join(roomName);
            log('Socket.IO', `🚪 Client ${socket.id} (User: ${socket.data.userId || 'guest'}) joined room [${roomName}]`);
            socket.emit('joined', { room: roomName, status: 'ok' });
        }
    });

    socket.on('leave', (roomName) => {
        if (roomName && typeof roomName === 'string') {
            socket.leave(roomName);
            log('Socket.IO', `🚪 Client ${socket.id} (User: ${socket.data.userId || 'guest'}) left room [${roomName}]`);
            socket.emit('left', { room: roomName, status: 'ok' });
        }
    });

    socket.on('disconnect', (reason) => {
        // Remove userId reference
        const leavingUserId = socket.data.userId;
        log('Socket.IO', `🔴 Client disconnected: ${socket.id} (User: ${leavingUserId || 'guest'}, Reason: ${reason}) | ${getStatsSummary()}`);
    });
});

// ── Redis Pub/Sub Subscriber ─────────────────────────────────────────────────
if (REDIS_ENABLED) {
    log('Redis', `Connecting to Redis at ${REDIS_HOST}:${REDIS_PORT}...`);
    const redisSubscriber = new Redis({
        host: REDIS_HOST,
        port: REDIS_PORT,
        password: REDIS_PASSWORD,
        retryStrategy(times) {
            return Math.min(times * 1000, 15000);
        },
    });

    redisSubscriber.on('ready', () => {
        redisStatus.connected = true;
        redisStatus.error = null;
        log('Redis', `Connected and ready at ${REDIS_HOST}:${REDIS_PORT}`);
    });

    redisSubscriber.psubscribe(`*${REDIS_CHANNEL}`, (err, count) => {
        if (err) {
            log('Redis', `❌ Subscription error: ${err.message}`);
            redisStatus.error = err.message;
        } else {
            log('Redis', `Subscribed to pattern [*${REDIS_CHANNEL}] (covers direct & prefixed channels)`);
        }
    });

    redisSubscriber.on('pmessage', (pattern, channel, message) => {
        try {
            const payload = JSON.parse(message);
            const { room, rooms, event = 'notification', data } = payload;
            const target = rooms || room;
            const res = broadcastEvent(target, event, data);
            
            // Log message received from Redis and forwarded to clients
            log('Redis <- PubSub', `📩 Received message on channel [${channel}] -> Broadcast event "${event}" to [${JSON.stringify(res.rooms)}] | ${getStatsSummary()}`, data);
        } catch (e) {
            log('Redis', `❌ Failed to parse message on channel [${channel}]: ${e.message}`, message);
        }
    });

    redisSubscriber.on('error', (err) => {
        redisStatus.connected = false;
        redisStatus.error = err.message;
        log('Redis', `⚠️ Warning: ${err.message}`);
    });
} else {
    log('Redis', `Redis Pub/Sub is disabled (REDIS_ENABLED=false). Using HTTP REST broadcast only.`);
}

// ── HTTP Endpoints ───────────────────────────────────────────────────────────

// Root info
app.get('/', (req, res) => {
    const stats = getActiveStats();
    res.json({
        service: 'OTA WebSocket Microservice',
        version: '1.0.0',
        activeClients: stats.totalSockets,
        uniqueUsers: stats.uniqueUsersCount,
        activeUserIds: stats.activeUserIds,
        guestClients: stats.guestCount,
        uptimeSeconds: Math.floor(process.uptime()),
        endpoints: {
            health: 'GET /health',
            broadcast: 'POST /api/broadcast'
        }
    });
});

// Health check
app.get('/health', (req, res) => {
    const stats = getActiveStats();
    res.json({
        status: 'healthy',
        service: 'ota-websocket-microservice',
        uptime: Math.floor(process.uptime()),
        connectedClients: stats.totalSockets,
        uniqueUsers: stats.uniqueUsersCount,
        activeUserIds: stats.activeUserIds,
        guestClients: stats.guestCount,
        redis: {
            enabled: REDIS_ENABLED,
            ...redisStatus
        },
        timestamp: new Date().toISOString()
    });
});

// REST Broadcast API (Used by Laravel and Python API)
app.post('/api/broadcast', (req, res) => {
    const providedKey = req.headers['x-api-key'] || req.query.api_key;

    if (!providedKey || providedKey !== API_KEY) {
        log('HTTP', `⛔ Unauthorized broadcast attempt from ${req.ip}`);
        return res.status(401).json({
            error: 'Unauthorized',
            message: 'Invalid or missing x-api-key header.'
        });
    }

    const { room, rooms, event = 'notification', data } = req.body;

    if (!data) {
        return res.status(422).json({
            error: 'Unprocessable Entity',
            message: 'Missing "data" payload in request body.'
        });
    }

    const target = rooms || room;
    const result = broadcastEvent(target, event, data);

    // Log the message received via HTTP REST
    log('HTTP <- Broadcast', `📩 Received HTTP broadcast | Event: "${event}" | Target: ${JSON.stringify(result.rooms)} | ${getStatsSummary()}`, data);

    return res.status(200).json({
        success: true,
        event: event,
        targetRooms: result.rooms,
        activeClients: io.engine ? io.engine.clientsCount : 0,
        timestamp: new Date().toISOString()
    });
});

// ── Periodic Heartbeat Logger (every 60s if clients connected) ───────────────
setInterval(() => {
    const stats = getActiveStats();
    if (stats.totalSockets > 0) {
        log('Heartbeat', `Current Status -> ${getStatsSummary()}`);
    }
}, 60000);

// ── Start Listening ──────────────────────────────────────────────────────────
server.listen(PORT, '0.0.0.0', () => {
    console.log(`=======================================================`);
    console.log(`  OTA Real-time WebSocket Microservice Started`);
    console.log(`  Listening on: http://0.0.0.0:${PORT}`);
    console.log(`  CORS Origin:  ${CORS_ORIGIN}`);
    console.log(`  API Key:      ${API_KEY ? '•••••••• (Configured)' : 'NONE'}`);
    console.log(`  Redis Sub:    ${REDIS_ENABLED ? `ENABLED (${REDIS_HOST}:${REDIS_PORT})` : 'DISABLED'}`);
    console.log(`=======================================================`);
});
