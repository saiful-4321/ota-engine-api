# OTA Real-time WebSocket Microservice

A high-performance, containerized WebSocket microservice built with **Node.js, Express, and Socket.IO**, with built-in **Redis Pub/Sub** and **REST API** support.

Designed to serve real-time notifications, live flight tracking, search status, and messaging across both **Laravel (OTA Backoffice)** and your **Python API services**.

---

## 🚀 Quick Start with Docker

### 1. Start the container
From the `websocket_service` directory (or workspace root):

```bash
docker compose up -d --build
```

### 2. Verify health
```bash
curl http://localhost:6001/health
```

Expected JSON response:
```json
{
  "status": "healthy",
  "service": "ota-websocket-microservice",
  "uptime": 12,
  "connectedClients": 0,
  "redis": {
    "enabled": true,
    "connected": true,
    "channel": "ota-broadcast"
  }
}
```

---

## 🛠 Local Development (Without Docker)

```bash
cd websocket_service
npm install
npm start
# or auto-reloading dev mode:
npm run dev
```

---

## 📡 Broadcasting from Python API (FastAPI / Flask / Django)

You have **two seamless ways** to broadcast from your Python services:

### Method A: Via REST API (Recommended & Universal)

```python
import requests

WEBSOCKET_URL = "http://localhost:6001/api/broadcast"
API_KEY = "ota_ws_secret_key_2026"

def broadcast_event(room: str, event: str, data: dict):
    """
    Broadcasts real-time event to a specific room or user.
    room examples:
      - "user_10"       (targeted to user ID 10)
      - "flight_EK202"  (targeted to everyone viewing flight EK202)
      - None            (broadcast to ALL connected clients)
    """
    payload = {
        "room": room,
        "event": event,
        "data": data
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY
    }
    try:
        response = requests.post(WEBSOCKET_URL, json=payload, headers=headers, timeout=2)
        return response.json()
    except Exception as e:
        print(f"WebSocket broadcast error: {e}")
        return None

# Example 1: Send a notification to user 10
broadcast_event(
    room="user_10",
    event="notification",
    data={
        "id": 123,
        "title": "Flight Booking Confirmed",
        "body": "PNR #XY789 has been ticketed successfully.",
        "url": "/flights/bookings/123",
        "type": "success"
    }
)

# Example 2: Stream live flight status update to a flight room
broadcast_event(
    room="flight_EK202",
    event="flight_status_updated",
    data={
        "flight_number": "EK202",
        "status": "Boarding",
        "gate": "B22",
        "updated_at": "14:30"
    }
)
```

### Method B: Via Redis Pub/Sub (Zero HTTP Overhead)

If your Python service already connects to Redis, you can publish directly without HTTP:

```python
import json
import redis

r = redis.Redis(host='localhost', port=6379, db=0)

# Publish message to Redis channel
r.publish('ota-broadcast', json.dumps({
    "room": "user_10",
    "event": "notification",
    "data": {
        "title": "Payment Received",
        "body": "Your invoice #4092 has been cleared."
    }
}))
```

The Node.js WebSocket microservice automatically catches this and delivers it to the user's browser in under 1 millisecond.

---

## 🐘 Broadcasting from Laravel (PHP)

In Laravel, the `BroadcastChannelService` dispatches notifications to the microservice:

```php
use Illuminate\Support\Facades\Http;

Http::withHeaders([
    'x-api-key' => config('services.websocket.key', 'ota_ws_secret_key_2026'),
])->post("http://127.0.0.1:6001/api/broadcast", [
    'room'  => "user_{$userId}",
    'event' => 'notification',
    'data'  => [
        'id'    => $notification->id,
        'title' => $notification->title,
        'body'  => $notification->body,
        'url'   => $notification->action_url,
    ],
]);
```

---

## 💻 Frontend Client (Browser / Socket.IO)

```html
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<script>
    // Connect to your WebSocket server with user identification
    const socket = io("http://localhost:6001", {
        query: { userId: "{{ auth()->id() }}" }
    });

    // Listen for private user notifications
    socket.on('notification', function(data) {
        console.log("Real-time notification received:", data);
        // 1. Update bell badge counter
        // 2. Prepend item to navbar dropdown
        // 3. Trigger toast or chime sound
    });

    // Optional: Join a flight room
    socket.emit('join', 'flight_EK202');
    socket.on('flight_status_updated', function(data) {
        console.log("Live flight update:", data);
    });
</script>
```

---

## ⚙ Environment Variables Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PORT` | `6001` | Port the server listens on |
| `API_KEY` | `ota_ws_secret_key_2026` | Secret key required in `x-api-key` header |
| `CORS_ORIGIN` | `*` | Allowed CORS origins (e.g. `http://ota-backoffice.test`) |
| `REDIS_ENABLED` | `true` | Enable Redis Pub/Sub subscription |
| `REDIS_HOST` | `127.0.0.1` / `host.docker.internal` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD`| `null` | Redis password (if any) |
| `REDIS_CHANNEL` | `ota-broadcast` | Redis channel to subscribe to |
