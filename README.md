
# 🎤 TTS Telegram Bot

An advanced **Text-to-Speech Telegram Bot** with comprehensive credit system, multi-language support, and powerful administrative features.

## ✨ Features

### 🎵 Text-to-Speech Capabilities
- **10+ Voice Options**: Multiple male and female voices
- **Multi-Language Support**: Hindi, English, Spanish, French, German
- **High-Quality Audio**: Microsoft Edge TTS integration
- **Real-time Processing**: Fast audio generation and delivery

### 💰 Credit System
- **Dynamic Credit Management**: Earn and spend credits for TTS usage
- **Multiple Earning Methods**: Referrals, free credit links, purchases
- **Payment Integration**: QR code-based payment processing
- **Transaction History**: Detailed tracking and CSV exports

### 👥 User Management
- **User Profiles**: Comprehensive user statistics and management
- **Referral System**: Reward users for bringing friends
- **Access Control**: Ban/unban functionality with reasons
- **Activity Tracking**: Last active timestamps and usage patterns

### 🛠️ Administrative Features
- **Owner Panel**: Complete bot management interface
- **Broadcast Messages**: Send messages to all users with placeholders
- **Settings Management**: Configurable credit rates and system parameters
- **Database Backups**: Automated backups every 10 minutes
- **Statistics Dashboard**: Real-time bot usage and user analytics

### 🌐 Web Dashboard
- **Real-time Monitoring**: System resource usage and bot statistics
- **Health Checks**: API endpoints for deployment monitoring
- **User Analytics**: Comprehensive usage reports and trends

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- Optional: PostgreSQL database for production

### Installation

1. **Clone or download the project files**

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   Create a `.env` file in the root directory:
   ```env
   BOT_TOKEN=your_telegram_bot_token
   API_ID=your_telegram_api_id
   API_HASH=your_telegram_api_hash
   OWNER_ID=your_telegram_user_id
   CHANNEL_ID=your_notification_channel_id  # Optional
   DATABASE_URL=sqlite:///./bot.db  # or PostgreSQL URL for production
   BOT_USERNAME=your_bot_username
   ```

4. **Run the bot**:
   ```bash
   python main.py
   ```

## 🗂️ Project Structure

```
├── main.py                 # Main bot application
├── database.py            # Database models and configuration
├── tts_service.py         # Text-to-speech service implementation
├── keyboards.py           # Telegram inline keyboards
├── web_server.py          # Flask web dashboard
├── credit_history.py      # Credit transaction tracking
├── transaction_history.py # Transaction export and management
├── referral_system.py     # User referral functionality
├── message_deletion.py    # Automated message cleanup
├── free_credit.py         # Free credit link generation
├── migrate_db.py          # Database migration utilities
├── templates/             # HTML templates for web dashboard
│   ├── base.html
│   └── dashboard.html
└── temp_files/           # Temporary file storage
```

## 📊 Database Schema

### Core Tables
- **users**: User profiles and credit balances
- **tts_requests**: TTS usage history
- **credit_transactions**: Credit earning/spending records
- **payment_requests**: Payment processing records
- **referral_system**: User referral tracking
- **bot_settings**: Configurable system parameters

### Supported Databases
- **SQLite**: Default for development and small deployments
- **PostgreSQL**: Recommended for production environments

## 🔧 Configuration

### Bot Settings (Configurable via Owner Panel)
- **Welcome Credits**: Credits given to new users (default: 10)
- **TTS Charge**: Credits per word for TTS (default: 0.05)
- **Payment Rate**: Credits per rupee (default: 10)
- **Link Timeout**: Free credit link validity (default: 10 minutes)

### Environment Variables
| Variable | Description | Required |
|----------|-------------|----------|
| `BOT_TOKEN` | Telegram bot token from BotFather | Yes |
| `API_ID` | Telegram API ID from my.telegram.org | Yes |
| `API_HASH` | Telegram API hash from my.telegram.org | Yes |
| `OWNER_ID` | Telegram user ID of the bot owner | Yes |
| `CHANNEL_ID` | Channel for notifications (optional) | No |
| `DATABASE_URL` | Database connection string | No |
| `BOT_USERNAME` | Bot username for referral links | No |

## 🎮 Usage

### For Users
1. **Start the bot**: Send `/start` to begin
2. **Select TTS**: Choose voice type and enter text
3. **Earn Credits**: Use referral system or buy credits
4. **Track Usage**: View transaction history and profile stats

### For Owners
1. **Access Owner Panel**: Owners get special administrative interface
2. **Manage Users**: Ban, unban, give credits, view user info
3. **Configure Settings**: Adjust credit rates, payment settings
4. **Monitor System**: View comprehensive bot statistics
5. **Backup Data**: Automated database backups to channel

## 🌐 Web Dashboard

Access the web dashboard at `http://localhost:5000` (or your deployment URL):

- **System Monitoring**: CPU, memory, disk usage
- **Bot Statistics**: User count, TTS requests, revenue
- **Health Checks**: API endpoints for monitoring services

### API Endpoints
- `GET /` - Main dashboard
- `GET /health` - Health check with database status
- `GET /api/status` - Simple status check
- `GET /api/stats` - Bot statistics (JSON)

## 💳 Payment System

### QR Code Setup
1. Access Owner Panel → Settings → QR Code Settings
2. Upload QR code image or provide URL
3. Set UPI ID and payment name
4. Users can now buy credits via QR payments

### Payment Processing
- Users request credits and provide transaction ID
- Owner receives notification with verification options
- Manual verification and credit addition
- Automatic user notification on confirmation

## 🔄 Backup & Restore

### Automated Backups
- **Frequency**: Every 10 minutes
- **Location**: Configured notification channel
- **Content**: Complete database exports (both main and credit history)
- **Format**: SQL dumps (PostgreSQL) or SQLite files

### Manual Backup Restore
1. Access Owner Panel → Settings → Database Backup
2. Upload main database file (.sql or .db)
3. Upload credit history file (.db)
4. System automatically processes and restores data

## 🚀 Deployment on Replit

This bot is optimized for Replit deployment:

1. **Import Project**: Create new Repl and upload files
2. **Install Dependencies**: Run `pip install -r requirements.txt`
3. **Configure Secrets**: Set environment variables in Replit Secrets
4. **Enable Always On**: For continuous operation (Hacker plan)
5. **Monitor via Dashboard**: Access web interface at your Repl URL

### Replit-Specific Features
- **Port 5000**: Configured for Replit's port forwarding
- **Keep Alive**: Web server prevents sleeping
- **Environment Integration**: Automatic secrets loading
- **Database Persistence**: SQLite files preserved between runs

## 📈 Monitoring & Analytics

### Real-time Statistics
- **User Metrics**: Total users, active users, new registrations
- **Usage Analytics**: TTS requests, credit transactions, revenue
- **System Health**: Database connections, memory usage, uptime

### Transaction Exports
- **CSV Downloads**: Complete transaction history
- **Date Range Filters**: Custom period exports
- **User-specific**: Individual transaction tracking
- **Payment Tracking**: Revenue and payment request monitoring

## 🔧 Development

### Adding New Features
1. **Voice Types**: Extend `tts_service.py` with new voice options
2. **Payment Methods**: Integrate additional payment gateways
3. **Languages**: Add new TTS language support
4. **Admin Features**: Extend owner panel functionality

### Database Migrations
- Use `migrate_db.py` for schema updates
- Test migrations on SQLite before PostgreSQL deployment
- Backup data before running migrations

## 🛡️ Security Features

- **Owner-only Access**: Administrative functions restricted to owner
- **User State Management**: Secure session handling
- **Database Security**: Parameterized queries prevent injection
- **Environment Variables**: Sensitive data stored securely
- **Rate Limiting**: Built-in protection against abuse

## 📞 Support

### For Users
- Use the "Contact Support" button in the bot
- Messages are automatically forwarded to the owner
- Response time: Usually 2-4 hours

### For Developers
- Check console logs for error messages
- Use health check endpoints for monitoring
- Review database logs for transaction issues

## 📄 License

This project is provided as-is for educational and personal use. Please ensure compliance with Telegram's Bot API terms of service and local regulations when deploying.

## 🙏 Credits

- **Text-to-Speech**: Microsoft Edge TTS
- **Telegram Framework**: Pyrogram
- **Database**: SQLAlchemy ORM
- **Web Framework**: Flask
- **UI Components**: Custom Telegram inline keyboards

---

**Made with ❤️ for the Telegram Bot community**

*For questions, suggestions, or contributions, please contact the bot owner or check the project documentation.*
