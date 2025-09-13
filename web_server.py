
"""
Flask Web Server for TTS Bot - Deployment Compatibility
Provides HTTP endpoints for health checks and status monitoring
"""

from flask import Flask, jsonify, request, render_template
import threading
import os
import sqlite3
from datetime import datetime, timedelta
from database import SessionLocal, User, TTSRequest, BotStatus
import psutil
import sys

app = Flask(__name__)

# Dashboard route
@app.route('/')
def dashboard():
    """Enhanced main dashboard page with comprehensive bot details"""
    try:
        # Get database connections
        db = SessionLocal()
        
        # Import credit history for comprehensive stats
        from credit_history import get_credit_history_db
        credit_db = get_credit_history_db()
        
        # Basic user statistics
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active == True, User.is_banned == False).count()
        banned_users = db.query(User).filter(User.is_banned == True).count()
        total_tts = db.query(TTSRequest).count()
        
        # Advanced time-based statistics
        today = datetime.utcnow().date()
        today_start = datetime.combine(today, datetime.min.time())
        yesterday_start = today_start - timedelta(days=1)
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)
        
        # Daily statistics
        today_users = db.query(User).filter(User.last_active >= today_start).count()
        today_tts = db.query(TTSRequest).filter(TTSRequest.timestamp >= today_start).count()
        yesterday_users = db.query(User).filter(User.last_active >= yesterday_start, User.last_active < today_start).count()
        yesterday_tts = db.query(TTSRequest).filter(TTSRequest.timestamp >= yesterday_start, TTSRequest.timestamp < today_start).count()
        
        # Weekly & Monthly statistics
        week_users = db.query(User).filter(User.last_active >= week_start).count()
        week_tts = db.query(TTSRequest).filter(TTSRequest.timestamp >= week_start).count()
        month_users = db.query(User).filter(User.last_active >= month_start).count()
        month_tts = db.query(TTSRequest).filter(TTSRequest.timestamp >= month_start).count()
        
        # Calculate growth rates
        user_growth = ((today_users - yesterday_users) / yesterday_users * 100) if yesterday_users > 0 else 0
        tts_growth = ((today_tts - yesterday_tts) / yesterday_tts * 100) if yesterday_tts > 0 else 0
        
        # Credit and transaction statistics
        try:
            credit_cursor = credit_db.cursor()
            credit_cursor.execute("SELECT COUNT(*) FROM credit_transactions")
            total_transactions = credit_cursor.fetchone()[0]
            
            credit_cursor.execute("SELECT SUM(amount) FROM credit_transactions WHERE amount > 0")
            total_credits_earned = credit_cursor.fetchone()[0] or 0
            
            credit_cursor.execute("SELECT SUM(ABS(amount)) FROM credit_transactions WHERE amount < 0")
            total_credits_spent = credit_cursor.fetchone()[0] or 0
            
            credit_cursor.execute("SELECT COUNT(DISTINCT user_id) FROM credit_transactions")
            users_with_transactions = credit_cursor.fetchone()[0]
            
            credit_db.close()
        except:
            total_transactions = 0
            total_credits_earned = 0
            total_credits_spent = 0
            users_with_transactions = 0
        
        # Calculate engagement metrics
        engagement_rate = (active_users / total_users * 100) if total_users > 0 else 0
        transaction_rate = (users_with_transactions / total_users * 100) if total_users > 0 else 0
        avg_tts_per_user = (total_tts / total_users) if total_users > 0 else 0
        
        # System information
        import psutil
        import sys
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Bot status
        bot_status = db.query(BotStatus).first()
        bot_active = bot_status.is_active if bot_status else True
        
        # Voice statistics (mock data for TTS voices)
        voice_stats = {
            "english_voices": 5,
            "hindi_voices": 5,
            "total_languages": 2,
            "neural_voices": 10,
            "premium_voices": 8
        }
        
        db.close()
        
        stats = {
            # Basic stats
            "total_users": total_users,
            "active_users": active_users,
            "banned_users": banned_users,
            "total_tts": total_tts,
            
            # Time-based stats
            "today_users": today_users,
            "today_tts": today_tts,
            "yesterday_users": yesterday_users,
            "yesterday_tts": yesterday_tts,
            "week_users": week_users,
            "week_tts": week_tts,
            "month_users": month_users,
            "month_tts": month_tts,
            
            # Growth rates
            "user_growth": round(user_growth, 1),
            "tts_growth": round(tts_growth, 1),
            
            # Credit system
            "total_transactions": total_transactions,
            "total_credits_earned": round(total_credits_earned, 2),
            "total_credits_spent": round(total_credits_spent, 2),
            "users_with_transactions": users_with_transactions,
            
            # Engagement metrics
            "engagement_rate": round(engagement_rate, 1),
            "transaction_rate": round(transaction_rate, 1),
            "avg_tts_per_user": round(avg_tts_per_user, 2),
            
            # System information
            "cpu_percent": round(cpu_percent, 1),
            "memory_percent": round(memory.percent, 1),
            "memory_used_gb": round(memory.used / (1024**3), 2),
            "memory_total_gb": round(memory.total / (1024**3), 2),
            "disk_percent": round(disk.percent, 1),
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_total_gb": round(disk.total / (1024**3), 2),
            
            # Bot information
            "bot_active": bot_active,
            "bot_version": "2.1.0",
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "voice_stats": voice_stats,
            
            # Timestamp
            "timestamp": datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            "iso_timestamp": datetime.now().isoformat()
        }
        
        return render_template('dashboard.html', stats=stats)
    except Exception as e:
        return render_template('dashboard.html', stats=None, error=str(e))

# Health check endpoint (moved to /api/health)
@app.route('/api/health')
def health_check():
    """API endpoint for health checks"""
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
