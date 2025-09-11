
"""
Flask Web Server for TTS Bot - Deployment Compatibility
Provides HTTP endpoints for health checks and status monitoring
"""

from flask import Flask, jsonify, request
import threading
import os
import sqlite3
from datetime import datetime
from database import SessionLocal, User, TTSRequest, BotStatus

app = Flask(__name__)

# Health check endpoint
@app.route('/')
def health_check():
    """Root endpoint for health checks"""
    return jsonify({
        "status": "online",
        "service": "TTS Telegram Bot",
        "version": "2.1.0",
        "timestamp": datetime.now().isoformat(),
        "message": "Bot is running successfully!"
    })

@app.route('/health')
def health():
    """Detailed health check endpoint"""
    try:
        # Check database connection
        db = SessionLocal()
        user_count = db.query(User).count()
        tts_requests = db.query(TTSRequest).count()
        
        # Check bot status
        bot_status = db.query(BotStatus).first()
        bot_active = bot_status.is_active if bot_status else True
        
        db.close()
        
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "bot_active": bot_active,
            "total_users": user_count,
            "total_tts_requests": tts_requests,
            "uptime": "running",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/stats')
def api_stats():
    """API endpoint for bot statistics"""
    try:
        db = SessionLocal()
        
        # Get basic stats
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active == True, User.is_banned == False).count()
        total_tts = db.query(TTSRequest).count()
        
        # Get today's activity
        today = datetime.utcnow().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_users = db.query(User).filter(User.last_active >= today_start).count()
        today_tts = db.query(TTSRequest).filter(TTSRequest.timestamp >= today_start).count()
        
        db.close()
        
        return jsonify({
            "bot_stats": {
                "total_users": total_users,
                "active_users": active_users,
                "total_tts_requests": total_tts,
                "today_active_users": today_users,
                "today_tts_requests": today_tts
            },
            "status": "operational",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/status')
def bot_status():
    """Bot operational status endpoint"""
    try:
        db = SessionLocal()
        bot_status = db.query(BotStatus).first()
        
        if bot_status:
            status_info = {
                "active": bot_status.is_active,
                "deactivated_reason": bot_status.deactivated_reason,
                "deactivated_until": bot_status.deactivated_until.isoformat() if bot_status.deactivated_until else None,
                "last_updated": bot_status.updated_at.isoformat() if bot_status.updated_at else None
            }
        else:
            status_info = {
                "active": True,
                "deactivated_reason": None,
                "deactivated_until": None,
                "last_updated": None
            }
        
        db.close()
        
        return jsonify({
            "bot_status": status_info,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook endpoint for external integrations"""
    return jsonify({
        "received": True,
        "timestamp": datetime.now().isoformat(),
        "message": "Webhook received successfully"
    })

def start_web_server():
    """Start Flask web server in a separate thread"""
    port = int(os.getenv('PORT', 5000))
    host = '0.0.0.0'
    
    print(f"🌐 Starting web server on {host}:{port}")
    print(f"🔗 Health check available at: http://{host}:{port}/health")
    print(f"📊 API stats available at: http://{host}:{port}/api/stats")
    
    app.run(host=host, port=port, debug=False, use_reloader=False)

def run_web_server_in_background():
    """Run web server in background thread"""
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    print("✅ Web server started in background thread")
    return web_thread

if __name__ == "__main__":
    start_web_server()
