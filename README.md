# 🎤 TTS Telegram Bot

**Advanced Multi-Language Text-to-Speech Bot with Credit System**

A sophisticated Telegram bot that converts text messages to high-quality audio using Microsoft Edge TTS, featuring a complete credit economy, referral system, and multi-language support.

---

## 🌟 **Key Features**

### 🎯 **Multi-Language TTS Support**
- **10 Unique Neural Voices** (5 Male + 5 Female)
- **English, Hindi (Devanagari), Roman Hindi** language detection
- **Microsoft Edge TTS** for professional voice quality
- **Each voice is truly unique** - no voice switching

### 💰 **Credit Economy System**
- **10 Free Credits** for new users  
- **Earn Credits** through referral links and free activities
- **Purchase Credits** via integrated payment system
- **Complete Transaction History** with detailed tracking

### 🔄 **Advanced Referral Program**
- **Simple referral codes** (`ref_123456`)
- **Automatic credit distribution** on successful referrals
- **Statistics tracking** for engagement monitoring

### 🛡️ **Smart Message Management**
- **Audio files preserved permanently** 📁
- **Text messages auto-deleted** for chat cleanliness
- **Context-aware deletion timings**
- **Privacy-focused sensitive content cleanup**

---

## 🚀 **Quick Start**

### **Requirements**
- Python 3.11+
- Telegram Bot Token
- Microsoft Edge TTS (included)

### **Installation**

```bash
# Clone repository
git clone <your-repo-url>
cd tts-telegram-bot

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Add your BOT_TOKEN, API_ID, API_HASH
```

### **Environment Variables**

Create `.env` file:
```env
BOT_TOKEN=your_telegram_bot_token
API_ID=your_api_id  
API_HASH=your_api_hash
OWNER_ID=your_telegram_user_id
DATABASE_URL=sqlite:///bot.db  # or PostgreSQL URL for production
```

### **Run Bot**
```bash
python main.py
```

---

## 🎙️ **Voice Gallery**

### **👨 Male Voices**
- **Deep Tone** - `en-IN-PrabhatNeural`
- **Warm Tone** - `hi-IN-RehaanNeural`  
- **Calm Voice** - `en-IN-AaravNeural`
- **Gentle Speaker** - `hi-IN-MadhurNeural`
- **Smooth Narrator** - `en-IN-AnanyaNeural`

### **👩 Female Voices**  
- **Sweet Voice** - `en-IN-NeerjaNeural`
- **Melodic Angel** - `hi-IN-KavyaNeural`
- **Crystal Clear** - `en-IN-PriyaNeural`
- **Honey Sweet** - `hi-IN-SwaraNeural`
- **Elegant Lady** - `en-IN-ShaliniNeural`

---

## 💡 **Usage Examples**

### **Basic TTS**
```
User: "Hello bhaiya, kaise ho?"
Bot: 🎤 [Audio file with chosen voice]
```

### **Language Auto-Detection**
- **English:** "How are you today?"
- **Hindi:** "आप कैसे हैं?"  
- **Roman Hindi:** "Aaj kaisa din tha?"

### **Credit Management**
- Check balance: `/credits`
- View history: `/history`
- Get referral link: `/referral`

---

## 🏗️ **Architecture**

### **Core Components**
- **`main.py`** - Bot client and handlers
- **`tts_service.py`** - Voice generation engine  
- **`message_deletion.py`** - Smart cleanup system
- **`credit_history.py`** - Transaction tracking
- **`keyboards.py`** - Interactive UI components

### **Database Design**
- **Dual Database System**
  - Main DB: User data, settings, basic transactions
  - Credit History DB: Detailed transaction logs
- **SQLAlchemy ORM** with SQLite/PostgreSQL support

### **Message Management Strategy**
- ✅ **Audio Files: PERMANENT** (never deleted)
- ⏰ **Text Messages: Auto-deleted** with smart timing
- 🔒 **Sensitive Content: Quick cleanup** (8 seconds)
- 📋 **Menu/Info: Medium timing** (45-60 seconds)

---

## 🔧 **Advanced Configuration**

### **Production Deployment**
```bash
# Use PostgreSQL for production
DATABASE_URL=postgresql://user:password@host:port/database

# Enable channel backup
CHANNEL_ID=-100123456789  # Your backup channel

# Configure credit settings
WELCOME_CREDITS=10
REFERRAL_BONUS=5
```

### **Custom Voice Settings**
Modify `VOICE_SETTINGS` in `tts_service.py` to add more voices or adjust parameters.

---

## 🛠️ **Development**

### **Project Structure**
```
tts-telegram-bot/
├── main.py                 # Bot entry point
├── tts_service.py         # TTS engine
├── message_deletion.py    # Cleanup service  
├── database.py           # Main database models
├── credit_history.py     # Transaction database
├── keyboards.py          # UI components
├── requirements.txt      # Dependencies
└── README.md            # Documentation
```

### **Adding New Features**
1. Create service classes for complex features
2. Use proper message types for deletion timing
3. Follow the existing database pattern
4. Add comprehensive logging

---

## 📊 **Performance & Scale**

### **Optimization Features**
- **Connection retry logic** with exponential backoff
- **Threaded TTS processing** for concurrent requests
- **Automatic message cleanup** to prevent chat bloat
- **Database indexing** for fast credit lookups

### **Scalability**
- Supports both **SQLite** (single instance) and **PostgreSQL** (multi-instance)
- **Modular architecture** for easy feature additions
- **Efficient memory management** with temporary file cleanup

---

## 🤝 **Support**

### **Troubleshooting**
- Check bot permissions in your Telegram channel
- Verify environment variables are set correctly
- Ensure internet connectivity for Edge TTS API
- Review logs in `/logs` directory

### **Common Issues**
- **Bot not responding:** Check BOT_TOKEN
- **TTS failed:** Verify internet connection
- **Credits not updating:** Check database permissions
- **Messages not deleting:** Verify bot admin rights

---

## 📈 **Future Roadmap**

- [ ] More voice languages (Tamil, Bengali, etc.)
- [ ] Custom voice speed/pitch controls
- [ ] Bulk TTS processing
- [ ] Voice mixing and effects
- [ ] Advanced analytics dashboard
- [ ] API endpoints for integration

---

## 💻 **Tech Stack**

- **Framework:** Pyrogram (Telegram MTProto)
- **TTS Engine:** Microsoft Edge TTS
- **Database:** SQLAlchemy + SQLite/PostgreSQL  
- **Language:** Python 3.11+
- **Architecture:** Async/Await with service layers

---

**Made with ❤️ for the Telegram community**

*Transform your text into perfect audio with professional-grade voices!* 🎯