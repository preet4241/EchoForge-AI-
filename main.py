import os
import asyncio
import sqlite3
import shutil
import random
import string
import subprocess
import urllib.parse
from datetime import datetime, timedelta
from pyrogram.client import Client
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.orm import Session
from database import create_tables, get_db, User, TTSRequest, LinkShortner, BotSettings, BotStatus, BotRating, CreditTransaction, ReferralSystem, SessionLocal, get_setting, update_setting, QRCodeSettings, PaymentRequest, MessageTracking # Import QRCodeSettings and MessageTracking
from credit_history import create_credit_history_tables, log_credit_history, get_user_credit_history, get_user_credit_summary, get_credit_history_db
from transaction_history import transaction_manager
from keyboards import (
    get_owner_panel, get_user_panel, get_about_keyboard,
    get_back_to_owner, get_back_to_user, get_tts_languages,
    get_users_panel, get_shortner_panel, get_shortner_add_panel, get_shortner_info_panel,
    get_voice_selection, get_voice_selection_owner,
    get_settings_panel, get_credits_settings_panel, get_settings_confirmation_panel,
    get_rating_panel, get_deactivate_confirmation_panel, get_user_credit_panel,
    get_support_contact_panel, get_payment_cancel_panel, get_payment_verification_panel, get_payment_settings_panel, get_qr_management_panel,
    get_referral_panel, get_referral_share_panel, get_owner_referral_panel, get_simple_referral_panel, get_free_credit_referral_panel,
    get_user_about_keyboard, get_owner_details_keyboard, get_referral_settings_panel,
    get_transaction_history_panel, get_custom_date_panel, get_my_transaction_panel,
    get_support_confirmation_keyboard, get_contact_support_keyboard, get_help_section_keyboard,
    get_credit_handler_panel, get_buy_credit_management_panel, get_buy_credit_setup_panel
)
from tts_service import TTSService
from referral_system import get_user_referral_link, get_user_referral_stats, process_referral
from message_deletion import (
    initialize_deletion_service, get_deletion_service,
    track_sent_message, track_message_for_deletion, delete_messages_by_context,
    MessageType, get_context_from_callback, cleanup_conversation
)

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', '')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Channel for admin data and payment requests

# Initialize bot and services
app = Client("tts_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
tts_service = TTSService()

# User states for TTS
user_states = {}

# Connected channel for notifications (runtime variable)
connected_channel_id = None

# Transaction ID Generator Function
def generate_transaction_id():
    """Generate a unique 16-digit transaction ID"""
    # Format: 4-digit year + 4-digit random + 4-digit timestamp + 4-digit random
    year = datetime.now().strftime('%Y')
    timestamp_part = datetime.now().strftime('%m%d')
    random_part1 = ''.join(random.choices(string.digits, k=4))
    random_part2 = ''.join(random.choices(string.digits, k=4))
    transaction_id = f"{year}{random_part1}{timestamp_part}{random_part2}"
    return transaction_id

def secure_pg_dump(database_url: str, output_file: str) -> tuple:
    """
    Securely execute pg_dump without exposing credentials in process list.
    
    Args:
        database_url: PostgreSQL connection URL
        output_file: Path to output backup file
    
    Returns:
        tuple: (success: bool, error_message: str)
    """
    try:
        # Parse DATABASE_URL to extract connection components
        parsed_url = urllib.parse.urlparse(database_url)
        
        # Extract connection parameters
        host = parsed_url.hostname
        port = parsed_url.port or 5432
        database = parsed_url.path.lstrip('/')
        username = parsed_url.username
        password = parsed_url.password
        
        if not all([host, database, username]):
            return False, "Missing required database connection parameters"
        
        # Set up environment with password (secure way)
        env = os.environ.copy()
        if password:
            env['PGPASSWORD'] = password
        
        # Build pg_dump command without exposing credentials
        pg_dump_cmd = [
            'pg_dump',
            '-h', host,
            '-p', str(port),
            '-U', username,
            '-d', database,
            '--no-password',  # Use PGPASSWORD environment variable
            '-f', output_file,
            '--verbose'
        ]
        
        # Execute pg_dump securely
        print(f"🔒 Executing secure pg_dump to {output_file}")
        result = subprocess.run(
            pg_dump_cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            print(f"✅ Secure pg_dump completed successfully")
            return True, ""
        else:
            error_msg = f"pg_dump failed with exit code {result.returncode}"
            if result.stderr:
                error_msg += f"\nStderr: {result.stderr.strip()}"
            if result.stdout:
                print(f"pg_dump stdout: {result.stdout.strip()}")
            return False, error_msg
            
    except subprocess.TimeoutExpired:
        return False, "pg_dump timed out after 5 minutes"
    except FileNotFoundError:
        return False, "pg_dump command not found. Please install PostgreSQL client tools."
    except Exception as e:
        return False, f"Error executing pg_dump: {str(e)}"

# Database backup function
async def create_and_send_db_backup():
    """Create database backup and send to channel every 10 minutes - Both databases"""
    try:
        # Use connected channel instead of environment variable
        target_channel = connected_channel_id or CHANNEL_ID
        if not target_channel:
            print("⚠️ No channel connected for backup, skipping database backup")
            return

        # Create backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        backup_files = []
        backup_info = []

        # Get DATABASE_URL to determine database type
        database_url = os.getenv('DATABASE_URL', 'sqlite:///./bot.db')
        print(f"🔍 Database URL detected: {database_url[:50]}...")
        
        # Handle PostgreSQL main database backup
        if database_url.startswith('postgresql://') or database_url.startswith('postgres://'):
            print("🐘 PostgreSQL database detected, using secure pg_dump for backup")
            
            main_backup_name = f"main_bot_backup_{timestamp}.sql"
            try:
                # Use secure pg_dump function to prevent credential exposure
                success, error_msg = secure_pg_dump(database_url, main_backup_name)
                
                if success and os.path.exists(main_backup_name):
                    file_size = os.path.getsize(main_backup_name)
                    if file_size > 0:
                        backup_files.append(main_backup_name)
                        size_kb = file_size / 1024
                        backup_info.append(f"📊 **Main Database (PostgreSQL):** {size_kb:.1f} KB")
                        print(f"✅ Secure PostgreSQL backup created successfully: {main_backup_name}")
                    else:
                        backup_info.append(f"❌ **Main Database:** Backup file empty")
                        print(f"❌ PostgreSQL backup file is empty: {main_backup_name}")
                else:
                    backup_info.append(f"❌ **Main Database:** {error_msg}")
                    print(f"❌ Secure pg_dump failed: {error_msg}")
                    
            except Exception as pg_error:
                print(f"❌ Error creating secure PostgreSQL backup: {pg_error}")
                backup_info.append(f"❌ **Main Database:** PostgreSQL backup failed - {str(pg_error)}")
        
        else:
            # Handle SQLite main database backup (fallback)
            print("🗃️ SQLite database detected for main DB")
            sqlite_file = 'bot.db'
            main_backup_name = f"main_bot_backup_{timestamp}.db"
            
            try:
                if os.path.exists(sqlite_file) and os.path.getsize(sqlite_file) > 0:
                    shutil.copy(sqlite_file, main_backup_name)
                    backup_files.append(main_backup_name)
                    file_size = os.path.getsize(sqlite_file)
                    size_kb = file_size / 1024
                    backup_info.append(f"📊 **Main Database (SQLite):** {size_kb:.1f} KB")
                    print(f"✅ SQLite backup created: {main_backup_name}")
                else:
                    backup_info.append(f"❌ **Main Database:** SQLite file not found or empty")
                    print(f"⚠️ SQLite file {sqlite_file} not found or empty")
            except Exception as sqlite_error:
                print(f"❌ Error backing up SQLite main database: {sqlite_error}")
                backup_info.append(f"❌ **Main Database:** SQLite backup failed")

        # Handle credit history database backup (always SQLite)
        credit_history_file = 'credit_history.db'
        credit_backup_name = f"credit_history_backup_{timestamp}.db"
        
        try:
            if os.path.exists(credit_history_file):
                file_size = os.path.getsize(credit_history_file)
                if file_size > 0:
                    shutil.copy(credit_history_file, credit_backup_name)
                    backup_files.append(credit_backup_name)
                    size_kb = file_size / 1024
                    backup_info.append(f"📊 **Credit History:** {size_kb:.1f} KB")
                    print(f"✅ Credit history backup created: {credit_backup_name}")
                else:
                    backup_info.append(f"❌ **Credit History:** File is empty")
                    print(f"⚠️ Credit history file is empty")
            else:
                backup_info.append(f"❌ **Credit History:** File not found")
                print(f"⚠️ Credit history file not found")
        except Exception as credit_error:
            print(f"❌ Error backing up credit history: {credit_error}")
            backup_info.append(f"❌ **Credit History:** Backup failed")

        if not backup_files:
            print("❌ No database files found for backup")
            return

        # Send to channel
        try:
            # Better channel ID validation and conversion (secure type handling)
            target_channel_str = str(target_channel) if target_channel is not None else ""
            if target_channel_str.startswith('-100'):
                target_id = int(target_channel_str)
            elif target_channel_str.startswith('-'):
                target_id = int(target_channel_str)
            elif target_channel_str.startswith('@'):
                target_id = target_channel_str
            else:
                target_id = f"@{target_channel_str}"
            
            # Create comprehensive backup message
            backup_details = "\n".join(backup_info)
            backup_message = (
                f"🗄️ **Complete Database Backup** 🗄️\n\n"
                f"📅 **Date:** {datetime.now().strftime('%d/%m/%Y')}\n"
                f"⏰ **Time:** {datetime.now().strftime('%H:%M:%S')}\n"
                f"📊 **Auto-backup:** Every 10 minutes\n\n"
                f"📋 **Backup Contents:**\n"
                f"{backup_details}\n\n"
                f"💾 **Total Files:** {len(backup_files)}\n"
                f"🔒 **Security:** Keep these backups secure!\n"
                f"🚀 **Bot:** Running smoothly"
            )

            # Send each backup file with detailed caption
            for i, backup_file in enumerate(backup_files):
                try:
                    # Determine database type from filename
                    if 'main_bot_backup' in backup_file:
                        if backup_file.endswith('.sql'):
                            db_name = "Main Database (PostgreSQL)"
                        else:
                            db_name = "Main Database (SQLite)"
                    elif 'credit_history_backup' in backup_file:
                        db_name = "Credit History"
                    else:
                        db_name = f"Database {i+1}"
                    
                    await app.send_document(
                        target_id,
                        backup_file,
                        caption=f"📂 **{db_name} Backup**\n\n{backup_message}" if i == 0 else f"📂 **{db_name} Backup**\n\n📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
                    )
                    print(f"✅ {db_name} backup sent to channel successfully!")
                except Exception as file_send_error:
                    print(f"❌ Error sending {backup_file} backup: {file_send_error}")

        except Exception as send_error:
            print(f"❌ Error sending backup to channel: {send_error}")
            print(f"💡 Channel troubleshooting:")
            print(f"   - Check if bot is added to channel")
            print(f"   - Check if bot has admin rights in channel")
            print(f"   - Verify CHANNEL_ID: {target_channel}")
            print(f"   - Target ID used: {target_id}")
            print(f"   - Error type: {type(send_error).__name__}")
            print(f"   - Full error details: {str(send_error)}")
            
            # Try to send error notification to owner as fallback
            try:
                if OWNER_ID and OWNER_ID != 0:
                    await app.send_message(
                        OWNER_ID,
                        f"❌ **Database Backup Failed**\n\n"
                        f"🔧 Channel: `{target_channel}`\n"
                        f"❌ Error: `{str(send_error)[:200]}`\n\n"
                        f"Kripaya channel connection check kare!"
                    )
            except Exception as owner_notify_error:
                print(f"❌ Failed to notify owner about backup error: {owner_notify_error}")

        # Clean up backup files
        for backup_file in backup_files:
            try:
                os.remove(backup_file)
            except Exception as cleanup_error:
                print(f"⚠️ Could not remove backup file {backup_file}: {cleanup_error}")

    except Exception as e:
        print(f"❌ Database backup error: {e}")

# Background task for database backups
async def database_backup_scheduler():
    """Background task to send database backups every 10 minutes"""
    while True:
        await asyncio.sleep(600)  # 10 minutes = 600 seconds
        await create_and_send_db_backup()

class UserState:
    NONE = 0
    WAITING_TTS_TEXT = 1
    WAITING_BROADCAST_TEXT = 2
    WAITING_GIVE_CREDIT_USER_ID = 3
    WAITING_GIVE_CREDIT_AMOUNT = 4
    WAITING_GIVE_CREDIT_ALL_AMOUNT = 5
    WAITING_BAN_USER_ID = 6
    WAITING_UNBAN_USER_ID = 7
    WAITING_SHORTNER_DOMAIN = 8
    WAITING_SHORTNER_API = 9
    WAITING_WELCOME_CREDIT = 10
    WAITING_TTS_CHARGE = 11
    WAITING_EARN_CREDIT = 12
    WAITING_USER_INFO_ID = 13
    WAITING_DEACTIVATE_REASON = 14
    WAITING_DEACTIVATE_TIME = 15
    WAITING_RATING_COUNT = 16
    WAITING_PAYMENT_AMOUNT = 17
    WAITING_TRANSACTION_ID = 18
    WAITING_MIN_PAYMENT = 19
    WAITING_MAX_PAYMENT = 20
    WAITING_PAYMENT_RATE = 21
    WAITING_QR_CODE_URL = 22 # New state for QR code URL
    WAITING_PAYMENT_NUMBER = 23 # New state for payment number
    WAITING_PAYMENT_NAME = 24 # New state for payment name
    WAITING_REFERRAL_CODE = 25 # New state for referral code input
    WAITING_REFERRER_BONUS = 26 # New state for setting referrer bonus
    WAITING_REFERRED_BONUS = 27 # New state for setting referred bonus
    WAITING_LINK_TIMEOUT = 28 # New state for link timeout setting
    WAITING_FREE_CREDIT = 29 # New state for free credit per link setting
    WAITING_BUY_CREDIT_RATE = 30 # New state for buy credit rate setting
    WAITING_REFERRAL_SETTING = 31 # New state for referral setting selection
    WAITING_QR_CODE_FILE = 32 # New state for QR code file upload
    WAITING_UPI_ID_ONLY = 33 # New state for UPI ID only input
    WAITING_QR_UPI_SETUP = 34 # New state for setting up both QR and UPI

def get_user_from_db(user_id: int) -> User:
    """Get or create user from database with enhanced error handling"""
    if not isinstance(user_id, int) or user_id <= 0:
        print(f"Invalid user_id provided: {user_id}")
        return User(user_id=user_id or 0, is_active=True, credits=10.0)

    db = None
    try:
        db = SessionLocal()
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            user = User(user_id=user_id, is_active=True)
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"Created new user: {user_id}")
        return user
    except Exception as e:
        print(f"Database error in get_user_from_db for user {user_id}: {e}")
        if db:
            try:
                db.rollback()
            except Exception as rollback_error:
                print(f"Error during rollback: {rollback_error}")
        # Return a default user object if database fails
        return User(user_id=user_id, is_active=True, credits=10.0)
    finally:
        if db:
            try:
                db.close()
            except Exception as close_error:
                print(f"Error closing database connection: {close_error}")

def update_user_info(message: Message):
    """Update user information in database with enhanced error handling"""
    if not message or not message.from_user or not message.from_user.id:
        print("Invalid message or user data provided to update_user_info")
        return

    db = None
    try:
        db = SessionLocal()
        user = db.query(User).filter(User.user_id == message.from_user.id).first()
        if user:
            # Safely handle Unicode characters with proper error handling
            try:
                user.username = message.from_user.username or None
                user.first_name = (message.from_user.first_name or "User")[:100] if message.from_user.first_name else "User"
                user.last_name = (message.from_user.last_name or "")[:100] if message.from_user.last_name else None
                user.last_active = datetime.utcnow()
                db.commit()
            except UnicodeError as unicode_error:
                print(f"Unicode error updating user info: {unicode_error}")
                # Use safe defaults if unicode fails
                user.first_name = "User"
                user.last_name = None
                user.last_active = datetime.utcnow()
                db.commit()
    except Exception as e:
        print(f"Error updating user info for user {message.from_user.id}: {e}")
        if db:
            try:
                db.rollback()
            except Exception as rollback_error:
                print(f"Error during rollback in update_user_info: {rollback_error}")
    finally:
        if db:
            try:
                db.close()
            except Exception as close_error:
                print(f"Error closing database in update_user_info: {close_error}")

def log_credit_transaction(user_id: int, amount: float, transaction_type: str, description: str = None):
    """Log credit transaction for tracking with enhanced error handling"""
    # Input validation
    if not isinstance(user_id, int) or user_id <= 0:
        print(f"Invalid user_id for credit transaction: {user_id}")
        return False

    if not isinstance(amount, (int, float)):
        print(f"Invalid amount for credit transaction: {amount}")
        return False

    if not transaction_type or not isinstance(transaction_type, str):
        print(f"Invalid transaction_type: {transaction_type}")
        return False

    db = None
    try:
        db = SessionLocal()
        
        # Generate unique transaction ID
        transaction_id = generate_transaction_id()
        
        transaction = CreditTransaction(
            user_id=user_id,
            amount=float(amount),
            transaction_type=transaction_type[:50],  # Limit length to prevent overflow
            description=description[:200] if description else None,  # Limit description length
            transaction_id=transaction_id
        )
        db.add(transaction)
        db.commit()
        
        print(f"✅ Transaction logged with ID: {transaction_id}")
        return transaction_id  # Return transaction ID instead of True
    except Exception as e:
        print(f"Error logging credit transaction for user {user_id}: {e}")
        if db:
            try:
                db.rollback()
            except Exception as rollback_error:
                print(f"Error during rollback in log_credit_transaction: {rollback_error}")
        return False
    finally:
        if db:
            try:
                db.close()
            except Exception as close_error:
                print(f"Error closing database in log_credit_transaction: {close_error}")

async def send_new_user_notification(message: Message, user):
    """Send new user notification to channel with details"""
    try:
        target_channel = connected_channel_id or CHANNEL_ID
        if not target_channel:
            print("⚠️ No channel connected for notifications, skipping new user notification")
            return

        # Get referral information if available
        referral_info = ""
        if len(message.command) > 1:
            param = message.command[1]
            if param.startswith("ref_"):
                try:
                    # Get referrer details
                    try:
                        from referral_system import get_referrer_details
                        referrer_name = get_referrer_details(param)
                    except ImportError:
                        referrer_name = "Unknown Referrer"
                    referral_info = f"\n🔗 **Referred by:** {referrer_name}\n📊 **Referral Code:** `{param}`"
                except:
                    referral_info = f"\n🔗 **Referral Code:** `{param}`"

        # Create notification message
        notification_message = (
            f"👥 **New User Joined!** 🎉\n\n"
            f"👤 **Name:** {message.from_user.first_name or 'Unknown'}"
            f"{' ' + message.from_user.last_name if message.from_user.last_name else ''}\n"
            f"🆔 **User ID:** `{message.from_user.id}`\n"
            f"👤 **Username:** @{message.from_user.username or 'No username'}\n"
            f"📅 **Join Date:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
            f"💎 **Starting Credits:** {user.credits}\n"
            f"🌍 **Language:** {message.from_user.language_code or 'Unknown'}"
            f"{referral_info}\n\n"
            f"🚀 **Total Users:** {get_total_user_count()}\n"
            f"📊 **Welcome #{get_total_user_count()}**"
        )

        # Send to channel
        try:
            # Better channel ID validation and conversion (secure type handling)
            target_channel_str = str(target_channel) if target_channel is not None else ""
            if target_channel_str.startswith('-100'):
                target_id = int(target_channel_str)
            elif target_channel_str.startswith('-'):
                target_id = int(target_channel_str)
            elif target_channel_str.startswith('@'):
                target_id = target_channel_str
            else:
                target_id = f"@{target_channel_str}"
                
            await app.send_message(target_id, notification_message)
            print(f"✅ New user notification sent to channel for user {message.from_user.id}")
        except Exception as send_error:
            print(f"❌ Error sending new user notification to channel: {send_error}")
            print(f"💡 Channel troubleshooting:")
            print(f"   - Check if bot is added to channel")
            print(f"   - Check if bot has admin rights in channel")
            print(f"   - Verify CHANNEL_ID: {target_channel}")

    except Exception as e:
        print(f"❌ Error in send_new_user_notification: {e}")

def get_total_user_count():
    """Get total user count from database"""
    try:
        db = SessionLocal()
        count = db.query(User).count()
        db.close()
        return count
    except:
        return "Unknown"

# Handler for when bot is added to a group/channel
@app.on_message(filters.new_chat_members)
async def welcome_bot_to_channel(client: Client, message: Message):
    """Handle when bot is added to a channel or group"""
    try:
        # Check if bot was added
        bot_user = await app.get_me()
        
        for new_member in message.new_chat_members:
            if new_member.id == bot_user.id:
                # Bot was added to this channel/group
                chat_info = message.chat
                
                # Send thank you message
                await message.reply(
                    f"🙏 **Dhanyawad mujhe is {chat_info.type} me add karne ke liye!** 🙏\n\n"
                    f"🏷️ **{chat_info.type.title()}:** {chat_info.title}\n"
                    f"🆔 **ID:** `{chat_info.id}`\n"
                    f"👥 **Members:** {chat_info.members_count or 'Unknown'}\n\n"
                    f"📋 **Instructions for Owner:**\n"
                    f"🔹 ab owner ko is channel me `/connect` command send karna hai\n"
                    f"🔹 tab main is channel ko notifications ke liye use karunga\n"
                    f"🔹 New users, payments, aur database backups yahan aayenge\n\n"
                    f"⚠️ **Note:** keval Owner hi `/connect` command use kar sakte hai"
                )
                
                # Notify owner about new channel addition
                try:
                    if OWNER_ID and OWNER_ID != 0:
                        await app.send_message(
                            OWNER_ID,
                            f"🎉 **Bot ko naye channel me add kiya gaya!**\n\n"
                            f"🏷️ **{chat_info.type.title()}:** {chat_info.title}\n"
                            f"🆔 **ID:** `{chat_info.id}`\n"
                            f"👥 **Members:** {chat_info.members_count or 'Unknown'}\n\n"
                            f"💡 **Action Required:**\n"
                            f"📱 us channel me jakar `/connect` command send kare\n"
                            f"🔗 tab channel notifications ke liye connected ho jaega"
                        )
                except Exception as owner_notify_error:
                    print(f"Failed to notify owner about new channel: {owner_notify_error}")
                
                break
                
    except Exception as e:
        print(f"Error in welcome_bot_to_channel: {e}")

# Connect command for channels
@app.on_message(filters.command("connect"))
async def connect_channel_command(client: Client, message: Message):
    """Connect current channel for notifications - Owner only"""
    global connected_channel_id
    
    try:
        # Check if command is from owner
        if not message.from_user or message.from_user.id != OWNER_ID:
            await message.reply("❌ keval Owner hi is command ka use kar sakte hai!")
            return
        
        # Get current chat info
        chat_info = message.chat
        
        # Check if it's a group or channel
        if chat_info.type not in ["group", "supergroup", "channel"]:
            await message.reply("❌ yah command keval groups/channels me use kare!")
            return
        
        # Connect this channel
        connected_channel_id = str(chat_info.id)
        
        # Store in database for persistence (optional enhancement)
        try:
            from database import update_setting
            update_setting("connected_channel_id", float(chat_info.id), f"Connected channel: {chat_info.title}")
        except Exception as db_error:
            print(f"Could not store channel in database: {db_error}")
        
        await message.reply(
            f"✅ **Channel Successfully Connected!** 🎉\n\n"
            f"🏷️ **{chat_info.type.title()}:** {chat_info.title}\n"
            f"🆔 **ID:** `{chat_info.id}`\n"
            f"👥 **Members:** {chat_info.members_count or 'Unknown'}\n\n"
            f"📋 **ab yah channel receive karega:**\n"
            f"🔹 naye user join notifications\n"
            f"🔹 Database backups (har 10 minutes)\n"
            f"🔹 Payment request notifications\n"
            f"🔹 System alerts aur updates\n\n"
            f"🚀 **Channel connection active hai!**"
        )
        
        # Notify in private message too
        try:
            await app.send_message(
                OWNER_ID,
                f"✅ **Channel Connected Successfully!**\n\n"
                f"🏷️ **{chat_info.type.title()}:** {chat_info.title}\n"
                f"🆔 **ID:** `{chat_info.id}`\n\n"
                f"ab sabhi bot notifications is channel par aayenge. 🎉"
            )
        except Exception as private_notify_error:
            print(f"Could not send private notification: {private_notify_error}")
        
        print(f"✅ Channel connected: {chat_info.title} (ID: {chat_info.id})")
        
    except Exception as e:
        print(f"Error in connect_channel_command: {e}")
        await message.reply(f"❌ Error connecting channel: {str(e)[:100]}")

# Load connected channel from database on startup
async def load_connected_channel():
    """Load connected channel from database on bot startup"""
    global connected_channel_id
    try:
        from database import get_setting
        channel_id = get_setting("connected_channel_id", None)
        if channel_id and channel_id != 0:
            connected_channel_id = str(int(channel_id))
            print(f"✅ Loaded connected channel from database: {connected_channel_id}")
    except Exception as e:
        print(f"Could not load connected channel from database: {e}")

@app.on_message(filters.command("test_channel"))
async def test_channel_command(client: Client, message: Message):
    """Test channel connectivity - Owner only command"""
    # Handle case where message.from_user might be None (channel messages)
    if not message.from_user:
        await message.reply("❌ **Commands ko private message me bheje, channel me nahi!**\n\nBot ko private message me `/test_channel` command send kare.")
        return
        
    user_id = message.from_user.id
    
    if user_id != OWNER_ID:
        await message.reply("❌ This command is for owner only.")
        return
    
    target_channel = connected_channel_id or CHANNEL_ID
    if not target_channel:
        await message.reply("❌ **No Channel Connected!**\n\n📋 **Options:**\n🔹 Bot ko channel me add kare\n🔹 Channel me `/connect` command send kare\n🔹 ya CHANNEL_ID environment variable set kare")
        return
    
    await message.reply(f"🔍 **Testing Channel Connection...**\n\n📋 **Channel ID:** `{target_channel}`\n📍 **Source:** {'Runtime Connected' if connected_channel_id else 'Environment Variable'}")
    
    try:
        # Test channel ID validation
        if target_channel.startswith('-100'):
            target_id = int(target_channel)
            channel_type = "Supergroup"
        elif target_channel.startswith('-'):
            target_id = int(target_channel)
            channel_type = "Group/Channel"
        elif target_channel.startswith('@'):
            target_id = target_channel
            channel_type = "Username"
        else:
            target_id = f"@{target_channel}"
            channel_type = "Username (auto-prefixed)"
        
        await message.reply(f"✅ **Channel ID Validation Passed**\n\n🎯 **Target ID:** `{target_id}`\n📂 **Type:** {channel_type}")
        
        # Test channel access
        try:
            channel_info = await client.get_chat(target_id)
            await message.reply(
                f"✅ **Channel Access Successful!**\n\n"
                f"📋 **Channel Details:**\n"
                f"🏷️ **Title:** {channel_info.title}\n"
                f"📂 **Type:** {channel_info.type}\n"
                f"🆔 **ID:** {channel_info.id}\n"
                f"👥 **Members:** {channel_info.members_count or 'Unknown'}\n"
                f"📝 **Description:** {channel_info.description[:100] if channel_info.description else 'None'}"
            )
            
            # Test sending a message
            try:
                test_msg = await client.send_message(
                    target_id,
                    f"🧪 **Channel Test Message**\n\n"
                    f"📅 **Time:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
                    f"✅ **Status:** Channel connection successful!\n"
                    f"🤖 **Bot:** Working perfectly\n\n"
                    f"🔧 **Test initiated by:** {message.from_user.first_name}"
                )
                await message.reply("✅ **Message Send Test Successful!**\n\nChannel connection is working perfectly! 🎉")
                
            except Exception as send_error:
                await message.reply(
                    f"❌ **Message Send Test Failed!**\n\n"
                    f"**Error:** `{send_error}`\n\n"
                    f"**Possible Solutions:**\n"
                    f"• Check if bot has 'Send Messages' permission\n"
                    f"• Verify bot is admin in channel\n"
                    f"• Check if channel allows bots to post"
                )
                
        except Exception as access_error:
            await message.reply(
                f"❌ **Channel Access Failed!**\n\n"
                f"**Error:** `{access_error}`\n\n"
                f"**Common Solutions:**\n"
                f"• Add bot to channel as admin\n"
                f"• Check CHANNEL_ID format\n"
                f"• Verify channel exists and is accessible\n"
                f"• Check if channel is private/public"
            )
            
    except Exception as validation_error:
        await message.reply(
            f"❌ **Channel ID Validation Failed!**\n\n"
            f"**Error:** `{validation_error}`\n\n"
            f"**CHANNEL_ID Format Examples:**\n"
            f"• `-1001234567890` (Supergroup)\n"
            f"• `-123456789` (Group)\n"
            f"• `@channelname` (Public channel)\n"
            f"• `channelname` (Public channel)\n\n"
            f"💡 **ya bot ko channel me add karke `/connect` command use kare!**"
        )

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    user_id = message.from_user.id
    user = get_user_from_db(user_id)
    update_user_info(message)

    # Check if this is a credit link click or referral code
    if len(message.command) > 1:
        param = message.command[1]
        if param.startswith("credit_"):
            from free_credit import on_credit_link_click
            token = param.replace("credit_", "")
            result_message = on_credit_link_click(token)
            await message.reply(result_message)
            return
        elif param.startswith("ref_"):
            # Process referral code properly
            referral_code = param

            # Check if user is new (joined in last 5 minutes)
            is_new_user = (datetime.utcnow() - user.join_date).total_seconds() < 300

            if is_new_user:
                success, result = process_referral(referral_code, user_id)
                if success:
                    # Send success message to referred user
                    await message.reply(
                        f"🎉 **Referral Success**\n\n"
                        f"✅ Aapko {result['referrer_name']} ne refer kiya hai\n"
                        f"🎁 **Aapko mile:** {result['referred_bonus']} credits\n"
                        f"💰 **{result['referrer_name']} ko mile:** {result['referrer_bonus']} credits\n\n"
                        f"🚀 ab aap bot use kar sakte hai apne bonus credits ke saath",
                        reply_markup=get_user_panel()
                    )

                    # Send notification to referrer
                    try:
                        await app.send_message(
                            result['referrer_id'],
                            f"🎉 **naya Referral Success**\n\n"
                            f"👤 **naya User:** {result['referred_name']}\n"
                            f"💰 **Aapko mile:** {result['referrer_bonus']} credits\n"
                            f"🎁 **unhe mile:** {result['referred_bonus']} credits\n\n"
                            f"📈 aapki referral link se yah user aaya hai\n"
                            f"🙏 hamare community ko badhane ke liye Dhanyawad"
                        )
                    except Exception as notify_error:
                        print(f"Could not notify referrer: {notify_error}")
                    return
                else:
                    await message.reply(f"❌ Referral failed: {result}")
            else:
                await message.reply(
                    "⚠️ **Referral codes can only be used by new users within 5 minutes of joining.**\n\n"
                    "You can still use the bot normally!",
                    reply_markup=get_user_panel()
                )

    # Check bot status for regular users
    if user_id != OWNER_ID:
        db = SessionLocal()
        try:
            bot_status = db.query(BotStatus).first()
            if bot_status and not bot_status.is_active:
                if bot_status.deactivated_until and datetime.utcnow() < bot_status.deactivated_until:
                    await message.reply(
                        f"🤖 **Bot Temporarily Deactivated**\n\n"
                        f"📝 Reason: {bot_status.deactivated_reason}\n"
                        f"⏰ Available again: {bot_status.deactivated_until.strftime('%d/%m/%Y %H:%M')}\n\n"
                        f"Kripaya kuch samay baad try kare."
                    )
                    return
                elif not bot_status.deactivated_until:
                    await message.reply(
                        f"🤖 **Bot Deactivated**\n\n"
                        f"📝 Reason: {bot_status.deactivated_reason or 'Maintenance'}\n\n"
                        f"Kripaya kuch samay baad try kare."
                    )
                    return
        finally:
            db.close()

    # Check if user is owner
    if user_id == OWNER_ID:
        await message.reply(
            "🌟═════════════════🌟\n"
            "👑 **MASTER CONTROL PANEL** 👑\n"
            "🌟═════════════════🌟\n\n"
            "🎯 **Ready to take control?** ⚡\n"
            "💫 Niche diye gaye powerful options se apni pasand chune:\n"
            "🔥 **Your command is my wish** 🔥",
            reply_markup=get_owner_panel()
        )
    else:
        # Check user status
        if user.is_banned == True:
            await message.reply("❌ Aap is bot ka istemal nahi kar sakte.")
            return

        if user.is_active == False:
            await message.reply("⚠️ Aapka account deactive hai. Admin se contact karo.")
            return

        # Check if new user (joined today and this is first interaction)
        is_new_user = (user.join_date.date() == datetime.utcnow().date() and
                      abs((user.last_active - user.join_date).total_seconds()) < 60)

        if is_new_user:
            # Send new user notification to channel
            await send_new_user_notification(message, user)
            
            # New user - show about page
            await message.reply(
                "🎉 **TTS Bot me Welcome hai aapka!** 🎉\n\n"
                "Ye ek advanced Text-to-Speech bot hai jo aapke text ko natural voice me convert karta hai.\n\n"
                "**Features:**\n"
                "🎤 Multiple voice types\n"
                "⚡ Fast conversion speed\n"
                "🆓 Free credits naye users ke liye\n"
                "💰 Credit system\n\n"
                "Aapko **10 free credits** mile hain!\n"
                "Har word ke liye 0.05 credit charge hota hai.",
                reply_markup=get_about_keyboard()
            )
        else:
            # Existing user - show user panel
            await message.reply(
                f"🌟 **Welcome back** {user.first_name}! 🌟\n\n"
                f"💎 **Aapke Credits:** {user.credits}\n"
                f"🚀 **Ready for TTS Magic?** ✨\n\n"
                f"🎯 Niche diye gaye options me se choose karo:",
                reply_markup=get_user_panel()
            )

@app.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    """Handle all callback queries"""
    data = callback_query.data
    user_id = callback_query.from_user.id

    # Owner callbacks
    if data == "back_to_owner":
        await callback_query.edit_message_text(
            "🌟═════════════════🌟\n"
            "👑 **MASTER CONTROL PANEL** 👑\n"
            "🌟═════════════════🌟\n\n"
            "🎯 **Ready to take control?** ⚡\n"
            "💫 Niche diye gaye powerful options se apni pasand chune:\n"
            "🔥 **Your command is my wish** 🔥",
            reply_markup=get_owner_panel()
        )

    elif data == "owner_tts":
        await callback_query.edit_message_text(
            "🎤 **Owner TTS**\n\n"
            "Kripaya apni pasandida voice select karo:",
            reply_markup=get_voice_selection_owner()
        )

    elif data == "owner_users":
        await callback_query.edit_message_text(
            "👥 **User Management**\n\n"
            "Yahan se aap users ko manage kar sakte hai:",
            reply_markup=get_users_panel()
        )

    elif data == "owner_broadcast":
        user_states[user_id] = UserState.WAITING_BROADCAST_TEXT
        await callback_query.edit_message_text(
            "📢 **Broadcast Message**\n\n"
            "Kripaya woh message bheje jo aap sabhi users ko send karna chahte hai:\n\n"
            "**Available Placeholders:**\n"
            "• `{first_name}` - User ka naam\n"
            "• `{last_name}` - User ka surname\n"
            "• `{username}` - Username\n"
            "• `{user_id}` - User ID\n"
            "• `{credits}` - Current credits\n"
            "• `{join_date}` - Join date\n"
            "• `{tts_count}` - Total TTS requests\n\n"
            "**Example:**\n"
            "`Hello {first_name}! Your ID: {user_id}`",
            reply_markup=get_back_to_owner()
        )

    elif data == "owner_status":
        # Show loading message first
        loading_msg = await callback_query.edit_message_text(
            "📊 **Bot ke Comprehensive Statistics gather kar rahe hain...**\n\n"
            "🔄 Please wait jab tak hum sab data analyze karte hain..."
        )
        
        # Gather all statistics with error handling
        db = None
        try:
            db = SessionLocal()
            from sqlalchemy import func, and_
            from datetime import datetime, timedelta
            
            # Basic counts with error handling
            total_users = db.query(User).count()
            active_users = db.query(User).filter(User.is_active == True, User.is_banned == False).count()
            banned_users = db.query(User).filter(User.is_banned == True).count()
            
            # TTS Statistics
            total_tts_requests = db.query(TTSRequest).count()
            total_words_processed = db.query(func.sum(TTSRequest.credits_used)).scalar() or 0
            total_words_processed = int(total_words_processed / 0.05)  # Convert credits to words
            
            # Today's activity
            today = datetime.utcnow().date()
            today_start = datetime.combine(today, datetime.min.time())
            
            today_users = db.query(User).filter(User.last_active >= today_start).count()
            today_tts = db.query(TTSRequest).filter(TTSRequest.timestamp >= today_start).count()
            
            # This week's activity
            week_start = datetime.utcnow() - timedelta(days=7)
            week_users = db.query(User).filter(User.last_active >= week_start).count()
            week_tts = db.query(TTSRequest).filter(TTSRequest.timestamp >= week_start).count()
            
            # Credit statistics
            total_credits_given = db.query(func.sum(CreditTransaction.amount)).filter(
                CreditTransaction.amount > 0
            ).scalar() or 0
            
            total_credits_used = abs(db.query(func.sum(CreditTransaction.amount)).filter(
                CreditTransaction.amount < 0
            ).scalar() or 0)
            
            # Payment statistics
            try:
                from database import PaymentRequest
                total_payments = db.query(PaymentRequest).count()
                confirmed_payments = db.query(PaymentRequest).filter(PaymentRequest.status == 'confirmed').count()
                pending_payments = db.query(PaymentRequest).filter(PaymentRequest.status == 'pending').count()
                total_revenue = db.query(func.sum(PaymentRequest.amount)).filter(
                    PaymentRequest.status == 'confirmed'
                ).scalar() or 0
            except Exception as payment_error:
                print(f"Payment statistics error: {payment_error}")
                total_payments = confirmed_payments = pending_payments = total_revenue = 0
            
            # Referral statistics with proper error handling
            try:
                total_referrals = db.query(ReferralSystem).filter(ReferralSystem.is_claimed == True).count()
                referral_credits_distributed = db.query(func.sum(ReferralSystem.credits_earned)).scalar() or 0
            except Exception as referral_error:
                print(f"Referral statistics error: {referral_error}")
                db.rollback()  # Rollback transaction
                total_referrals = 0
                referral_credits_distributed = 0
            
            # Bot settings
            bot_status = db.query(BotStatus).first()
            bot_active_status = "🟢 Active" if bot_status and bot_status.is_active else "🔴 Inactive"
            
            # Top users by TTS usage
            top_users = db.query(
                TTSRequest.user_id, 
                func.count(TTSRequest.id).label('request_count')
            ).group_by(TTSRequest.user_id).order_by(
                func.count(TTSRequest.id).desc()
            ).limit(3).all()
            
            # Average statistics
            avg_tts_per_user = total_tts_requests / total_users if total_users > 0 else 0
            avg_words_per_tts = total_words_processed / total_tts_requests if total_tts_requests > 0 else 0
            
            # Database size estimation
            db_size = "Unknown"
            try:
                import os
                if os.path.exists('bot.db'):
                    size_bytes = os.path.getsize('bot.db')
                    db_size = f"{size_bytes / 1024 / 1024:.2f} MB"
            except:
                pass
            
            # Build top users text
            top_users_text = ""
            if top_users:
                top_users_text = "\n👑 **Top 3 Users by TTS Usage:**\n"
                for i, (user_id, count) in enumerate(top_users, 1):
                    try:
                        user_info = db.query(User).filter(User.user_id == user_id).first()
                        user_name = user_info.first_name if user_info and user_info.first_name else "Unknown"
                        top_users_text += f"{i}. {user_name} - {count} requests\n"
                    except:
                        top_users_text += f"{i}. User {user_id} - {count} requests\n"
            
            # System uptime
            uptime_text = "System running normally"
            
            db.close()
            
            # Create comprehensive status message
            status_message = (
                f"📊 **COMPLETE BOT STATUS DASHBOARD** 📊\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 **Bot Information:**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔋 **Status:** {bot_active_status}\n"
                f"⏱️ **Uptime:** {uptime_text}\n"
                f"💾 **Database Size:** {db_size}\n"
                f"📅 **Report Date:** {datetime.utcnow().strftime('%d/%m/%Y %H:%M UTC')}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👥 **USER STATISTICS:**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 **Total Users:** {total_users:,}\n"
                f"✅ **Active Users:** {active_users:,}\n"
                f"🚫 **Banned Users:** {banned_users:,}\n"
                f"📊 **Active Rate:** {(active_users/total_users*100 if total_users > 0 else 0):.1f}% of total\n\n"
                f"🔥 **ACTIVITY METRICS:**\n"
                f"📅 **Today Active:** {today_users:,} users\n"
                f"📊 **This Week:** {week_users:,} users\n"
                f"⚡ **Engagement:** {(today_users/total_users*100 if total_users > 0 else 0):.1f}% daily activity\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎤 **TTS USAGE STATISTICS:**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Total Requests:** {total_tts_requests:,}\n"
                f"📝 **Words Processed:** {total_words_processed:,}\n"
                f"📅 **Today's TTS:** {today_tts:,}\n"
                f"📊 **This Week:** {week_tts:,}\n"
                f"📈 **Avg per User:** {avg_tts_per_user:.1f} requests\n"
                f"📝 **Avg Words/TTS:** {avg_words_per_tts:.0f} words\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 **FINANCIAL OVERVIEW:**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💳 **Total Payments:** {total_payments:,}\n"
                f"✅ **Confirmed:** {confirmed_payments:,}\n"
                f"⏳ **Pending:** {pending_payments:,}\n"
                f"💰 **Total Revenue:** ₹{total_revenue:,.0f}\n"
                f"📊 **Success Rate:** {(confirmed_payments/total_payments*100 if total_payments > 0 else 0):.1f}%\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💎 **CREDIT SYSTEM:**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 **Credits Given:** {total_credits_given:,.0f}\n"
                f"📉 **Credits Used:** {total_credits_used:,.0f}\n"
                f"💹 **Net Flow:** {(total_credits_given - total_credits_used):+.0f}\n"
                f"🎁 **Referral Credits:** {referral_credits_distributed:.0f}\n"
                f"👥 **Total Referrals:** {total_referrals:,}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 **PERFORMANCE INSIGHTS:**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔥 **User Retention:** {(week_users/total_users*100 if total_users > 0 else 0):.1f}% weekly\n"
                f"⚡ **Daily Growth:** +{today_users - week_users + today_users if week_users > 0 else 0} new today\n"
                f"💡 **TTS Adoption:** {(total_tts_requests > 0)}, {total_users} users tried TTS\n"
                f"🎯 **Revenue/User:** ₹{(total_revenue/confirmed_payments if confirmed_payments > 0 else 0):.0f} avg\n"
                f"{top_users_text}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                "✅ **Status: All Systems Operational** ✅\n"
                "🚀 **Bot performing excellently!** 🚀"
            )
            
            await callback_query.edit_message_text(
                status_message,
                reply_markup=get_back_to_owner()
            )
            
        except Exception as e:
            print(f"Error gathering bot statistics: {e}")
            try:
                await callback_query.edit_message_text(
                    f"❌ **Error Gathering Statistics**\n\n"
                    f"📊 kuch technical issue hui hai statistics gather karte samay.\n\n"
                    f"**Error Details:**\n"
                    f"`{str(e)[:100]}...`\n\n"
                    f"🔧 Kripaya baad me try kare ya database check kare.\n"
                    f"📱 agar problem persist kare to code review kare.",
                    reply_markup=get_back_to_owner()
                )
            except Exception as edit_error:
                print(f"Failed to edit message with error: {edit_error}")
                try:
                    await callback_query.answer("Statistics loading failed. Check console for details.", show_alert=True)
                except:
                    pass

    elif data == "owner_credit_handler":
        # Check if user is owner
        if user_id != OWNER_ID:
            await callback_query.answer("❌ Access denied! Owner only.", show_alert=True)
            return
            
        # Credit Handler Panel
        await callback_query.edit_message_text(
            "💰 **Credit Handler**\n\n"
            "Credit management aur link shortener options:",
            reply_markup=get_credit_handler_panel()
        )

    elif data == "credit_handler_buy":
        # Check if user is owner
        if user_id != OWNER_ID:
            await callback_query.answer("❌ Access denied! Owner only.", show_alert=True)
            return
            
        # Check if QR code and UPI ID are available
        db = SessionLocal()
        try:
            qr_settings = db.query(QRCodeSettings).filter(QRCodeSettings.is_active == True).first()
            if qr_settings and (qr_settings.qr_code_file_id or qr_settings.qr_code_url) and qr_settings.payment_number:
                # Show current QR and payment details
                if qr_settings.qr_code_file_id:
                    # File ID based QR code
                    await callback_query.edit_message_text(
                        f"💳 **Buy Credit Management**\n\n"
                        f"📱 **UPI ID:** {qr_settings.payment_number}\n"
                        f"👤 **Payment Name:** {qr_settings.payment_name or 'Not Set'}\n"
                        f"🖼️ **QR Code:** ✅ Available (File ID)\n\n"
                        "Manage QR code aur UPI details:",
                        reply_markup=get_buy_credit_management_panel()
                    )
                else:
                    # URL based QR code (backward compatibility)
                    await callback_query.edit_message_text(
                        f"💳 **Buy Credit Management**\n\n"
                        f"📱 **UPI ID:** {qr_settings.payment_number}\n"
                        f"👤 **Payment Name:** {qr_settings.payment_name or 'Not Set'}\n"
                        f"🖼️ **QR Code:** ✅ Available (URL)\n\n"
                        "Manage QR code aur UPI details:",
                        reply_markup=get_buy_credit_management_panel()
                    )
            else:
                # QR or UPI not available
                await callback_query.edit_message_text(
                    "💳 **Buy Credit Management**\n\n"
                    "❌ QR code aur UPI ID available nahi hai\n"
                    "Pehle setup kare:",
                    reply_markup=get_buy_credit_setup_panel()
                )
        finally:
            db.close()

    elif data == "owner_shortner":
        # Check if link shortner exists
        db = SessionLocal()
        try:
            shortner = db.query(LinkShortner).filter(LinkShortner.is_active == True).first()
            if shortner:
                await callback_query.edit_message_text(
                    "🔗 **Link Shortner**\n\n"
                    f"✅ Active Domain: {shortner.domain}",
                    reply_markup=get_shortner_panel()
                )
            else:
                await callback_query.edit_message_text(
                    "🔗 **Link Shortner**\n\n"
                    "❌ koi link shortner add nahi hai.",
                    reply_markup=get_shortner_add_panel()
                )
        finally:
            db.close()

    elif data == "owner_referrals":
        await callback_query.edit_message_text(
            "👥 **Referral Management**\n\n"
            "yahan se aap referral system ko manage kar sakte hai:",
            reply_markup=get_owner_referral_panel()
        )

    elif data == "owner_referral_stats":
        db = SessionLocal()
        try:
            from sqlalchemy import func

            # Total referrals
            total_referrals = db.query(ReferralSystem).filter(
                ReferralSystem.is_claimed == True,
                ReferralSystem.referred_id.isnot(None)
            ).count()

            # Total credits given through referrals
            total_referral_credits = db.query(func.sum(ReferralSystem.credits_earned)).filter(
                ReferralSystem.is_claimed == True
            ).scalar() or 0.0

            # Active referrers (users with at least 1 referral)
            active_referrers = db.query(ReferralSystem.referrer_id).filter(
                ReferralSystem.is_claimed == True,
                ReferralSystem.referred_id.isnot(None)
            ).distinct().count()

            # Referrals this month
            from datetime import datetime
            month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            monthly_referrals = db.query(ReferralSystem).filter(
                ReferralSystem.is_claimed == True,
                ReferralSystem.created_at >= month_start
            ).count()

            # Average referrals per active referrer
            avg_referrals = total_referrals / active_referrers if active_referrers > 0 else 0

            await callback_query.edit_message_text(
                f"📊 **Referral System Statistics**\n\n"
                f"👥 **Total Referrals:** {total_referrals}\n"
                f"💰 **Credits Distributed:** {total_referral_credits:.0f}\n"
                f"🎯 **Active Referrers:** {active_referrers}\n"
                f"📅 **This Month:** {monthly_referrals}\n"
                f"📈 **Avg per Referrer:** {avg_referrals:.1f}\n\n"
                f"💡 **System Status:** Active\n"
                f"🎁 **Referrer Bonus:** 20 credits\n"
                f"🎁 **Welcome Bonus:** 15 credits",
                reply_markup=get_owner_referral_panel()
            )
        finally:
            db.close()

    elif data == "owner_top_referrers":
        await callback_query.edit_message_text(
            "🏆 **Top Referrers**\n\nReferral system is being updated.",
            reply_markup=get_owner_referral_panel()
        )

    elif data == "owner_referral_settings":
        await callback_query.edit_message_text(
            "⚙️ **Referral Settings**\n\n"
            "🎁 **Current Rewards:**\n"
            "• Referrer Bonus: 20 credits\n"
            "• Welcome Bonus: 15 credits\n\n"
            "📋 **Current Rules:**\n"
            "• New users only (5 min window)\n"
            "• No self-referrals\n"
            "• Unlimited referrals\n\n"
            "💡 Settings can be modified in database.py",
            reply_markup=get_owner_referral_panel()
        )

    elif data == "owner_settings":
        await callback_query.edit_message_text(
            "⚙️ **Bot Settings**\n\n"
            "Bot ki sabhi settings yahan manage kare:",
            reply_markup=get_settings_panel()
        )

    elif data == "settings_credits":
        await callback_query.edit_message_text(
            "💰 **Credits Settings**\n\n"
            "yahan se aap credit system ke settings manage kar sakte hai:",
            reply_markup=get_credits_settings_panel()
        )

    elif data == "settings_toggle":
        # Check current bot status
        db = SessionLocal()
        try:
            bot_status = db.query(BotStatus).first()
            if not bot_status:
                bot_status = BotStatus(is_active=True)
                db.add(bot_status)
                db.commit()

            if bot_status.is_active:
                # Ask for deactivation reason
                user_states[user_id] = UserState.WAITING_DEACTIVATE_REASON
                await callback_query.edit_message_text(
                    "⚠️ **Bot Deactivation**\n\n"
                    "Kripaya deactivation ka reason enter kare:",
                    reply_markup=get_back_to_owner()
                )
            else:
                # Reactivate bot
                bot_status.is_active = True
                bot_status.deactivated_reason = None
                bot_status.deactivated_until = None
                bot_status.updated_at = datetime.utcnow()
                db.commit()

                await callback_query.edit_message_text(
                    "✅ **Bot Activated!**\n\n"
                    "Bot ab sabhi users ke liye active hai.",
                    reply_markup=get_back_to_owner()
                )
        finally:
            db.close()

    elif data == "settings_shutdown":
        # Bot shutdown/start functionality
        db = SessionLocal()
        try:
            bot_status = db.query(BotStatus).first()
            if not bot_status:
                bot_status = BotStatus(is_active=True)
                db.add(bot_status)
                db.commit()

            if bot_status.is_active:
                # Shutdown bot
                bot_status.is_active = False
                bot_status.deactivated_reason = "Bot Shutdown by Owner"
                bot_status.deactivated_until = None  # Permanent until restarted
                bot_status.updated_at = datetime.utcnow()
                db.commit()

                await callback_query.edit_message_text(
                    "🔴 **Bot Shutdown!**\n\n"
                    "Bot ko successfully shutdown kar दिya गya.\n"
                    "sabhi users ke liye bot ab unavailable hai.",
                    reply_markup=get_back_to_owner()
                )
            else:
                # Start bot
                bot_status.is_active = True
                bot_status.deactivated_reason = None
                bot_status.deactivated_until = None
                bot_status.updated_at = datetime.utcnow()
                db.commit()

                await callback_query.edit_message_text(
                    "🟢 **Bot Started!**\n\n"
                    "Bot ko successfully start kar दिya गya.\n"
                    "sabhi users ke liye bot ab available hai.",
                    reply_markup=get_back_to_owner()
                )
        finally:
            db.close()

    elif data == "settings_rating":
        user_states[user_id] = UserState.WAITING_RATING_COUNT
        await callback_query.edit_message_text(
            "⭐ **Add Fake Ratings**\n\n"
            "कितne fake ratings add karna चाहते hai?\n"
            "Kripaya number enter kare:",
            reply_markup=get_back_to_owner()
        )

    elif data == "bot_backup":
        # Automatically start backup restore mode
        from datetime import datetime as dt
        user_states[user_id] = {
            'state': 'waiting_backup_main_db', 
            'backup_step': 1,
            'backup_start_time': dt.now()
        }
        
        backup_msg = await callback_query.edit_message_text(
            "🔄 **Bot Backup Mode Activated!** 🔄\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "**📂 BACKUP RESTORATION PROCESS**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ **Backup mode is now ACTIVE**\n"
            "⏰ **Started at:** " + dt.now().strftime('%H:%M:%S') + "\n\n"
            "📋 **Process Steps:**\n"
            "1️⃣ **Main Database** (.sql/.db/.backup)\n"
            "2️⃣ **Credit History** (.db/.sqlite)\n\n"
            "📤 **Step 1/2: Upload Main Database file now**\n\n"
            "💡 **Supported formats:**\n"
            "• `.sql`, `.dump`, `.backup` (PostgreSQL)\n"
            "• `.db`, `.sqlite`, `.sqlite3` (SQLite)\n\n"
            "⚠️ **Note:** Upload करने पर automatic processing शुरू हो जाएगी",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel Backup", callback_data="cancel_backup")]
            ])
        )
        
        # Store message ID for tracking
        user_states[user_id]['backup_msg_id'] = backup_msg.id

    elif data == "cancel_backup":
        # Cancel backup process and exit backup mode
        user_state_data = user_states.get(user_id, {})
        
        if isinstance(user_state_data, dict) and user_state_data.get('state') in ['waiting_backup_main_db', 'waiting_backup_credit_history_db']:
            backup_msg_id = user_state_data.get('backup_msg_id')
            backup_start_time = user_state_data.get('backup_start_time')
            elapsed_time = ""
            
            if backup_start_time:
                from datetime import datetime as dt2
                elapsed = dt2.now() - backup_start_time
                elapsed_time = f"\n⏱️ **Duration:** {elapsed.seconds}s"
            
            await callback_query.edit_message_text(
                "❌ **Backup Process Cancelled** ❌\n\n"
                "🔄 **Backup mode deactivated**\n"
                "⚡ **Bot returned to normal mode**\n"
                f"📅 **Cancelled at:** {dt2.now().strftime('%H:%M:%S')}"
                f"{elapsed_time}\n\n"
                "✅ **No changes made to current database**\n"
                "💡 **You can restart backup anytime from Settings**",
                reply_markup=get_back_to_owner()
            )
            
            # Clear backup state
            user_states.pop(user_id, None)
            
            # Auto-delete the cancellation message after 10 seconds
            try:
                from message_deletion import track_sent_message
                await track_sent_message(
                    callback_query.message.chat.id,
                    callback_query.message.id,
                    user_id,
                    'admin',
                    scheduled_deletion=True,
                    context='backup_cancelled'
                )
            except:
                pass
        else:
            await callback_query.edit_message_text(
                "❌ **No active backup process found**",
                reply_markup=get_back_to_owner()
            )

    elif data.startswith("add_rating_"):
        rating = int(data.split("_")[2])

        # Get how many ratings to add from user state
        rating_count = user_states.get(user_id, {}).get('rating_count', 1)

        db = SessionLocal()
        try:
            # Add fake ratings
            for _ in range(rating_count):
                fake_rating = BotRating(rating=rating, fake_rating=True)
                db.add(fake_rating)
            db.commit()

            await callback_query.edit_message_text(
                f"✅ **Ratings Added!**\n\n"
                f"Successfully added {rating_count} fake ratings of {rating}⭐",
                reply_markup=get_back_to_owner()
            )
        finally:
            db.close()

        user_states.pop(user_id, None)

    elif data == "confirm_deactivate":
        # Confirm deactivation with time and reason
        user_data = user_states.get(user_id, {})
        reason = user_data.get('reason', 'No reason provided')
        minutes = user_data.get('minutes', 0)

        db = SessionLocal()
        try:
            bot_status = db.query(BotStatus).first()
            if not bot_status:
                bot_status = BotStatus()
                db.add(bot_status)

            bot_status.is_active = False
            bot_status.deactivated_reason = reason

            if minutes > 0:
                from datetime import timedelta
                bot_status.deactivated_until = datetime.utcnow() + timedelta(minutes=minutes)
                time_text = f"⏰ Duration: {minutes} minutes"
            else:
                bot_status.deactivated_until = None
                time_text = "⏰ Duration: Permanent"

            bot_status.updated_at = datetime.utcnow()
            db.commit()

            # Show confirmation with OK button
            ok_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👌 OK", callback_data="back_to_owner")]
            ])

            await callback_query.edit_message_text(
                f"✅ **Bot Deactivated Successfully!**\n\n"
                f"📝 Reason: {reason}\n"
                f"{time_text}\n\n"
                f"Bot ab users ke liye unavailable hai.\n"
                f"(Owner access बना रहेगा)",
                reply_markup=ok_keyboard
            )
        finally:
            db.close()

        user_states.pop(user_id, None)

    # User callbacks
    elif data == "start_bot":
        await callback_query.edit_message_text(
            f"🌟 **Wellcome** {callback_query.from_user.first_name}! 🌟\n\n"
            f"💎 **aapke Credits:** 10\n"
            f"🚀 **Ready for TTS Magic?** ✨\n\n"
            f"🎯 नीचे दिए गए options me se choose kare:",
            reply_markup=get_user_panel()
        )

    elif data == "back_to_user":
        user = get_user_from_db(user_id)
        await callback_query.edit_message_text(
            f"🌟 **Wellcome** {callback_query.from_user.first_name}! 🌟\n\n"
            f"💎 **aapke Credits:** {user.credits}\n"
            f"🚀 **Ready for TTS Magic?** ✨\n\n"
            f"🎯 नीचे दिए गए options me se choose kare:",
            reply_markup=get_user_panel()
        )

    elif data == "user_tts":
        await callback_query.edit_message_text(
            "🎤 **Text to Speech**\n\n"
            "Kripaya apni pasandida voice select karo:",
            reply_markup=get_voice_selection()
        )

    elif data.startswith("voice_"):
        voice_type = data.replace("voice_", "")
        user_states[user_id] = {'state': UserState.WAITING_TTS_TEXT, 'voice': voice_type}

        voice_names = {
            'male1': 'Male Voice 1 (Deep)', 'male2': 'Male Voice 2 (Calm)',
            'male3': 'Male Voice 3 (Professional)', 'male4': 'Male Voice 4 (Energetic)',
            'male5': 'Male Voice 5 (Warm)',
            'female1': 'Female Voice 1 (Sweet)', 'female2': 'Female Voice 2 (Clear)',
            'female3': 'Female Voice 3 (Soft)', 'female4': 'Female Voice 4 (Bright)',
            'female5': 'Female Voice 5 (Melodic)'
        }

        if user_id == OWNER_ID:
            await callback_query.edit_message_text(
                f"🎤 **Owner TTS - {voice_names.get(voice_type, 'Unknown')}**\n\n"
                "Kripaya अपना text bheje (Maximum 3000 characters):\n\n"
                "⭐ **Owner:** Free unlimited access",
                reply_markup=get_back_to_owner()
            )
        else:
            await callback_query.edit_message_text(
                f"🎤 **TTS - {voice_names.get(voice_type, 'Unknown')}**\n\n"
                "Kripaya अपना text bheje (Maximum 3000 characters):\n\n"
                "💰 **Charges:** 0.05 credits per word",
                reply_markup=get_back_to_user()
            )

    elif data == "user_profile":
        user = get_user_from_db(user_id)
        db = SessionLocal()
        try:
            # Get comprehensive user statistics
            user_requests = db.query(TTSRequest).filter(TTSRequest.user_id == user_id).count()
            
            # Get total credits used in TTS
            from sqlalchemy import func
            total_credits_used = db.query(func.sum(TTSRequest.credits_used)).filter(TTSRequest.user_id == user_id).scalar() or 0.0
            
            # Get last TTS request date
            last_request = db.query(TTSRequest).filter(TTSRequest.user_id == user_id).order_by(TTSRequest.timestamp.desc()).first()
            last_request_date = last_request.timestamp.strftime('%d/%m/%Y %H:%M') if last_request else "कभी nahi"
            
            # Calculate days since joining
            from datetime import datetime
            days_since_join = (datetime.utcnow() - user.join_date).days
            
            # Get referral statistics
            referrals_made = db.query(ReferralSystem).filter(ReferralSystem.referrer_id == user_id).count()
            referral_credits_earned = db.query(func.sum(ReferralSystem.credits_earned)).filter(ReferralSystem.referrer_id == user_id).scalar() or 0.0
            
            # Check if referred by someone
            was_referred = db.query(ReferralSystem).filter(ReferralSystem.referred_id == user_id).first()
            referred_by = was_referred.referrer_id if was_referred else None
            
            # Get credit transaction history
            total_credits_earned = db.query(func.sum(CreditTransaction.amount)).filter(
                CreditTransaction.user_id == user_id,
                CreditTransaction.amount > 0
            ).scalar() or 0.0
            
            total_credits_spent = abs(db.query(func.sum(CreditTransaction.amount)).filter(
                CreditTransaction.user_id == user_id,
                CreditTransaction.amount < 0
            ).scalar() or 0.0)
            
            # Calculate average words per TTS
            avg_words = 0
            if user_requests > 0 and total_credits_used > 0:
                avg_words = int((total_credits_used / 0.05) / user_requests)  # 0.05 credits per word
            
            # Account status
            account_status = "🟢 Active" if user.is_active and not user.is_banned else "🔴 Restricted"
            
            # Membership level based on usage
            if user_requests >= 100:
                membership = "💎 Diamond User"
            elif user_requests >= 50:
                membership = "🥇 Gold User"
            elif user_requests >= 20:
                membership = "🥈 Silver User"
            elif user_requests >= 5:
                membership = "🥉 Bronze User"
            else:
                membership = "🆕 New User"
            
            await callback_query.edit_message_text(
                f"👤 **Complete User Profile** 👤\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 **Name:** {callback_query.from_user.first_name or 'User'} {callback_query.from_user.last_name or ''}\n"
                f"👤 **Username:** @{callback_query.from_user.username or 'None'}\n"
                f"🆔 **User ID:** `{user_id}`\n"
                f"📅 **Join Date:** {user.join_date.strftime('%d/%m/%Y %H:%M')}\n"
                f"📈 **Days Active:** {days_since_join} days\n"
                f"🕐 **Last Active:** {user.last_active.strftime('%d/%m/%Y %H:%M')}\n"
                f"🏆 **Membership:** {membership}\n"
                f"📊 **Status:** {account_status}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 **Credit Information** 💰\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💎 **Current Balance:** {user.credits:.2f} credits\n"
                f"📈 **Total Earned:** {total_credits_earned:.2f} credits\n"
                f"📉 **Total Spent:** {total_credits_spent:.2f} credits\n"
                f"💸 **TTS Usage:** {total_credits_used:.2f} credits\n"
                f"🎁 **Referral Earnings:** {referral_credits_earned:.2f} credits\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎤 **TTS Statistics** 🎤\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Total Requests:** {user_requests}\n"
                f"📝 **Average Words:** {avg_words} per request\n"
                f"🕒 **Last TTS Request:** {last_request_date}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👥 **Referral Information** 👥\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📤 **Referrals Made:** {referrals_made}\n"
                f"💰 **Referral Credits:** {referral_credits_earned:.2f}\n"
                f"📥 **Referred By:** {'Yes' if referred_by else 'Direct Join'}\n\n"
                f"🎯 **Keep using TTS Bot for more rewards!** ✨",
                reply_markup=get_back_to_user()
            )
        finally:
            db.close()

    elif data == "user_credits":
        await callback_query.edit_message_text(
            "💰 **Credit Management**\n\n"
            "yahan se aap apne credits manage kar sakte hai:",
            reply_markup=get_user_credit_panel()
        )

    elif data == "free_credit":
        # Call the actual free_credit.py function
        try:
            from free_credit import on_free_credit_button
            
            # Get free credit link from the free_credit.py module
            link, message = on_free_credit_button(user_id)
            
            if link:
                await callback_query.edit_message_text(
                    f"🆓 **Free Credits**\n\n"
                    f"{message}\n\n"
                    f"🔗 **Your Free Credit Link:**\n"
                    f"`{link}`\n\n"
                    f"⏰ Click the link within 10 minutes to earn 10 free credits!\n"
                    f"💡 Each link can only be used once.",
                    reply_markup=get_back_to_user()
                )
            else:
                await callback_query.edit_message_text(
                    f"🆓 **Free Credits**\n\n"
                    f"❌ {message}\n\n"
                    f"Kripaya baad me try kare ya admin se contact kare.",
                    reply_markup=get_user_credit_panel()
                )
        except Exception as error:
            print(f"Error in free credit handler: {error}")
            try:
                await callback_query.edit_message_text(
                    f"🆓 **Free Credits**\n\n"
                    f"❌ Service temporarily unavailable!\n"
                    f"Kripaya baad me try kare ya admin se contact kare.",
                    reply_markup=get_user_credit_panel()
                )
            except:
                await callback_query.answer("Service temporarily unavailable", show_alert=True)

    elif data == "buy_credit":
        min_amount = get_setting("min_payment_amount", default=10.0)
        max_amount = get_setting("max_payment_amount", default=100.0)
        payment_rate = get_setting("payment_rate", default=10.0)

        min_credits = int(min_amount * payment_rate)
        max_credits = int(max_amount * payment_rate)

        user_states[user_id] = UserState.WAITING_PAYMENT_AMOUNT
        prompt_msg = await callback_query.edit_message_text(
            f"💳 **Buy Credits**\n\n"
            f"💰 **Rate:** ₹1 = {payment_rate} credits\n"
            f"📊 **Minimum:** ₹{min_amount} ({min_credits} credits)\n"
            f"📊 **Maximum:** ₹{max_amount} ({max_credits} credits)\n\n"
            f"Kripaya amount enter kare (₹{min_amount} - ₹{max_amount}):",
            reply_markup=get_back_to_user()
        )
        # Track payment prompt - delete when user responds or times out
        await track_sent_message(
            prompt_msg,
            message_type=MessageType.PROMPT,
            user_id=user_id,
            custom_delay=60,  # Give user 1 minute to respond
            context="payment_flow"
        )

    elif data == "my_transaction":
        try:
            # Get user transaction summary
            db = SessionLocal()
            user = db.query(User).filter(User.user_id == user_id).first()
            
            # Get user credit summary from credit_history
            summary = get_user_credit_summary(user_id)
            
            if summary:
                transaction_text = (
                    f"📊 **Total Transactions Summary**\n\n"
                    f"📋 **Total transactions:** {summary.total_transactions}\n\n"
                    f"💰 **Total free credits:** {summary.earned_links + summary.earned_welcome:.2f}\n"
                    f"💳 **Total credit buy:** {summary.earned_purchase:.2f}\n"
                    f"👥 **Total referral credit:** {summary.earned_referral:.2f}\n\n"
                    f"💎 **Total credit earn:** {summary.total_earned:.2f}\n"
                    f"📉 **Total credit used:** {summary.total_spent:.2f}\n"
                    f"💰 **Remaining credit:** {user.credits:.2f}\n\n"
                    f"📅 **First transaction:** {summary.first_transaction.strftime('%d/%m/%Y') if summary.first_transaction else 'N/A'}\n"
                    f"🕒 **Last transaction:** {summary.last_transaction.strftime('%d/%m/%Y %H:%M') if summary.last_transaction else 'N/A'}"
                )
            else:
                transaction_text = (
                    f"📊 **Total Transactions Summary**\n\n"
                    f"📋 **Total transactions:** 0\n\n"
                    f"💰 **Total free credits:** 0.00\n"
                    f"💳 **Total credit buy:** 0.00\n"
                    f"👥 **Total referral credit:** 0.00\n\n"
                    f"💎 **Total credit earn:** 0.00\n"
                    f"📉 **Total credit used:** 0.00\n"
                    f"💰 **Remaining credit:** {user.credits:.2f}\n\n"
                    f"🚀 **Start using the bot to see your transaction history!**"
                )
                
            await callback_query.edit_message_text(
                transaction_text,
                reply_markup=get_my_transaction_panel()
            )
            db.close()
            
        except Exception as e:
            print(f"Error in my_transaction handler: {e}")
            await callback_query.edit_message_text(
                "❌ **Error loading transaction summary**\n\nPlease try again later.",
                reply_markup=get_user_credit_panel()
            )

    elif data == "download_transactions":
        try:
            import csv
            import tempfile
            from pyrogram.types import InputMediaDocument
            
            # Get user transactions from credit_history
            db_credit = get_credit_history_db()
            from credit_history import CreditHistory
            
            user_transactions = db_credit.query(CreditHistory).filter(
                CreditHistory.user_id == user_id
            ).order_by(CreditHistory.timestamp.desc()).all()
            
            if not user_transactions:
                await callback_query.edit_message_text(
                    "📄 **Download Transactions**\n\n"
                    "❌ **No transactions found!**\n\n"
                    "aapka koi transaction history nahi hai.\n"
                    "Bot use kare aur फिर try kare.",
                    reply_markup=get_my_transaction_panel()
                )
                db_credit.close()
                return
            
            # Create temporary CSV file
            temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', encoding='utf-8')
            csv_writer = csv.writer(temp_file)
            
            # Write CSV headers
            csv_writer.writerow([
                'Transaction ID', 'Date & Time', 'Amount', 'Type', 'Source', 
                'Description', 'Balance Before', 'Balance After'
            ])
            
            # Write transaction data
            for trans in user_transactions:
                csv_writer.writerow([
                    trans.transaction_id or 'N/A',
                    trans.timestamp.strftime('%d/%m/%Y %H:%M:%S') if trans.timestamp else 'N/A',
                    f"{trans.amount:.2f}",
                    trans.transaction_type or 'N/A',
                    trans.source or 'N/A',
                    trans.description or 'N/A',
                    f"{trans.balance_before:.2f}",
                    f"{trans.balance_after:.2f}"
                ])
            
            temp_file.close()
            
            # Send file to user
            current_time = datetime.now().strftime('%d-%m-%Y_%H-%M')
            filename = f"transactions_{user_id}_{current_time}.csv"
            
            await callback_query.edit_message_text(
                f"📄 **Generating Transaction File...**\n\n"
                f"📊 **Total Transactions:** {len(user_transactions)}\n"
                f"📅 **Generated:** {current_time}\n\n"
                f"⏳ Please wait while we prepare your file..."
            )
            
            # Send the file
            await app.send_document(
                user_id,
                temp_file.name,
                file_name=filename,
                caption=(
                    f"📄 **Your Transaction History**\n\n"
                    f"📊 **Total Records:** {len(user_transactions)}\n"
                    f"📅 **Generated on:** {datetime.now().strftime('%d/%m/%Y at %H:%M')}\n\n"
                    f"📋 **File contains:**\n"
                    f"• Transaction IDs\n"
                    f"• Date & Time stamps\n"
                    f"• Amount details\n"
                    f"• Transaction types & sources\n"
                    f"• Balance information\n\n"
                    f"💡 **Tip:** Open with Excel or Google Sheets for better viewing!"
                )
            )
            
            # Clean up temporary file
            import os
            os.unlink(temp_file.name)
            
            await callback_query.edit_message_text(
                f"✅ **Transaction File Sent!**\n\n"
                f"📁 Check your chat for the CSV file\n"
                f"📊 **Total Records:** {len(user_transactions)}\n\n"
                f"💡 **File Name:** {filename}",
                reply_markup=get_my_transaction_panel()
            )
            
            db_credit.close()
            
        except Exception as e:
            print(f"Error in download_transactions handler: {e}")
            await callback_query.edit_message_text(
                "❌ **Error generating transaction file**\n\n"
                "kuch technical issue hui hai.\n"
                "Kripaya baad me try kare ya admin se contact kare.",
                reply_markup=get_my_transaction_panel()
            )

    elif data == "track_transactions":
        try:
            # Show transactions with pagination (5 per page)
            from credit_history import CreditHistory

            
            db_credit = get_credit_history_db()
            
            # Get total count
            total_transactions = db_credit.query(CreditHistory).filter(
                CreditHistory.user_id == user_id
            ).count()
            
            if total_transactions == 0:
                await callback_query.edit_message_text(
                    "📋 **Track Transactions**\n\n"
                    "❌ **No transactions found!**\n\n"
                    "aapka koi transaction history nahi hai.\n"
                    "Bot use kare aur फिर try kare.",
                    reply_markup=get_my_transaction_panel()
                )
                db_credit.close()
                return
            
            # Set initial page to 1 and store in user_states
            page = 1
            page_size = 5
            offset = (page - 1) * page_size
            total_pages = (total_transactions + page_size - 1) // page_size
            
            user_states[user_id] = {'state': 'tracking_transactions', 'page': page}
            
            # Get transactions for current page
            transactions = db_credit.query(CreditHistory).filter(
                CreditHistory.user_id == user_id
            ).order_by(CreditHistory.timestamp.desc()).offset(offset).limit(page_size).all()
            
            # Build transaction list
            trans_text = f"📋 **Track Transactions** (Page {page}/{total_pages})\n\n"
            
            for i, trans in enumerate(transactions, 1):
                trans_text += (
                    f"**{i + offset}.** **{trans.transaction_type.title()}**\n"
                    f"🆔 ID: `{trans.transaction_id or 'N/A'}`\n"
                    f"💰 Amount: {trans.amount:+.2f} credits\n"
                    f"📝 Source: {trans.source or 'N/A'}\n"
                    f"📅 Date: {trans.timestamp.strftime('%d/%m/%Y %H:%M') if trans.timestamp else 'N/A'}\n"
                    f"💳 Balance: {trans.balance_before:.2f} → {trans.balance_after:.2f}\n"
                    f"─────────────────────\n"
                )
            
            trans_text += f"\n📊 **Total Records:** {total_transactions}"
            
            # Create pagination keyboard
            keyboard = []
            
            # Navigation buttons
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data="track_prev"))
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data="track_next"))
            
            if nav_buttons:
                keyboard.append(nav_buttons)
            
            # Page indicator and back button
            keyboard.append([InlineKeyboardButton(f"📄 Page {page}/{total_pages}", callback_data="track_page_info")])
            keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="my_transaction")])
            
            await callback_query.edit_message_text(
                trans_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            db_credit.close()
            
        except Exception as e:
            print(f"Error in track_transactions handler: {e}")
            await callback_query.edit_message_text(
                "❌ **Error loading transactions**\n\n"
                "kuch technical issue hui hai.\n"
                "Kripaya baad me try kare.",
                reply_markup=get_my_transaction_panel()
            )

    elif data == "track_custom_transaction":
        try:
            # Ask user for transaction ID
            user_states[user_id] = {'state': 'waiting_custom_transaction_id'}
            
            await callback_query.edit_message_text(
                "🔍 **Track Custom Transaction**\n\n"
                "Kripaya Transaction ID enter kare:\n\n"
                "📝 **Example:** 2025123456781234\n"
                "💡 **Note:** Transaction ID must be from your account only\n\n"
                "⚠️ **यदि Transaction ID गलत hai तो error आएगी**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel", callback_data="my_transaction")]
                ])
            )
            
        except Exception as e:
            print(f"Error in track_custom_transaction handler: {e}")
            await callback_query.edit_message_text(
                "❌ **Error in custom transaction tracking**\n\n"
                "kuch technical issue hui hai.",
                reply_markup=get_my_transaction_panel()
            )

    # Pagination handlers for track_transactions
    elif data == "track_prev":
        try:
            if user_id in user_states and user_states[user_id].get('state') == 'tracking_transactions':
                current_page = user_states[user_id].get('page', 1)
                if current_page > 1:
                    new_page = current_page - 1
                    user_states[user_id]['page'] = new_page
                    
                    # Reload transactions for new page
                    from credit_history import CreditHistory
                    
                    db_credit = get_credit_history_db()
                    
                    total_transactions = db_credit.query(CreditHistory).filter(
                        CreditHistory.user_id == user_id
                    ).count()
                    
                    page_size = 5
                    offset = (new_page - 1) * page_size
                    total_pages = (total_transactions + page_size - 1) // page_size
                    
                    transactions = db_credit.query(CreditHistory).filter(
                        CreditHistory.user_id == user_id
                    ).order_by(CreditHistory.timestamp.desc()).offset(offset).limit(page_size).all()
                    
                    # Build transaction list
                    trans_text = f"📋 **Track Transactions** (Page {new_page}/{total_pages})\n\n"
                    
                    for i, trans in enumerate(transactions, 1):
                        trans_text += (
                            f"**{i + offset}.** **{trans.transaction_type.title()}**\n"
                            f"🆔 ID: `{trans.transaction_id or 'N/A'}`\n"
                            f"💰 Amount: {trans.amount:+.2f} credits\n"
                            f"📝 Source: {trans.source or 'N/A'}\n"
                            f"📅 Date: {trans.timestamp.strftime('%d/%m/%Y %H:%M') if trans.timestamp else 'N/A'}\n"
                            f"💳 Balance: {trans.balance_before:.2f} → {trans.balance_after:.2f}\n"
                            f"─────────────────────\n"
                        )
                    
                    trans_text += f"\n📊 **Total Records:** {total_transactions}"
                    
                    # Create pagination keyboard
                    keyboard = []
                    nav_buttons = []
                    if new_page > 1:
                        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data="track_prev"))
                    if new_page < total_pages:
                        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data="track_next"))
                    
                    if nav_buttons:
                        keyboard.append(nav_buttons)
                    
                    keyboard.append([InlineKeyboardButton(f"📄 Page {new_page}/{total_pages}", callback_data="track_page_info")])
                    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="my_transaction")])
                    
                    await callback_query.edit_message_text(
                        trans_text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    
                    db_credit.close()
                    
        except Exception as e:
            print(f"Error in track_prev handler: {e}")
            await callback_query.answer("Error loading previous page", show_alert=True)

    elif data == "track_next":
        try:
            if user_id in user_states and user_states[user_id].get('state') == 'tracking_transactions':
                current_page = user_states[user_id].get('page', 1)
                
                # Get total pages to check if we can go to next page
                from credit_history import CreditHistory
                db_credit = get_credit_history_db()
                total_transactions = db_credit.query(CreditHistory).filter(
                    CreditHistory.user_id == user_id
                ).count()
                page_size = 5
                total_pages = (total_transactions + page_size - 1) // page_size
                
                if current_page < total_pages:
                    new_page = current_page + 1
                    user_states[user_id]['page'] = new_page
                    
                    # Reload transactions for new page
        
                    
                    offset = (new_page - 1) * page_size
                    
                    transactions = db_credit.query(CreditHistory).filter(
                        CreditHistory.user_id == user_id
                    ).order_by(CreditHistory.timestamp.desc()).offset(offset).limit(page_size).all()
                    
                    # Build transaction list
                    trans_text = f"📋 **Track Transactions** (Page {new_page}/{total_pages})\n\n"
                    
                    for i, trans in enumerate(transactions, 1):
                        trans_text += (
                            f"**{i + offset}.** **{trans.transaction_type.title()}**\n"
                            f"🆔 ID: `{trans.transaction_id or 'N/A'}`\n"
                            f"💰 Amount: {trans.amount:+.2f} credits\n"
                            f"📝 Source: {trans.source or 'N/A'}\n"
                            f"📅 Date: {trans.timestamp.strftime('%d/%m/%Y %H:%M') if trans.timestamp else 'N/A'}\n"
                            f"💳 Balance: {trans.balance_before:.2f} → {trans.balance_after:.2f}\n"
                            f"─────────────────────\n"
                        )
                    
                    trans_text += f"\n📊 **Total Records:** {total_transactions}"
                    
                    # Create pagination keyboard
                    keyboard = []
                    nav_buttons = []
                    if new_page > 1:
                        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data="track_prev"))
                    if new_page < total_pages:
                        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data="track_next"))
                    
                    if nav_buttons:
                        keyboard.append(nav_buttons)
                    
                    keyboard.append([InlineKeyboardButton(f"📄 Page {new_page}/{total_pages}", callback_data="track_page_info")])
                    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="my_transaction")])
                    
                    await callback_query.edit_message_text(
                        trans_text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    
                db_credit.close()
                    
        except Exception as e:
            print(f"Error in track_next handler: {e}")
            await callback_query.answer("Error loading next page", show_alert=True)

    elif data == "referral_system":
        # Redirect to the same functionality as free_credit
        try:
            referral_link, referral_code = get_user_referral_link(user_id)

            await callback_query.edit_message_text(
                f"👥 **Your Referral System**\n\n"
                f"🔗 **Your Referral Link:**\n"
                f"`{referral_link}`\n\n"
                f"📤 Share this link with friends to earn credits!\n"
                f"💰 When someone joins using your link, you both get bonus credits.\n\n"
                f"🎁 **Rewards:**\n"
                f"• You get bonus credits for each referral\n"
                f"• Your friends get welcome bonus\n\n"
                f"Use the buttons below to share your link!",
                reply_markup=get_free_credit_referral_panel(referral_link)
            )
        except Exception as error:
            print(f"Error in referral system handler: {error}")
            try:
                await callback_query.edit_message_text(
                    f"👥 **Referral System**\n\n"
                    f"❌ Service temporarily unavailable!\n"
                    f"Kripaya baad me try kare ya admin se contact kare.",
                    reply_markup=get_user_credit_panel()
                )
            except:
                # If editing fails, send new message
                await callback_query.answer("Service temporarily unavailable", show_alert=True)

    elif data == "referral_status":
        try:
            referral_link, referral_code = get_user_referral_link(user_id)
            stats = get_user_referral_stats(user_id)

            # Build recent referrals text
            recent_referrals_text = ""
            if stats['referred_users']:
                recent_referrals_text = "\n\n👥 **Recent Referrals:**\n"
                for i, user_ref in enumerate(stats['referred_users'][:3], 1):
                    recent_referrals_text += f"{i}. {user_ref['name']} - {user_ref['joined_date']} (+{user_ref['credits_earned']:.0f} credits)\n"
                if len(stats['referred_users']) > 3:
                    recent_referrals_text += f"... aur {len(stats['referred_users']) - 3} referrals"
            else:
                recent_referrals_text = "\n\n👥 **Recent Referrals:** None yet"

            await callback_query.edit_message_text(
                f"📊 **Referral Status**\n\n"
                f"🔗 **Your Code:** `{referral_code}`\n"
                f"📈 **Total Referrals:** {stats['successful_referrals']}\n"
                f"💰 **Credits Earned:** {stats['total_referral_credits']:.0f}\n"
                f"🎁 **Per Referral:** 20 credits for you, 15 for friend"
                f"{recent_referrals_text}\n\n"
                f"📤 Share your link to earn more credits!",
                reply_markup=get_free_credit_referral_panel(referral_link)
            )
        except Exception as error:
            print(f"Error in referral status handler: {error}")
            await callback_query.edit_message_text(
                f"📊 **Referral Status**\n\n"
                f"❌ Service temporarily unavailable!",
                reply_markup=get_user_credit_panel()
            )

    elif data.startswith("copy_referral_"):
        referral_code = data.replace("copy_referral_", "")
        bot_username = os.getenv('BOT_USERNAME', 'your_bot_username')
        referral_link = f"https://t.me/{bot_username}?start={referral_code}"

        await callback_query.answer(
            f"✅ Referral link copied!\n{referral_link}",
            show_alert=True
        )

    elif data == "my_referral_stats":
        try:
            referral_link, referral_code = get_user_referral_link(user_id)
            await callback_query.edit_message_text(
                f"📊 **Your Referral Statistics**\n\n"
                f"🔗 **Your Code:** `{referral_code}`\n"
                f"👥 **Status:** Referral system active\n"
                f"💰 **Earnings:** Check with admin for details\n\n"
                f"📤 Share your link to earn credits!",
                reply_markup=get_free_credit_referral_panel(referral_link)
            )
        except Exception as error:
            await callback_query.edit_message_text(
                f"📊 **Referral Statistics**\n\n❌ Service unavailable",
                reply_markup=get_user_credit_panel()
            )

    elif data == "share_referral":
        try:
            referral_link, referral_code = get_user_referral_link(user_id)
            bot_username = os.getenv('BOT_USERNAME', 'your_bot_username')

            await callback_query.edit_message_text(
                f"📤 **Share Your Referral Code**\n\n"
                f"🔗 **Your Code:** `{referral_code}`\n\n"
                f"📱 **Share Message:**\n"
                f"\"🤖 Join this amazing TTS Bot using my referral code!\n\n"
                f"🎁 Use: /start {referral_code}\n"
                f"💰 Get 15 bonus credits instantly!\n\n"
                f"Bot: @{bot_username}\"\n\n"
                f"💡 Copy the code or use share button below:",
                reply_markup=get_free_credit_referral_panel(referral_link)
            )
        except Exception as error:
            await callback_query.edit_message_text(
                f"📤 **Share Referral**\n\n❌ Service unavailable",
                reply_markup=get_user_credit_panel()
            )

    elif data.startswith("copy_referral_"):
        referral_code = data.replace("copy_referral_", "")
        await callback_query.answer(f"Referral code {referral_code} copied! Share it with friends.", show_alert=True)

    elif data == "referral_leaderboard":
        leaderboard_text = "🏆 **Top Referrers**\n\nLeaderboard will be updated soon!"

        await callback_query.edit_message_text(
            leaderboard_text,
            reply_markup=get_free_credit_referral_panel("https://t.me/bot?start=example")
        )

    elif data == "referral_info":
        await callback_query.edit_message_text(
            "ℹ️ **How Referral System Works**\n\n"
            "🎯 **Step 1:** Get your referral code\n"
            "📤 **Step 2:** Share with friends\n"
            "👥 **Step 3:** Friend joins using: /start YOUR_CODE\n"
            "🎁 **Step 4:** Both get bonus credits!\n\n"
            "💰 **Rewards:**\n"
            "• You: 20 credits per referral\n"
            "• Friend: 15 welcome bonus\n\n"
            "📋 **Rules:**\n"
            "• New users only (within 5 minutes)\n"
            "• No self-referrals\n"
            "• No limit on referrals\n\n"
            "🚀 Start earning today!",
            reply_markup=get_referral_panel()
        )

    elif data.startswith("confirm_payment_"):
        payment_id = data.replace("confirm_payment_", "")

        db = SessionLocal()
        try:
            from database import PaymentRequest
            from datetime import datetime
            payment = db.query(PaymentRequest).filter(PaymentRequest.id == int(payment_id)).first()
            if payment and payment.status == 'pending':
                # Confirm payment
                payment.status = 'confirmed'
                payment.verified_at = datetime.utcnow()
                db.commit()

                # Add credits to user
                user = db.query(User).filter(User.user_id == payment.user_id).first()
                if user:
                    user.credits = float(user.credits) + payment.credits_to_add
                    db.commit()

                    # Log credit transaction
                    log_credit_transaction(payment.user_id, payment.credits_to_add, 'purchase', f'Payment confirmed - ₹{payment.amount}')

                # Notify user with detailed confirmation
                try:
                    user_msg = await client.send_message(
                        payment.user_id,
                        f"✅ **Payment Confirmed!**\n\n"
                        f"💳 Amount: ₹{payment.amount}\n"
                        f"💰 Credits Added: {payment.credits_to_add}\n"
                        f"💎 Current Balance: {user.credits:.0f} credits\n"
                        f"🆔 Transaction ID: {payment.transaction_id}\n"
                        f"📅 Verified: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}\n\n"
                        f"🎉 Thank you for your purchase!\n"
                        f"🎆 aap ab TTS ka use kar sakte hai!",
                        reply_markup=get_user_panel()
                    )
                    # Track payment confirmation message for deletion
                    await track_sent_message(
                        user_msg,
                        message_type=MessageType.STATUS,
                        user_id=payment.user_id,
                        custom_delay=20,  # Keep payment confirmation longer
                        context="payment_confirmation"
                    )
                    print(f"✅ Payment confirmation sent to user {payment.user_id}")
                except Exception as notify_error:
                    print(f"⚠️ Error notifying user about payment confirmation: {notify_error}")

                admin_msg = await callback_query.edit_message_text(
                    f"✅ **Payment Confirmed Successfully!**\n\n"
                    f"👤 User ID: {payment.user_id}\n"
                    f"💰 Amount: ₹{payment.amount}\n"
                    f"💎 Credits Added: {payment.credits_to_add}\n"
                    f"🆔 Transaction ID: {payment.transaction_id}\n"
                    f"📅 Processed: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}\n\n"
                    f"✅ User has been notified and credits added!",
                    reply_markup=get_back_to_owner()
                )
                # Track admin confirmation message
                await track_sent_message(
                    admin_msg,
                    message_type=MessageType.ADMIN,
                    user_id=user_id,
                    context="payment_admin"
                )
            else:
                await callback_query.answer("Payment not found or already processed!", show_alert=True)
        finally:
            db.close()

    elif data.startswith("cancel_payment_"):
        payment_id = data.replace("cancel_payment_", "")

        db = SessionLocal()
        try:
            from database import PaymentRequest
            from datetime import datetime
            payment = db.query(PaymentRequest).filter(PaymentRequest.id == int(payment_id)).first()
            if payment and payment.status == 'pending':
                # Cancel payment
                payment.status = 'cancelled'
                payment.verified_at = datetime.utcnow()
                db.commit()

                # Notify user about payment cancellation
                try:
                    await client.send_message(
                        payment.user_id,
                        f"❌ **Payment Request Cancelled**\n\n"
                        f"💳 Amount: ₹{payment.amount}\n"
                        f"🆔 Transaction ID: {payment.transaction_id}\n"
                        f"📅 Cancelled: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}\n\n"
                        f"😔 aapki payment request cancel हो गई hai.\n"
                        f"👤 यदि Aapko लगता hai yah mistake hai तो owner se contact kare.",
                        reply_markup=get_payment_cancel_panel()
                    )
                    print(f"❌ Payment cancellation notification sent to user {payment.user_id}")
                except Exception as notify_error:
                    print(f"⚠️ Error notifying user about payment cancellation: {notify_error}")

                await callback_query.edit_message_text(
                    f"❌ **Payment Cancelled Successfully!**\n\n"
                    f"👤 User ID: {payment.user_id}\n"
                    f"💰 Amount: ₹{payment.amount}\n"
                    f"🆔 Transaction ID: {payment.transaction_id}\n"
                    f"📅 Cancelled: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}\n\n"
                    f"❌ User has been notified about cancellation.",
                    reply_markup=get_back_to_owner()
                )
            else:
                await callback_query.answer("Payment not found or already processed!", show_alert=True)
        finally:
            db.close()
    
    # Transaction History Handlers
    elif data == "transaction_history":
        summary = transaction_manager.get_today_transactions_summary()
        
        await callback_query.edit_message_text(
            f"📊 **Today's Transactions Summary**\n\n"
            f"👥 **Total Users:** {summary['total_users']}\n\n"
            f"🆓 **Free Credit:** {summary['free_credit']['users']} users\n"
            f"   💰 Total: {summary['free_credit']['amount']} credits\n\n"
            f"💳 **Buy Credit:** {summary['buy_credit']['users']} users\n"
            f"   💎 Total: {summary['buy_credit']['amount']} credits\n\n"
            f"👥 **Referral Users:** {summary['referral']['users']} users\n"
            f"   🎁 Total: {summary['referral']['amount']} credits\n\n"
            f"Select time period to export transaction history:",
            reply_markup=get_transaction_history_panel()
        )
    
    elif data == "tx_today":
        from datetime import datetime, timedelta
        import os
        transactions = transaction_manager.get_transactions_by_date_range(
            datetime.combine(datetime.utcnow().date(), datetime.min.time())
        )
        filename = f"transactions_today_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        filepath = transaction_manager.create_transaction_file(transactions, filename)
        
        if filepath and os.path.exists(filepath):
            await callback_query.answer("📄 Generating today's transaction file...", show_alert=True)
            await app.send_document(
                user_id,
                filepath,
                caption=f"📊 **Today's Transaction History**\n"
                       f"📅 Date: {datetime.now().strftime('%d/%m/%Y')}\n"
                       f"📈 Total Records: {len(transactions)}"
            )
        else:
            await callback_query.answer("❌ Error generating transaction file!", show_alert=True)
    
    elif data == "tx_yesterday":
        from datetime import datetime, timedelta
        import os
        transactions = transaction_manager.get_yesterday_transactions()
        filename = f"transactions_yesterday_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        filepath = transaction_manager.create_transaction_file(transactions, filename)
        
        if filepath and os.path.exists(filepath):
            await callback_query.answer("📄 Generating yesterday's transaction file...", show_alert=True)
            await app.send_document(
                user_id,
                filepath,
                caption=f"📊 **Yesterday's Transaction History**\n"
                       f"📅 Date: {(datetime.now().date() - timedelta(days=1)).strftime('%d/%m/%Y')}\n"
                       f"📈 Total Records: {len(transactions)}"
            )
        else:
            await callback_query.answer("❌ Error generating transaction file!", show_alert=True)
    
    elif data == "tx_last_week":
        from datetime import datetime, timedelta
        import os
        transactions = transaction_manager.get_last_week_transactions()
        filename = f"transactions_last_week_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        filepath = transaction_manager.create_transaction_file(transactions, filename)
        
        if filepath and os.path.exists(filepath):
            await callback_query.answer("📄 Generating last week's transaction file...", show_alert=True)
            await app.send_document(
                user_id,
                filepath,
                caption=f"📊 **Last Week's Transaction History**\n"
                       f"📅 Period: Last 7 days\n"
                       f"📈 Total Records: {len(transactions)}"
            )
        else:
            await callback_query.answer("❌ Error generating transaction file!", show_alert=True)
    
    elif data == "tx_last_month":
        from datetime import datetime, timedelta
        import os
        transactions = transaction_manager.get_last_month_transactions()
        filename = f"transactions_last_month_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        filepath = transaction_manager.create_transaction_file(transactions, filename)
        
        if filepath and os.path.exists(filepath):
            await callback_query.answer("📄 Generating last month's transaction file...", show_alert=True)
            await app.send_document(
                user_id,
                filepath,
                caption=f"📊 **Last Month's Transaction History**\n"
                       f"📅 Period: Last 30 days\n"
                       f"📈 Total Records: {len(transactions)}"
            )
        else:
            await callback_query.answer("❌ Error generating transaction file!", show_alert=True)
    
    elif data == "tx_custom":
        user_states[user_id] = {'state': 'waiting_custom_date_1', 'stage': 'first_date'}
        await callback_query.edit_message_text(
            "📅 **Custom Date Range**\n\n"
            "Enter the first date in format:\n"
            "**DD/MM/YYYY** (e.g., 15/01/2025)\n\n"
            "This will be the start date for transaction history.",
            reply_markup=get_custom_date_panel()
        )
    
    elif data == "tx_custom_single":
        if user_id in user_states and user_states[user_id].get('first_date'):
            import os
            first_date = user_states[user_id]['first_date']
            transactions = transaction_manager.get_transactions_by_date_range(first_date)
            filename = f"transactions_custom_{first_date.strftime('%Y%m%d')}_{datetime.now().strftime('%H%M')}.csv"
            filepath = transaction_manager.create_transaction_file(transactions, filename)
            
            if filepath and os.path.exists(filepath):
                await app.send_document(
                    user_id,
                    filepath,
                    caption=f"📊 **Custom Transaction History**\n"
                           f"📅 Date: {first_date.strftime('%d/%m/%Y')}\n"
                           f"📈 Total Records: {len(transactions)}"
                )
            user_states.pop(user_id, None)
        
        await callback_query.edit_message_text(
            "📊 **Transaction History**\n\nSelect time period:",
            reply_markup=get_transaction_history_panel()
        )
    
    elif data == "tx_track_payment":
        user_states[user_id] = {'state': 'waiting_payment_id'}
        await callback_query.edit_message_text(
            "🔍 **Track Payment Request**\n\n"
            "Enter Transaction ID to track:\n"
            "• User provided transaction ID\n"
            "• System generated payment ID (PAYxxxxxxxxxx)\n\n"
            "Example: PAY20250109123456ABCD",
            reply_markup=get_custom_date_panel()
        )
    
    elif data == "tx_all_transactions":
        # Show comprehensive transaction summary
        db = SessionLocal()
        try:
            total_credit_tx = db.query(CreditTransaction).count()
            total_payments = db.query(PaymentRequest).count()
            
            await callback_query.edit_message_text(
                f"📋 **All Transactions Overview**\n\n"
                f"💰 **Credit Transactions:** {total_credit_tx}\n"
                f"💳 **Payment Requests:** {total_payments}\n\n"
                f"🚨 **Note:** Export all transactions may take time.\n"
                f"Use specific date ranges for better performance.\n\n"
                f"Select a specific time period instead:",
                reply_markup=get_transaction_history_panel()
            )
        except Exception as e:
            await callback_query.answer(f"Error: {e}", show_alert=True)
        finally:
            db.close()

    elif data == "contact_support":
        keyboard = [
        [InlineKeyboardButton("👨‍💼 Contact Owner", url="tg://resolve?domain=KissuHQ")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_user")]
    ]
    return InlineKeyboardMarkup(keyboard)
    

    elif data == "i_know_that":
        user = get_user_from_db(user_id)
        await callback_query.edit_message_text(
            f"🌟 **Wellcome** {callback_query.from_user.first_name}! 🌟\n\n"
            f"💎 **aapke Credits:** {user.credits}\n"
            f"🚀 **Ready for TTS Magic?** ✨\n\n"
            f"🎯 नीचे दिए गए options me se choose kare:",
            reply_markup=get_user_panel()
        )

    elif data == "user_help":
        # Get user's current info for personalized help
        user = get_user_from_db(user_id)
        
        await callback_query.edit_message_text(
            f"❓ **Complete Help Guide** ❓\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎤 **TTS Usage Guide:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"1️⃣ 🎤 **Start TTS** button दबाएं\n"
            f"2️⃣ 🎵 अपनी पसंदीदा voice select kare\n"
            f"3️⃣ 📝 Text type kare (max 3000 characters)\n"
            f"4️⃣ 🎧 Audio file receive kare\n"
            f"5️⃣ ⭐ Quality rate kare\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 **Credit Information:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 **Your Current Balance:** {user.credits:.2f}\n"
            f"💸 **Per Word Cost:** 0.05 credits\n"
            f"🎁 **Free Credits:** Referral system\n"
            f"💳 **Buy Credits:** Payment options available\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎵 **Voice Options:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👨 **Male Voices:** Deep, Calm, Professional, Energetic, Warm\n"
            f"👩 **Female Voices:** Sweet, Clear, Soft, Bright, Melodic\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 **Pro Tips:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 Use punctuation for natural pauses\n"
            f"🔹 Break long text into smaller chunks\n"
            f"🔹 Try different voices for best results\n"
            f"🔹 Rate audio quality to help us improve\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 **Available Commands:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 `/start` - Bot ko शुरू kare\n"
            f"❌ `/cancel` - Current operation cancel kare\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆘 **Need Support?**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📞 Contact admin for technical issues\n"
            f"💬 Report bugs or suggestions\n"
            f"🎯 Join our community for updates\n\n"
            f"✨ **Happy TTS-ing!** ✨",
            reply_markup=get_help_section_keyboard()
        )

    elif data == "user_about":
        # Calculate average rating from both real feedback and fake ratings
        db = SessionLocal()
        try:
            from database import Feedback
            from sqlalchemy import func

            # Get real feedback ratings
            real_avg = db.query(func.avg(Feedback.rating)).scalar() or 0
            real_count = db.query(Feedback).count()

            # Get fake ratings
            fake_avg = db.query(func.avg(BotRating.rating)).scalar() or 0
            fake_count = db.query(BotRating).count()

            # Calculate combined rating
            total_count = real_count + fake_count
            if total_count > 0:
                combined_avg = ((real_avg * real_count) + (fake_avg * fake_count)) / total_count
                rating_text = f"⭐ **User Rating:** {combined_avg:.1f}/5 ({total_count} reviews)\n"
            else:
                rating_text = ""
        except:
            rating_text = ""
        finally:
            db.close()

        await callback_query.edit_message_text(
            "ℹ️  About TTS Bot  ℹ️\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🤖  Next-Gen Text-to-Speech Bot\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎯 Mission: Aapke words ko natural, clear & human-like voice me badalna 🎤\n\n"
            "✨ Key Features:\n"
            "🎙️  20+ Hindi & English voice styles  \n"
            "⚡  Ultra-fast conversion speed  \n"
            "🎶  Studio-quality audio output  \n"
            "👥  Invite friends & earn rewards  \n"
            "💳  Premium system pro users ke liye  \n\n"
            "🔧 Technology: Microsoft Edge TTS  \n"
            "🚀 Version: 1.0.0 (Pro Upgrade)  \n\n"
            f"{rating_text}\n"
            "👑 Owner & Developer: ＰＲΞΞＴ ＢＯＰＣＨΞ  \n"
            "      📌 Username: @KissuHQ  \n\n"
            "✨ Text bolega – aapki awaaz me ✨",
            reply_markup=get_user_about_keyboard()
        )

    elif data == "owner_details":
        await callback_query.edit_message_text(
            "👑 **Owner Information** 👑\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "✨ **प्रीत बोपचे** ✨\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎯 **Position:** Bot Owner & Manager\n"
            "💼 **Experience:** Advanced Bot Development\n"
            "🌟 **Specialty:** TTS Solutions & User Experience\n\n"
            "📞 **Contact:**\n"
            "▪️ Direct Message: @PR_GAMING_25\n"
            "▪️ For Support: Use Contact Support button\n"
            "▪️ Business Inquiries: Available 24/7\n\n"
            "🎨 **Vision:** \n"
            "Making text-to-speech accessible and \n"
            "enjoyable for everyone with cutting-edge technology.\n\n"
            "💡 **Fun Fact:** \n"
            "Always working to improve your TTS experience! 🚀",
            reply_markup=get_owner_details_keyboard()
        )

    elif data == "contact_support":
        # Set user state to wait for support message
        user_states[user_id] = {'state': 'waiting_support_message'}
        
        await callback_query.edit_message_text(
            "🆘 **Contact Support** 🆘\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "**Kripaya अपना issue बताएं**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📝 **aap kya problem face kar रहे hai?**\n\n"
            "🔧 **aap लिख sakte hai:**\n"
            "▪️ Technical Issues (App crashes, features not working)\n"
            "▪️ Payment Problems (Credits not added, payment failed)\n"
            "▪️ TTS Issues (Voice not working, poor quality)\n"
            "▪️ Account Problems (Login issues, banned account)\n"
            "▪️ Feature Requests (New features you want)\n"
            "▪️ Any other problems\n\n"
            "💡 **Tip:** Please describe your issue in detail so we can help you better!\n\n"
            "⏳ **Type your message below...**",
            reply_markup=get_contact_support_keyboard()
        )

    # Feedback callbacks
    elif data.startswith("feedback_"):
        if data == "feedback_back":
            # Back to voice selection
            await callback_query.edit_message_text(
                "🎤 **Voice Selection**\n\n"
                "Kripaya apni pasandida voice select karo:",
                reply_markup=get_voice_selection() if user_id != OWNER_ID else get_voice_selection_owner()
            )
        else:
            # Handle rating feedback
            rating = int(data.split("_")[1])

            # Store feedback in database
            db = SessionLocal()
            try:
                from database import Feedback
                feedback = Feedback(
                    user_id=user_id,
                    rating=rating
                )
                db.add(feedback)
                db.commit()

                await callback_query.answer(f"Dhanyawad! aapki {rating}⭐ rating मिल गई.", show_alert=True)

                # Redirect to voice selection
                await callback_query.edit_message_text(
                    "🎤 **Voice Selection**\n\n"
                    "Kripaya apni pasandida voice select karo:",
                    reply_markup=get_voice_selection() if user_id != OWNER_ID else get_voice_selection_owner()
                )
            except Exception as e:
                print(f"Feedback storage error: {e}")
                await callback_query.answer("Dhanyawad! aapki feedback मिल गई.", show_alert=True)
                await callback_query.edit_message_text(
                    "🎤 **Voice Selection**\n\n"
                    "Kripaya apni pasandida voice select karo:",
                    reply_markup=get_voice_selection() if user_id != OWNER_ID else get_voice_selection_owner()
                )
            finally:
                db.close()

    # Language selection callbacks
    elif data.startswith("tts_lang_"):
        lang = data.replace("tts_lang_", "")
        user_states[user_id] = {'state': UserState.WAITING_TTS_TEXT, 'lang': lang, 'voice': 'male1'}

        lang_names = {'hi': 'Hindi', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German'}

        if user_id == OWNER_ID:
            await callback_query.edit_message_text(
                f"🎤 **Owner TTS - {lang_names.get(lang, 'Unknown')}**\n\n"
                "Kripaya अपना text bheje (Maximum 3000 characters):\n\n"
                "⭐ **Owner:** Free unlimited access",
                reply_markup=get_back_to_owner()
            )
        else:
            await callback_query.edit_message_text(
                f"🎤 **TTS - {lang_names.get(lang, 'Unknown')}**\n\n"
                "Kripaya अपना text bheje (Maximum 3000 characters):\n\n"
                "💰 **Charges:** 0.05 credits per word",
                reply_markup=get_back_to_user()
            )

    # New Owner Panel Features
    elif data == "give_credit":
        user_states[user_id] = UserState.WAITING_GIVE_CREDIT_USER_ID
        await callback_query.edit_message_text(
            "💰 **Give Credit to User**\n\n"
            "Kripaya user ID enter kare:",
            reply_markup=get_back_to_owner()
        )

    elif data == "give_credit_all":
        user_states[user_id] = UserState.WAITING_GIVE_CREDIT_ALL_AMOUNT
        await callback_query.edit_message_text(
            "💰 **Give Credit to All Users**\n\n"
            "Kripaya credit amount enter kare जो sabhi users ko देना hai:",
            reply_markup=get_back_to_owner()
        )

    elif data == "ban_user":
        user_states[user_id] = UserState.WAITING_BAN_USER_ID
        await callback_query.edit_message_text(
            "🚫 **Ban User**\n\n"
            "Kripaya user ID enter kare jishe ban karna hai:",
            reply_markup=get_back_to_owner()
        )

    elif data == "unban_user":
        user_states[user_id] = UserState.WAITING_UNBAN_USER_ID
        await callback_query.edit_message_text(
            "✅ **Unban User**\n\n"
            "Kripaya user ID enter kare jishe unban karna hai:",
            reply_markup=get_back_to_owner()
        )

    elif data == "user_specific_info":
        user_states[user_id] = UserState.WAITING_USER_INFO_ID
        await callback_query.edit_message_text(
            "🔍 **Get User Info**\n\n"
            "Kripaya User ID ya Username enter kare:\n\n"
            "Example: 123456789 ya @username",
            reply_markup=get_back_to_owner()
        )

    elif data == "shortner_info":
        db = SessionLocal()
        try:
            shortner = db.query(LinkShortner).filter(LinkShortner.is_active == True).first()
            if shortner:
                await callback_query.edit_message_text(
                    f"🔗 **Link Shortner Info**\n\n"
                    f"🌐 **Domain:** {shortner.domain}\n"
                    f"🔑 **API Key:** {shortner.api_key}\n"
                    f"📅 **Added:** {shortner.created_at.strftime('%d/%m/%Y')}\n"
                    f"✅ **Status:** Active",
                    reply_markup=get_shortner_info_panel()
                )
            else:
                await callback_query.edit_message_text(
                    "❌ koi link shortner nahi मिला.",
                    reply_markup=get_back_to_owner()
                )
        finally:
            db.close()

    elif data == "add_shortner":
        user_states[user_id] = UserState.WAITING_SHORTNER_DOMAIN
        await callback_query.edit_message_text(
            "➕ **Add Link Shortner**\n\n"
            "Kripaya domain name enter kare (जैse: short.ly):",
            reply_markup=get_back_to_owner()
        )

    elif data == "remove_shortner":
        db = SessionLocal()
        try:
            shortner = db.query(LinkShortner).filter(LinkShortner.is_active == True).first()
            if shortner:
                shortner.is_active = False
                db.commit()
                await callback_query.edit_message_text(
                    "✅ **Link Shortner Removed!**\n\n"
                    f"Domain {shortner.domain} ko successfully remove kar दिya गya.",
                    reply_markup=get_back_to_owner()
                )
            else:
                await callback_query.edit_message_text(
                    "❌ koi active link shortner nahi मिला.",
                    reply_markup=get_back_to_owner()
                )
        finally:
            db.close()

    # Settings panel callbacks
    elif data == "settings_welcome_credit":
        current_welcome_credit = get_setting("welcome_credit", default=10.0)
        await callback_query.edit_message_text(
            f"⚙️ **Welcome Credit Settings**\n\n"
            f"वर्तमान me naye users ko **{current_welcome_credit}** credits मिलते hai.\n\n"
            "naye credit amount enter kare:",
            reply_markup=get_settings_confirmation_panel("welcome_credit")
        )
        user_states[user_id] = UserState.WAITING_WELCOME_CREDIT

    elif data == "settings_tts_charge":
        current_tts_charge = get_setting("tts_charge", default=0.05)
        await callback_query.edit_message_text(
            f"⚙️ **TTS Charge Settings**\n\n"
            f"वर्तमान me प्रति word **{current_tts_charge}** credits charge होते hai.\n\n"
            "naya charge amount enter kare (प्रति word):",
            reply_markup=get_settings_confirmation_panel("tts_charge")
        )
        user_states[user_id] = UserState.WAITING_TTS_CHARGE

    elif data == "settings_earn_credit":
        current_earn_credit = get_setting("earn_credit", default=0.01)
        await callback_query.edit_message_text(
            f"⚙️ **Earn Credit Settings**\n\n"
            f"वर्तमान me short link process karne par **{current_earn_credit}** credits मिलते hai.\n\n"
            "naya earn amount enter kare:",
            reply_markup=get_settings_confirmation_panel("earn_credit")
        )
        user_states[user_id] = UserState.WAITING_EARN_CREDIT

    elif data == "settings_link_timeout":
        current_timeout = get_setting("link_timeout_minutes", default=10.0)
        await callback_query.edit_message_text(
            f"⏱️ **Link Timeout Settings**\n\n"
            f"वर्तमान me links **{current_timeout} minutes** तक valid रहते hai.\n\n"
            "naya timeout duration enter kare (minutes me):",
            reply_markup=get_settings_confirmation_panel("link_timeout")
        )
        user_states[user_id] = UserState.WAITING_LINK_TIMEOUT

    elif data == "settings_free_credit":
        current_free_credit = get_setting("free_credit_per_link", default=10.0)
        await callback_query.edit_message_text(
            f"🆓 **Free Credit Settings**\n\n"
            f"वर्तमान me प्रति link **{current_free_credit}** credits मिलते hai.\n\n"
            "naya credit amount enter kare (per link):",
            reply_markup=get_settings_confirmation_panel("free_credit")
        )
        user_states[user_id] = UserState.WAITING_FREE_CREDIT

    elif data == "settings_buy_credit":
        current_buy_rate = get_setting("payment_rate", default=10.0)
        await callback_query.edit_message_text(
            f"💳 **Buy Credit Settings**\n\n"
            f"वर्तमान me **₹1 = {current_buy_rate} credits** ki rate hai.\n\n"
            "naya credit rate enter kare (per ₹1):",
            reply_markup=get_settings_confirmation_panel("buy_credit")
        )
        user_states[user_id] = UserState.WAITING_BUY_CREDIT_RATE

    elif data == "settings_referral":
        referred_user_credit = get_setting("referral_bonus_new_user", default=5.0)
        referrer_credit = get_setting("referral_bonus_referrer", default=5.0)
        await callback_query.edit_message_text(
            f"👥 **Referral Settings**\n\n"
            f"**Referred User ko:** {referred_user_credit} credits\n"
            f"**Referrer ko:** {referrer_credit} credits\n\n"
            "कौन सी setting change karna चाहते hai?",
            reply_markup=get_referral_settings_panel()
        )
        user_states[user_id] = UserState.WAITING_REFERRAL_SETTING

    elif data == "settings_payment":
        min_amount = get_setting("min_payment_amount", default=10.0)
        max_amount = get_setting("max_payment_amount", default=100.0)
        payment_rate = get_setting("payment_rate", default=10.0)

        await callback_query.edit_message_text(
            f"💳 **Payment Settings**\n\n"
            f"💰 **Minimum Amount:** ₹{min_amount}\n"
            f"💰 **Maximum Amount:** ₹{max_amount}\n"
            f"💎 **Credit Rate:** {payment_rate} credits per ₹1\n\n"
            "कौन सी setting change karna चाहते hai?",
            reply_markup=get_payment_settings_panel()
        )

    elif data == "settings_min_payment":
        current_min = get_setting("min_payment_amount", default=10.0)
        await callback_query.edit_message_text(
            f"⚙️ **Minimum Payment Amount**\n\n"
            f"वर्तमान minimum amount: **₹{current_min}**\n\n"
            "naya minimum amount enter kare (rupees me):",
            reply_markup=get_settings_confirmation_panel("min_payment")
        )
        user_states[user_id] = UserState.WAITING_MIN_PAYMENT

    elif data == "settings_max_payment":
        current_max = get_setting("max_payment_amount", default=100.0)
        await callback_query.edit_message_text(
            f"⚙️ **Maximum Payment Amount**\n\n"
            f"वर्तमान maximum amount: **₹{current_max}**\n\n"
            "naya maximum amount enter kare (rupees me):",
            reply_markup=get_settings_confirmation_panel("max_payment")
        )
        user_states[user_id] = UserState.WAITING_MAX_PAYMENT

    elif data == "settings_payment_rate":
        current_rate = get_setting("payment_rate", default=10.0)
        await callback_query.edit_message_text(
            f"⚙️ **Payment Credit Rate**\n\n"
            f"वर्तमान rate: **{current_rate} credits per ₹1**\n\n"
            "naya credit rate enter kare (per rupee):",
            reply_markup=get_settings_confirmation_panel("payment_rate")
        )
        user_states[user_id] = UserState.WAITING_PAYMENT_RATE

    # QR Code Settings Callbacks
    elif data == "settings_qr_code":
        await callback_query.edit_message_text(
            "🖼️ **QR Code Settings**\n\n"
            "yahan aap QR code aur payment details manage kar sakte hai:",
            reply_markup=get_qr_management_panel() # QR code management panel
        )

    elif data == "update_qr_code_url":
        user_states[user_id] = UserState.WAITING_QR_CODE_URL
        await callback_query.edit_message_text(
            "🖼️ **Update QR Code URL**\n\n"
            "Kripaya QR code ka URL enter kare:",
            reply_markup=get_back_to_owner()
        )

    elif data == "update_payment_details":
        user_states[user_id] = UserState.WAITING_PAYMENT_NUMBER
        await callback_query.edit_message_text(
            "📱 **Update Payment Details**\n\n"
            "Kripaya payment number (UPI ID or phone number) enter kare:",
            reply_markup=get_back_to_owner()
        )

    elif data == "view_qr_code":
        db = SessionLocal()
        try:
            qr_settings = db.query(QRCodeSettings).filter(QRCodeSettings.is_active == True).first()
            if qr_settings:
                await callback_query.edit_message_text(
                    f"🖼️ **Current QR Code & Payment Details**\n\n"
                    f"🌐 **QR Code URL:** {qr_settings.qr_code_url}\n"
                    f"📱 **Payment Number:** {qr_settings.payment_number}\n"
                    f"👤 **Payment Name:** {qr_settings.payment_name}",
                    reply_markup=get_back_to_owner()
                )
            else:
                await callback_query.edit_message_text(
                    "❌ **No QR Code or Payment Details Found!**\n\n"
                    "Kripaya पहले settings me jakar QR code aur payment details set kare.",
                    reply_markup=get_back_to_owner()
                )
        finally:
            db.close()

    elif data == "change_qr_code":
        # Check if user is owner
        if user_id != OWNER_ID:
            await callback_query.answer("❌ Access denied! Owner only.", show_alert=True)
            return
            
        user_states[user_id] = UserState.WAITING_QR_CODE_FILE
        await callback_query.edit_message_text(
            "🖼️ **Change QR Code**\n\n"
            "Kripaya QR code image bheje (photo upload kare):",
            reply_markup=get_back_to_owner()
        )

    elif data == "change_upi_id":
        # Check if user is owner
        if user_id != OWNER_ID:
            await callback_query.answer("❌ Access denied! Owner only.", show_alert=True)
            return
            
        user_states[user_id] = UserState.WAITING_UPI_ID_ONLY
        await callback_query.edit_message_text(
            "📱 **Change UPI/No. ID**\n\n"
            "Kripaya new UPI ID ya phone number enter kare:",
            reply_markup=get_back_to_owner()
        )

    elif data == "add_qr_upi":
        # Check if user is owner
        if user_id != OWNER_ID:
            await callback_query.answer("❌ Access denied! Owner only.", show_alert=True)
            return
            
        user_states[user_id] = UserState.WAITING_QR_UPI_SETUP
        await callback_query.edit_message_text(
            "➕ **Add QR & UPI ID**\n\n"
            "Pehle UPI ID enter kare:",
            reply_markup=get_back_to_owner()
        )


@app.on_message(filters.text & ~filters.command(["start", "/cancel"])) # Added /cancel command
async def handle_text(client: Client, message: Message):
    """Handle text messages based on user state"""
    user_id = message.from_user.id

    if user_id not in user_states:
        return

    user_state_data = user_states.get(user_id, {})

    if isinstance(user_state_data, dict) and user_state_data.get('state') == UserState.WAITING_TTS_TEXT:
        # Handle TTS request
        try:
            text = message.text.strip()
            voice_type = user_state_data.get('voice', 'male1')

            # Check text length
            if len(text) > 3000:
                await message.reply("❌ Text bahut lamba hai! Maximum 3000 characters allowed hai.")
                user_states.pop(user_id, None)
                return

            if len(text) == 0:
                await message.reply("❌ Kripaya kuch text send karo jo speech me convert karna hai.")
                user_states.pop(user_id, None)
                return

            # Calculate cost based on word count
            word_count = len(text.split())
            credits_needed = word_count * 0.05

            # Check user credits (only for non-owners)
            if user_id != OWNER_ID:
                user = get_user_from_db(user_id)
                if user.credits < credits_needed:
                    error_msg = await message.reply(f"❌ Credits kam hai! Aapko {credits_needed:.2f} credits chahiye lekin aapke paas {user.credits:.2f} hai")
                    # Track error message for quick deletion
                    await track_sent_message(
                        error_msg,
                        message_type=MessageType.ERROR,
                        user_id=user_id,
                        context="tts_error"
                    )
                    user_states.pop(user_id, None)
                    return

                # Show processing message
                processing_msg = await message.reply(f"🔄 Aapka request process ho raha hai...\n💰 Cost: {credits_needed:.2f} credits ({word_count} words)")
                # Track processing message - will be removed after TTS is sent
                await track_sent_message(
                    processing_msg,
                    message_type=MessageType.STATUS,
                    user_id=user_id,
                    custom_delay=8,  # Quick removal after processing
                    context="tts_processing"
                )
            else:
                # Owner gets free access
                processing_msg = await message.reply(f"🔄 Aapka request process ho raha hai...\n⭐ Owner: Free unlimited access")
                # Track owner processing message
                await track_sent_message(
                    processing_msg,
                    message_type=MessageType.STATUS,
                    user_id=user_id,
                    custom_delay=8,
                    context="tts_processing"
                )

            # Generate TTS with selected voice and language
            voice_type = user_state_data.get('voice', 'male1')
            lang = user_state_data.get('lang', 'hi')

            # Use voice-specific TTS if voice is selected, otherwise use language-based
            if voice_type and voice_type != 'male1':
                audio_data = await tts_service.text_to_speech_with_voice(text, voice_type)
            else:
                audio_data = await tts_service.text_to_speech(text, lang)

            if audio_data:
                # Reset buffer position and add name attribute
                audio_data.seek(0)
                audio_data.name = "tts_audio.mp3"

                # Send audio file
                audio_msg = await message.reply_audio(
                    audio_data,
                    caption=f"🎤 **Text:** {text[:50]}{'...' if len(text) > 50 else ''}\n🌐 **Language:** {lang.upper()}\n{'💰 **Cost:** ' + str(credits_needed) + ' credits' if user_id != OWNER_ID else '⭐ **Owner Access**'}",
                    title="TTS Audio"
                )
                # Track TTS audio result - keep longer for user to download
                await track_sent_message(
                    audio_msg,
                    message_type=MessageType.TTS_RESULT,
                    user_id=user_id,
                    custom_delay=120,  # Keep for 2 minutes
                    context="tts_result"
                )

                # Wait 2 seconds then show feedback buttons
                await asyncio.sleep(2)

    
                feedback_keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("1⭐", callback_data="feedback_1"),
                        InlineKeyboardButton("2⭐", callback_data="feedback_2"),
                        InlineKeyboardButton("3⭐", callback_data="feedback_3"),
                        InlineKeyboardButton("4⭐", callback_data="feedback_4"),
                        InlineKeyboardButton("5⭐", callback_data="feedback_5")
                    ],
                    [InlineKeyboardButton("Back", callback_data="feedback_back")]
                ])

                feedback_msg = await message.reply("⭐ **Rate this audio quality:**", reply_markup=feedback_keyboard)
                # Track feedback prompt - delete when user responds or times out
                await track_sent_message(
                    feedback_msg,
                    message_type=MessageType.PROMPT,
                    user_id=user_id,
                    custom_delay=45,  # Give time to rate
                    context="tts_feedback"
                )

                # Deduct credits and log request (only for non-owners)
                if user_id != OWNER_ID:
                    db = SessionLocal()
                    try:
                        user = db.query(User).filter(User.user_id == user_id).first()
                        if user:
                            user.credits = float(user.credits) - credits_needed
                            db.commit()
                            db.refresh(user)

                        # Log request
                        tts_request = TTSRequest(
                            user_id=user_id,
                            text=text,
                            language='hi',
                            credits_used=credits_needed
                        )
                        db.add(tts_request)
                        db.commit()

                        await processing_msg.edit_text(
                            f"✅ **Success!**\n"
                            f"💰 Remaining Credits: {user.credits:.2f}"
                        )
                    except Exception as db_error:
                        print(f"Database error: {db_error}")
                        await processing_msg.edit_text("✅ Audio generated successfully!")
                    finally:
                        db.close()
                else:
                    await processing_msg.edit_text("✅ **Success!** (Owner - Free)")
            else:
                await processing_msg.edit_text("❌ Error generating audio. Please try again.")

        except Exception as e:
            print(f"TTS processing error: {e}")
            await message.reply(f"❌ Error processing your request. Please try again.")

        # Reset user state
        user_states.pop(user_id, None)

    # Handle owner panel states
    elif user_state_data == UserState.WAITING_GIVE_CREDIT_USER_ID and user_id == OWNER_ID:
        try:
            target_user_id = int(message.text.strip())
            user_states[user_id] = {'state': UserState.WAITING_GIVE_CREDIT_AMOUNT, 'target_user': target_user_id}
            await message.reply(f"💰 User ID: {target_user_id}\n\nKripaya credit amount enter kare:")
        except ValueError:
            await message.reply("❌ Invalid user ID! Kripaya valid number enter kare.")
            user_states.pop(user_id, None)

    elif isinstance(user_state_data, dict) and user_state_data.get('state') == UserState.WAITING_GIVE_CREDIT_AMOUNT and user_id == OWNER_ID:
        try:
            credit_amount = float(message.text.strip())
            target_user_id = user_state_data.get('target_user')

            db = SessionLocal()
            try:
                user = db.query(User).filter(User.user_id == target_user_id).first()
                if user:
                    user.credits = float(user.credits) + credit_amount
                    db.commit()
                    await message.reply(f"✅ Successfully added {credit_amount} credits to user {target_user_id}!\n\nNew balance: {user.credits}")
                else:
                    await message.reply(f"❌ User {target_user_id} not found in database.")
            finally:
                db.close()
        except ValueError:
            await message.reply("❌ Invalid amount! Kripaya valid number enter kare.")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_GIVE_CREDIT_ALL_AMOUNT and user_id == OWNER_ID:
        try:
            credit_amount = float(message.text.strip())

            db = SessionLocal()
            try:
                users = db.query(User).all()
                updated_count = 0
                for user in users:
                    user.credits = float(user.credits) + credit_amount
                    updated_count += 1
                db.commit()
                await message.reply(f"✅ Successfully added {credit_amount} credits to {updated_count} users!")
            finally:
                db.close()
        except ValueError:
            await message.reply("❌ Invalid amount! Kripaya valid number enter kare.")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_BAN_USER_ID and user_id == OWNER_ID:
        try:
            target_user_id = int(message.text.strip())

            db = SessionLocal()
            try:
                user = db.query(User).filter(User.user_id == target_user_id).first()
                if user:
                    user.is_banned = True
                    db.commit()
                    await message.reply(f"✅ Successfully banned user {target_user_id}!")
                else:
                    await message.reply(f"❌ User {target_user_id} not found in database.")
            finally:
                db.close()
        except ValueError:
            await message.reply("❌ Invalid user ID! Kripaya valid number enter kare.")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_UNBAN_USER_ID and user_id == OWNER_ID:
        try:
            target_user_id = int(message.text.strip())

            db = SessionLocal()
            try:
                user = db.query(User).filter(User.user_id == target_user_id).first()
                if user:
                    user.is_banned = False
                    db.commit()
                    await message.reply(f"✅ Successfully unbanned user {target_user_id}!")
                else:
                    await message.reply(f"❌ User {target_user_id} not found in database.")
            finally:
                db.close()
        except ValueError:
            await message.reply("❌ Invalid user ID! Kripaya valid number enter kare.")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_SHORTNER_DOMAIN and user_id == OWNER_ID:
        domain = message.text.strip()
        user_states[user_id] = {'state': UserState.WAITING_SHORTNER_API, 'domain': domain}
        await message.reply(f"🌐 Domain: {domain}\n\nKripaya API key enter kare:")

    elif isinstance(user_state_data, dict) and user_state_data.get('state') == UserState.WAITING_SHORTNER_API and user_id == OWNER_ID:
        api_key = message.text.strip()
        domain = user_state_data.get('domain')

        db = SessionLocal()
        try:
            # Deactivate existing shortners
            db.query(LinkShortner).update({LinkShortner.is_active: False})

            # Add new shortner
            new_shortner = LinkShortner(
                domain=domain,
                api_key=api_key,
                is_active=True
            )
            db.add(new_shortner)
            db.commit()

            await message.reply(f"✅ Link shortner successfully added!\n\n🌐 Domain: {domain}\n🔑 API Key: {api_key}\n✅ Shortener configured successfully!")
        finally:
            db.close()
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_BROADCAST_TEXT and user_id == OWNER_ID:
        # Handle broadcast message with placeholders
        broadcast_text = message.text

        db = SessionLocal()
        try:
            users = db.query(User).filter(User.is_active.is_(True), User.is_banned.is_(False)).all()

            sent_count = 0
            failed_count = 0

            for user in users:
                try:
                    # Replace placeholders with actual user data
                    personalized_message = broadcast_text.replace("{user_id}", str(user.user_id))
                    personalized_message = personalized_message.replace("{first_name}", user.first_name or "User")
                    personalized_message = personalized_message.replace("{last_name}", user.last_name or "")
                    personalized_message = personalized_message.replace("{username}", f"@{user.username}" if user.username else "No Username")
                    personalized_message = personalized_message.replace("{credits}", str(user.credits))
                    personalized_message = personalized_message.replace("{join_date}", user.join_date.strftime('%d/%m/%Y'))

                    # Count TTS requests for this user
                    user_requests = db.query(TTSRequest).filter(TTSRequest.user_id == user.user_id).count()
                    personalized_message = personalized_message.replace("{tts_count}", str(user_requests))

                    await client.send_message(int(user.user_id), personalized_message)
                    sent_count += 1
                    await asyncio.sleep(0.1)  # Rate limiting
                except Exception as e:
                    failed_count += 1
                    print(f"Failed to send to {user.user_id}: {e}")

            # Show result with back button

            result_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Owner Panel", callback_data="back_to_owner")]
            ])

            await message.reply(
                f"📢 **Broadcast Complete!**\n\n"
                f"✅ Sent: {sent_count}\n"
                f"❌ Failed: {failed_count}",
                reply_markup=result_keyboard
            )
        finally:
            db.close()

        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_USER_INFO_ID and user_id == OWNER_ID:
        # Handle user info lookup
        user_input = message.text.strip()

        db = SessionLocal()
        try:
            target_user = None

            # Try to parse as user ID first
            try:
                target_user_id = int(user_input)
                target_user = db.query(User).filter(User.user_id == target_user_id).first()
            except ValueError:
                # If not a number, try as username
                if user_input.startswith('@'):
                    username = user_input[1:]  # Remove @ symbol
                else:
                    username = user_input
                target_user = db.query(User).filter(User.username == username).first()

            if target_user:
                # Get user's TTS request count and total credits used
                user_requests = db.query(TTSRequest).filter(TTSRequest.user_id == target_user.user_id).count()
                from sqlalchemy import func
                total_credits_used = db.query(func.sum(TTSRequest.credits_used)).filter(TTSRequest.user_id == target_user.user_id).scalar() or 0

                # Get last TTS request date
                last_request = db.query(TTSRequest).filter(TTSRequest.user_id == target_user.user_id).order_by(TTSRequest.timestamp.desc()).first()
                last_request_date = last_request.timestamp.strftime('%d/%m/%Y %H:%M') if last_request else "Never"

                # Calculate days since joining
                from datetime import datetime
                days_since_join = (datetime.utcnow() - target_user.join_date).days

                # Get detailed credit transaction history
                credit_transactions = db.query(CreditTransaction).filter(CreditTransaction.user_id == target_user.user_id).order_by(CreditTransaction.timestamp.desc()).limit(5).all()

                # Calculate total credits earned vs spent
                total_credits_earned = db.query(func.sum(CreditTransaction.amount)).filter(
                    CreditTransaction.user_id == target_user.user_id,
                    CreditTransaction.amount > 0
                ).scalar() or 0

                total_credits_spent = abs(db.query(func.sum(CreditTransaction.amount)).filter(
                    CreditTransaction.user_id == target_user.user_id,
                    CreditTransaction.amount < 0
                ).scalar() or 0)

                # Get referral info
                referrals_made = db.query(ReferralSystem).filter(ReferralSystem.referrer_id == target_user.user_id).count()
                referral_credits_earned = db.query(func.sum(ReferralSystem.credits_earned)).filter(ReferralSystem.referrer_id == target_user.user_id).scalar() or 0

                # Last credit transaction
                last_credit_transaction = db.query(CreditTransaction).filter(CreditTransaction.user_id == target_user.user_id).order_by(CreditTransaction.timestamp.desc()).first()
                last_credit_info = f"{last_credit_transaction.timestamp.strftime('%d/%m/%Y %H:%M')} - {last_credit_transaction.transaction_type} ({last_credit_transaction.amount:+.2f})" if last_credit_transaction else "No transactions"

                # Build transaction history text
                transaction_history = ""
                if credit_transactions:
                    transaction_history = "\n📋 **Recent Transactions:**\n"
                    for i, trans in enumerate(credit_transactions[:3], 1):
                        transaction_history += f"{i}. {trans.timestamp.strftime('%d/%m %H:%M')} - {trans.transaction_type} ({trans.amount:+.2f})\n"

                user_info_text = (
                    f"👤 **Complete User Information**\n\n"
                    f"🆔 **User ID:** {target_user.user_id}\n"
                    f"📝 **Name:** {target_user.first_name or 'N/A'} {target_user.last_name or ''}\n"
                    f"👤 **Username:** @{target_user.username or 'None'}\n"
                    f"📅 **Join Date:** {target_user.join_date.strftime('%d/%m/%Y %H:%M')}\n"
                    f"📈 **Days Since Join:** {days_since_join}\n"
                    f"🕐 **Last Active:** {target_user.last_active.strftime('%d/%m/%Y %H:%M')}\n\n"
                    f"💰 **Credit Information:**\n"
                    f"💳 **Current Balance:** {target_user.credits:.2f}\n"
                    f"📈 **Total Earned:** {total_credits_earned:.2f}\n"
                    f"📉 **Total Spent:** {total_credits_spent:.2f}\n"
                    f"🕒 **Last Transaction:** {last_credit_info}\n"
                    f"{transaction_history}\n"
                    f"🎤 **TTS Stats:**\n"
                    f"📊 **Total Requests:** {user_requests}\n"
                    f"💸 **TTS Credits Used:** {total_credits_used:.2f}\n"
                    f"🕒 **Last TTS Request:** {last_request_date}\n\n"
                    f"👥 **Referral Stats:**\n"
                    f"📊 **Referrals Made:** {referrals_made}\n"
                    f"💰 **Referral Credits:** {referral_credits_earned:.2f}\n\n"
                    f"📊 **Account Status:**\n"
                    f"✅ **Active:** {'Yes' if target_user.is_active else 'No'}\n"
                    f"🚫 **Banned:** {'Yes' if target_user.is_banned else 'No'}"
                )

                await message.reply(user_info_text, reply_markup=get_back_to_owner())
            else:
                await message.reply(
                    f"❌ **User Not Found!**\n\n"
                    f"User ID ya Username '{user_input}' database me nahi मिला.\n\n"
                    f"Kripaya valid User ID ya Username enter kare.",
                    reply_markup=get_back_to_owner()
                )
        finally:
            db.close()

        user_states.pop(user_id, None)

    # Settings state handlers
    elif user_state_data == UserState.WAITING_WELCOME_CREDIT and user_id == OWNER_ID:
        try:
            credit_amount = float(message.text.strip())
            if credit_amount < 0:
                await message.reply("❌ Credit amount nahi हो सकती negative!")
                user_states.pop(user_id, None)
                return

            update_setting("welcome_credit", credit_amount, "Credits given to new users")
            await message.reply(
                f"✅ **Welcome Credit Updated!**\n\n"
                f"naye users ko ab {credit_amount} credits mileंगे.",
                reply_markup=get_back_to_owner()
            )
        except ValueError:
            await message.reply("❌ Invalid amount! Kripaya valid number enter kare.")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_TTS_CHARGE and user_id == OWNER_ID:
        try:
            charge_amount = float(message.text.strip())
            if charge_amount < 0:
                await message.reply("❌ Charge amount nahi हो सकती negative!")
                user_states.pop(user_id, None)
                return

            update_setting("tts_charge", charge_amount, "Credits charged per word for TTS")
            await message.reply(
                f"✅ **TTS Charge Updated!**\n\n"
                f"ab per word {charge_amount} credits charge होंगे.",
                reply_markup=get_back_to_owner()
            )
        except ValueError:
            await message.reply("❌ Invalid amount! Kripaya valid number enter kare.")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_EARN_CREDIT and user_id == OWNER_ID:
        try:
            earn_amount = float(message.text.strip())
            if earn_amount < 0:
                await message.reply("❌ Earn amount nahi हो सकती negative!")
                user_states.pop(user_id, None)
                return

            update_setting("earn_credit", earn_amount, "Credits earned per short link process")
            await message.reply(
                f"✅ **Earn Credit Updated!**\n\n"
                f"ab short link process karne par {earn_amount} credits mileंगे.",
                reply_markup=get_back_to_owner()
            )
        except ValueError:
            await message.reply("❌ Invalid amount! Kripaya valid number enter kare.")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_DEACTIVATE_REASON and user_id == OWNER_ID:
        reason = message.text.strip()
        user_states[user_id] = {'state': UserState.WAITING_DEACTIVATE_TIME, 'reason': reason}
        await message.reply(
            f"📝 Reason: {reason}\n\n"
            f"कितne minutes ke liye bot ko deactivate karna hai?\n"
            f"(0 enter kare permanent ke liye):"
        )

    elif isinstance(user_state_data, dict) and user_state_data.get('state') == UserState.WAITING_DEACTIVATE_TIME and user_id == OWNER_ID:
        try:
            minutes = int(message.text.strip())
            reason = user_state_data.get('reason')

            user_states[user_id] = {'reason': reason, 'minutes': minutes}

            time_text = f"{minutes} minutes" if minutes > 0 else "permanent"

            await message.reply(
                f"⚠️ **Deactivation Confirmation**\n\n"
                f"📝 Reason: {reason}\n"
                f"⏰ Duration: {time_text}\n\n"
                f"क्ya aap confirm karte hai?",
                reply_markup=get_deactivate_confirmation_panel()
            )
        except ValueError:
            await message.reply("❌ Invalid number! Kripaya valid number enter kare.")
            user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_RATING_COUNT and user_id == OWNER_ID:
        try:
            rating_count = int(message.text.strip())
            if rating_count <= 0:
                await message.reply("❌ Count 0 se ज्yaदा होनी चाहिए!")
                user_states.pop(user_id, None)
                return

            user_states[user_id] = {'rating_count': rating_count}

            await message.reply(
                f"⭐ **Add {rating_count} Fake Ratings**\n\n"
                f"Kripaya rating select kare:",
                reply_markup=get_rating_panel()
            )
        except ValueError:
            await message.reply("❌ Invalid number! Kripaya valid number enter kare.")
            user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_MIN_PAYMENT and user_id == OWNER_ID:
        try:
            min_amount = float(message.text.strip())
            if min_amount <= 0:
                await message.reply("❌ Amount 0 se ज्yaदा होनी चाहिए!")
                user_states.pop(user_id, None)
                return

            update_setting("min_payment_amount", min_amount, "Minimum payment amount in rupees")
            await message.reply(
                f"✅ **Minimum Payment Amount Updated!**\n\n"
                f"naya minimum amount: ₹{min_amount}",
                reply_markup=get_back_to_owner()
            )
        except ValueError:
            await message.reply("❌ Invalid amount! Kripaya valid number enter kare.")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_MAX_PAYMENT and user_id == OWNER_ID:
        try:
            max_amount = float(message.text.strip())
            min_amount = get_setting("min_payment_amount", default=10.0)

            if max_amount <= min_amount:
                await message.reply(f"❌ Maximum amount minimum amount (₹{min_amount}) se ज्yaदा होनी चाहिए!")
                user_states.pop(user_id, None)
                return

            update_setting("max_payment_amount", max_amount, "Maximum payment amount in rupees")
            await message.reply(
                f"✅ **Maximum Payment Amount Updated!**\n\n"
                f"naya maximum amount: ₹{max_amount}",
                reply_markup=get_back_to_owner()
            )
        except ValueError:
            await message.reply("❌ Invalid amount! Kripaya valid number enter kare.")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_PAYMENT_RATE and user_id == OWNER_ID:
        try:
            payment_rate = float(message.text.strip())
            if payment_rate <= 0:
                await message.reply("❌ Rate 0 se ज्yaदा होनी चाहिए!")
                user_states.pop(user_id, None)
                return

            update_setting("payment_rate", payment_rate, "Credits per rupee")
            await message.reply(
                f"✅ **Payment Credit Rate Updated!**\n\n"
                f"naya rate: {payment_rate} credits per ₹1",
                reply_markup=get_back_to_owner()
            )
        except ValueError:
            await message.reply("❌ Invalid amount! Kripaya valid number enter kare.")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_PAYMENT_AMOUNT:
        try:
            amount = float(message.text.strip())
            min_amount = get_setting("min_payment_amount", default=10.0)
            max_amount = get_setting("max_payment_amount", default=100.0)
            payment_rate = get_setting("payment_rate", default=10.0)

            if amount < min_amount or amount > max_amount:
                await message.reply(f"❌ Amount ₹{min_amount} se ₹{max_amount} ke बीच होना चाहिए!")
                user_states.pop(user_id, None)
                return

            # Calculate credits based on current rate
            credits_to_add = int(amount * payment_rate)

            user_states[user_id] = {'state': UserState.WAITING_TRANSACTION_ID, 'amount': amount, 'credits': credits_to_add}

            # Get QR code from database (File ID based system)
            db = SessionLocal()
            qr_file_id = None
            qr_code_url = None
            payment_number = "Not Set"
            payment_name = "Not Set"
            
            try:
                qr_settings = db.query(QRCodeSettings).filter(QRCodeSettings.is_active == True).first()
                if qr_settings:
                    # Priority: File ID > URL (for backward compatibility)
                    qr_file_id = qr_settings.qr_code_file_id
                    qr_code_url = qr_settings.qr_code_url
                    payment_number = qr_settings.payment_number or "Not Set"
                    payment_name = qr_settings.payment_name or "Not Set"
            except Exception as e:
                print(f"Error retrieving QR settings: {e}")
            finally:
                db.close()

            # Send QR code with payment details (File ID preferred)
            payment_caption = (
                f"💳 **Payment Details**\n\n"
                f"💰 **Amount:** ₹{amount}\n"
                f"💎 **Credits:** {credits_to_add}\n"
                f"📱 **Pay to:** {payment_name}\n"
                f"🆔 **UPI/Number:** {payment_number}\n\n"
                f"📱 is QR code ko scan karke payment kare\n"
                f"⏰ 2 minutes ke अंदर transaction ID send kare\n\n"
                f"❌ Cancel karne ke liye /cancel type kare"
            )
            
            qr_sent = False
            payment_msg = None
            
            # Try to send using File ID first
            if qr_file_id:
                try:
                    payment_msg = await message.reply_photo(
                        qr_file_id,
                        caption=payment_caption
                    )
                    qr_sent = True
                except Exception as e:
                    print(f"Failed to send QR using file ID: {e}")
            
            # Fallback to URL if file ID failed or not available
            if not qr_sent and qr_code_url:
                try:
                    payment_msg = await message.reply_photo(
                        qr_code_url,
                        caption=payment_caption
                    )
                    qr_sent = True
                except Exception as e:
                    print(f"Failed to send QR using URL: {e}")
            
            # Final fallback - text only if no QR available
            if not qr_sent:
                payment_msg = await message.reply(
                    f"💳 **Payment Details**\n\n"
                    f"💰 **Amount:** ₹{amount}\n"
                    f"💎 **Credits:** {credits_to_add}\n"
                    f"📱 **Pay to:** {payment_name}\n"
                    f"🆔 **UPI/Number:** {payment_number}\n\n"
                    f"⚠️ QR code not available. Use UPI ID for payment.\n"
                    f"⏰ Transaction ID send kare\n"
                    f"❌ Cancel karne ke liye /cancel type kare"
                )
            
            # Store payment message ID for deletion when transaction ID is submitted
            if payment_msg:
                user_states[user_id]['payment_msg_id'] = payment_msg.id
        except ValueError:
            await message.reply("❌ Invalid amount! Kripaya valid number enter kare.")
            user_states.pop(user_id, None)
    
    # Custom Date Range Handler for Transaction History
    elif isinstance(user_state_data, dict) and user_state_data.get('state') == 'waiting_custom_date_1':
        try:
            date_text = message.text.strip()
            # Parse date in DD/MM/YYYY format
            day, month, year = date_text.split('/')
            first_date = datetime(int(year), int(month), int(day))
            
            # Ask for second date (end date) or allow skip for single day
            user_states[user_id] = {'state': 'waiting_custom_date_2', 'first_date': first_date}
            await message.reply(
                f"📅 **First Date Set:** {first_date.strftime('%d/%m/%Y')}\n\n"
                f"Enter the second date (end date) in format:\n"
                f"**DD/MM/YYYY** (e.g., 20/01/2025)\n\n"
                f"ya फिर **Skip** button दबाएं single day ke liye."
            )
        except (ValueError, IndexError):
            await message.reply(
                "❌ **Invalid date format!**\n\n"
                "Kripaya correct format me date enter kare:\n"
                "**DD/MM/YYYY** (e.g., 15/01/2025)"
            )
    
    elif isinstance(user_state_data, dict) and user_state_data.get('state') == 'waiting_custom_date_2':
        try:
            date_text = message.text.strip()
            # Parse date in DD/MM/YYYY format
            day, month, year = date_text.split('/')
            second_date = datetime(int(year), int(month), int(day))
            first_date = user_state_data.get('first_date')
            
            if second_date < first_date:
                await message.reply("❌ End date should be after start date!")
                return
            
            # Generate transaction history for date range
            import os
            transactions = transaction_manager.get_transactions_by_date_range(first_date, second_date + timedelta(days=1))
            filename = f"transactions_range_{first_date.strftime('%Y%m%d')}_{second_date.strftime('%Y%m%d')}_{datetime.now().strftime('%H%M')}.csv"
            filepath = transaction_manager.create_transaction_file(transactions, filename)
            
            if filepath and os.path.exists(filepath):
                await app.send_document(
                    user_id,
                    filepath,
                    caption=f"📊 **Custom Range Transaction History**\n"
                           f"📅 From: {first_date.strftime('%d/%m/%Y')}\n"
                           f"📅 To: {second_date.strftime('%d/%m/%Y')}\n"
                           f"📈 Total Records: {len(transactions)}"
                )
                await message.reply(
                    "✅ Transaction history file sent successfully!",
                    reply_markup=get_transaction_history_panel()
                )
            else:
                await message.reply("❌ Error generating transaction file!")
            
            user_states.pop(user_id, None)
            
        except (ValueError, IndexError):
            await message.reply(
                "❌ **Invalid date format!**\n\n"
                "Kripaya correct format me date enter kare:\n"
                "**DD/MM/YYYY** (e.g., 20/01/2025)"
            )
    
    # Payment Tracking Handler
    elif isinstance(user_state_data, dict) and user_state_data.get('state') == 'waiting_payment_id':
        transaction_id = message.text.strip()
        payment_info = transaction_manager.get_payment_by_transaction_id(transaction_id)
        
        if payment_info:
            await message.reply(
                f"🔍 **Payment Request Found!**\n\n"
                f"🆔 **System ID:** {payment_info['unique_id']}\n"
                f"👤 **User ID:** {payment_info['user_id']}\n"
                f"👤 **Username:** @{payment_info['username']}\n"
                f"💰 **Amount:** ₹{payment_info['amount']}\n"
                f"💎 **Credits:** {payment_info['credits']}\n"
                f"🆔 **Transaction ID:** {payment_info['transaction_id']}\n"
                f"📊 **Status:** {payment_info['status'].title()}\n"
                f"📅 **Created:** {payment_info['created_at']}\n"
                f"✅ **Verified:** {payment_info['verified_at'] or 'Not verified yet'}\n\n"
                f"💡 **Tracking Info:**\n"
                f"• System ID for internal tracking\n"
                f"• Transaction ID provided by user\n"
                f"• Complete payment lifecycle details",
                reply_markup=get_transaction_history_panel()
            )
        else:
            await message.reply(
                f"❌ **Payment Request Not Found!**\n\n"
                f"🔍 Searched for: `{transaction_id}`\n\n"
                f"**Possible reasons:**\n"
                f"• Transaction ID may be incorrect\n"
                f"• Payment request may not exist\n"
                f"• Case sensitive search\n\n"
                f"💡 **Try:**\n"
                f"• Double check the transaction ID\n"
                f"• Search for system ID (PAYxxxxxxxxxx)\n"
                f"• Contact user for correct ID",
                reply_markup=get_transaction_history_panel()
            )
        
        user_states.pop(user_id, None)

    elif isinstance(user_state_data, dict) and user_state_data.get('state') == 'waiting_custom_transaction_id':
        transaction_id = message.text.strip()
        
        try:
            # Search for transaction ID in user's own transactions only
            from credit_history import CreditHistory
            db_credit = get_credit_history_db()
            
            transaction = db_credit.query(CreditHistory).filter(
                CreditHistory.user_id == user_id,  # Only user's own transactions
                CreditHistory.transaction_id == transaction_id
            ).first()
            
            if transaction:
                await message.reply(
                    f"🔍 **Transaction Found!**\n\n"
                    f"🆔 **Transaction ID:** `{transaction.transaction_id}`\n"
                    f"💰 **Amount:** {transaction.amount:+.2f} credits\n"
                    f"📝 **Type:** {transaction.transaction_type.title()}\n"
                    f"🏷️ **Source:** {transaction.source or 'N/A'}\n"
                    f"📄 **Description:** {transaction.description or 'N/A'}\n\n"
                    f"💳 **Balance Changes:**\n"
                    f"• Before: {transaction.balance_before:.2f} credits\n"
                    f"• After: {transaction.balance_after:.2f} credits\n\n"
                    f"📅 **Date & Time:** {transaction.timestamp.strftime('%d/%m/%Y at %H:%M:%S') if transaction.timestamp else 'N/A'}\n"
                    f"✅ **Status:** {'Processed' if transaction.is_processed else 'Pending'}\n\n"
                    f"💡 **Transaction successfully tracked!**",
                    reply_markup=get_my_transaction_panel()
                )
            else:
                await message.reply(
                    f"❌ **Transaction Not Found!**\n\n"
                    f"🔍 **Searched ID:** `{transaction_id}`\n\n"
                    f"**Possible reasons:**\n"
                    f"• Transaction ID may be incorrect\n"
                    f"• Transaction doesn't belong to your account\n"
                    f"• Transaction may not exist in system\n\n"
                    f"💡 **Tips:**\n"
                    f"• Double check the transaction ID\n"
                    f"• Use exact ID from your transaction history\n"
                    f"• Transaction IDs are case sensitive\n"
                    f"• Only your own transactions can be tracked",
                    reply_markup=get_my_transaction_panel()
                )
            
            db_credit.close()
            
        except Exception as e:
            print(f"Error searching custom transaction ID {transaction_id} for user {user_id}: {e}")
            await message.reply(
                f"❌ **Error searching transaction**\n\n"
                f"kuch technical issue hui hai.\n"
                f"Kripaya baad me try kare ya admin se contact kare.",
                reply_markup=get_my_transaction_panel()
            )
            
        user_states.pop(user_id, None)

    elif isinstance(user_state_data, dict) and user_state_data.get('state') == 'waiting_support_message':
        support_message = message.text.strip()
        
        try:
            # Get user information
            db = SessionLocal()
            user = db.query(User).filter(User.user_id == user_id).first()
            
            # Prepare message to send to owner
            current_time = datetime.now().strftime('%d/%m/%Y at %H:%M:%S')
            owner_message = (
                f"🆘 **New Support Request** 🆘\n\n"
                f"👤 **User:** {user.first_name or 'Unknown'}\n"
                f"🆔 **User ID:** {user_id}\n"
                f"👤 **Username:** @{user.username or 'No username'}\n"
                f"📅 **Date:** {current_time}\n"
                f"💳 **Credits:** {user.credits:.2f}\n\n"
                f"📝 **Issue Description:**\n"
                f"{support_message}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 **Reply to this user directly at @{user.username or f'User ID: {user_id}'}**"
            )
            
            # Send message to owner
            try:
                await app.send_message(OWNER_ID, owner_message)
                
                # Show success message to user
                await message.reply(
                    f"✅ **Support Request Sent Successfully!**\n\n"
                    f"📤 **Confirmation: aapka message owner ko bhej diya gaya hai**\n\n"
                    f"🕒 **Sent on:** {current_time}\n"
                    f"📝 **Your Issue:** {support_message[:100]}{'...' if len(support_message) > 100 else ''}\n\n"
                    f"👨‍💼 **Owner will check aur aapko reply karenge**\n"
                    f"⏰ **Response Time:** Usually within 2-4 hours\n\n"
                    f"💡 **Thank you for contacting support!**",
                    reply_markup=get_support_confirmation_keyboard()
                )
                
            except Exception as e:
                print(f"Error sending support message to owner: {e}")
                await message.reply(
                    f"❌ **Error sending your message**\n\n"
                    f"kuch technical issue hui hai.\n"
                    f"Kripaya baad me try kare ya direct message kare: @PR_GAMING_25",
                    reply_markup=get_support_confirmation_keyboard()
                )
            
            db.close()
            
        except Exception as e:
            print(f"Error processing support message for user {user_id}: {e}")
            await message.reply(
                f"❌ **Error processing your support request**\n\n"
                f"kuch technical issue hui hai.\n"
                f"Kripaya baad me try kare.",
                reply_markup=get_support_confirmation_keyboard()
            )
            
        user_states.pop(user_id, None)

    elif isinstance(user_state_data, dict) and user_state_data.get('state') == UserState.WAITING_TRANSACTION_ID:
        transaction_id = message.text.strip()
        amount = user_state_data.get('amount')
        credits_to_add = user_state_data.get('credits')

        # Store payment request in database
        db = SessionLocal()
        try:
            from database import PaymentRequest
            from datetime import datetime
            import random
            import string
            
            # Generate unique payment request ID
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            unique_payment_id = f"PAY{timestamp}{random_suffix}"
            
            payment_request = PaymentRequest(
                user_id=user_id,
                amount=amount,
                credits_to_add=credits_to_add,
                transaction_id=transaction_id,
                status='pending'
            )
            db.add(payment_request)
            db.commit()
            db.refresh(payment_request)
            
            # Update payment request with unique ID
            payment_request.unique_id = unique_payment_id
            db.commit()

            # Delete payment details message and user's transaction ID message for clean chat
            try:
                # Delete user's transaction ID message
                await message.delete()
                
                # Delete payment details message if available
                payment_msg_id = user_state_data.get('payment_msg_id')
                if payment_msg_id:
                    await client.delete_messages(chat_id=message.chat.id, message_ids=payment_msg_id)
                    print(f"✅ Deleted payment details message for user {user_id}")
            except Exception as e:
                print(f"⚠️ Could not delete payment messages for user {user_id}: {e}")

            # Send confirmation message to user
            confirmation_msg = await message.reply(
                f"✅ **Payment Request Submitted!**\n\n"
                f"💰 Amount: ₹{amount}\n"
                f"💎 Credits: {credits_to_add}\n"
                f"🆔 Transaction ID: {transaction_id}\n\n"
                f"📋 aapki payment request admin ko manually check kiya जाएगा\n"
                f"⏰ Usually processed within 1-2 hours\n"
                f"🕐 agar kuch delay हो तो max 12 hours\n"
                f"🙏 Please be patient!\n\n"
                f"🎁 **Bonus:** Delay ke liye 10 extra credits mileंगे!"
            )

            # Auto-delete message after 15 seconds and give bonus credits
            await asyncio.sleep(15)
            try:
                await confirmation_msg.delete()

                # Give 10 bonus credits for patience
                user = db.query(User).filter(User.user_id == user_id).first()
                if user:
                    user.credits = float(user.credits) + 10
                    db.commit()
                    log_credit_transaction(user_id, 10, 'bonus', 'Patience bonus for payment delay')

                    await client.send_message(
                        user_id,
                        f"🎁 **Bonus Credits Added!**\n\n"
                        f"Aapko patience ke liye 10 extra credits mile hai!\n"
                        f"💰 Current Balance: {user.credits:.0f} credits"
                    )
            except:
                pass

            # Notify channel or owner with enhanced error handling and fallback
            notification_sent = False

            # Try channel first if configured
            target_channel = connected_channel_id or CHANNEL_ID
            if target_channel and not notification_sent:
                try:
                    # Better channel ID validation and conversion
                    if target_channel.startswith('-100'):
                        target_id = int(target_channel)
                    elif target_channel.startswith('-'):
                        target_id = int(target_channel)
                    elif target_channel.startswith('@'):
                        target_id = target_channel
                    else:
                        target_id = f"@{target_channel}"

                    print(f"📤 Attempting to send payment notification to channel (ID: {target_id})...")
                    print(f"📤 Channel source: {'Runtime Connected' if connected_channel_id else 'Environment Variable'}")
                    print(f"📤 Channel ID: {target_channel}")

                    # First test if we can get channel info
                    try:
                        channel_info = await client.get_chat(target_id)
                        print(f"✅ Channel found: {channel_info.title} (Type: {channel_info.type})")
                    except Exception as channel_check_error:
                        print(f"❌ Channel access check failed: {channel_check_error}")
                        raise Exception(f"Cannot access channel: {channel_check_error}")

                    notification_message = await client.send_message(
                        target_id,
                        f"💳 **New Payment Request #{payment_request.id}**\n\n"
                        f"👤 User: {message.from_user.first_name} (@{message.from_user.username or 'No username'})\n"
                        f"🆔 User ID: {user_id}\n"
                        f"💰 Amount: ₹{amount}\n"
                        f"💎 Credits: {credits_to_add}\n"
                        f"🆔 Transaction ID: `{transaction_id}`\n"
                        f"📅 Time: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                        f"⚡ **Action Required:** Please verify this payment manually and take action.",
                        reply_markup=get_payment_verification_panel(payment_request.id)
                    )

                    print(f"✅ Payment notification sent successfully to channel!")
                    notification_sent = True

                except Exception as channel_error:
                    print(f"❌ Channel notification failed: {channel_error}")
                    print(f"📋 Channel troubleshooting:")
                    print(f"   - Check if bot is added to channel")
                    print(f"   - Check if bot has admin rights in channel")
                    print(f"   - Verify channel connection or .env file")
                    print(f"   - Current channel: {target_channel}")
                    print(f"   - Channel source: {'Runtime Connected' if connected_channel_id else 'Environment Variable'}")

            # Fallback to owner if channel failed or not configured
            if not notification_sent and OWNER_ID and OWNER_ID != 0:
                try:
                    print(f"📤 Falling back to owner notification (ID: {OWNER_ID})...")

                    notification_message = await client.send_message(
                        OWNER_ID,
                        f"💳 **New Payment Request #{payment_request.id}**\n\n"
                        f"👤 User: {message.from_user.first_name} (@{message.from_user.username or 'No username'})\n"
                        f"🆔 User ID: {user_id}\n"
                        f"💰 Amount: ₹{amount}\n"
                        f"💎 Credits: {credits_to_add}\n"
                        f"🆔 Transaction ID: `{transaction_id}`\n"
                        f"📅 Time: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                        f"⚡ **Action Required:** Please verify this payment manually and take action.\n\n"
                        f"⚠️ Note: Channel notification failed, sending to owner directly.",
                        reply_markup=get_payment_verification_panel(payment_request.id)
                    )

                    print(f"✅ Payment notification sent successfully to owner!")
                    notification_sent = True

                except Exception as owner_error:
                    print(f"❌ Owner notification also failed: {owner_error}")

            # Notify user based on success/failure
            if notification_sent:
                try:
                    await message.reply(
                        f"📢 **Admin Notified!**\n\n"
                        f"aapki payment request admin ko भेज दी गई hai.\n"
                        f"🔔 Request ID: #{payment_request.id}\n"
                        f"⏰ Request processing time: 1-2 hours (max 12 hours).\n\n"
                        f"💡 You can continue using the bot with /start command.",
                        reply_markup=get_back_to_user()
                    )
                except:
                    pass
            else:
                print(f"❌ CRITICAL: Both channel and owner notification failed!")
                try:
                    await message.reply(
                        f"⚠️ **Notification Issue**\n\n"
                        f"✅ aapki payment request save हो गई hai\n"
                        f"🔔 Request ID: #{payment_request.id}\n"
                        f"⚠️ Admin notification me technical issue\n\n"
                        f"📱 Kripaya manually owner se contact kare:\n"
                        f"💳 Amount: ₹{amount}\n"
                        f"🆔 Transaction ID: {transaction_id}\n"
                        f"🔢 Request ID: #{payment_request.id}",
                        reply_markup=get_payment_cancel_panel()
                    )
                except:
                    pass

        finally:
            db.close()

        user_states.pop(user_id, None)

    # Settings confirmation and cancel handlers
    elif data == "settings_cancel":
        await callback_query.edit_message_text(
            "❌ **Settings Update Cancelled**\n\n"
            "koi changes nahi किए गए.",
            reply_markup=get_credits_settings_panel()
        )
        user_states.pop(user_id, None)

    elif data.startswith("settings_confirm_"):
        setting_type = data.replace("settings_confirm_", "")
        await callback_query.edit_message_text(
            f"✅ **Settings Confirmed**\n\n"
            f"Setting {setting_type} successfully updated!",
            reply_markup=get_back_to_owner()
        )
        user_states.pop(user_id, None)

    # QR code management text handlers
    elif user_state_data == UserState.WAITING_QR_CODE_URL and user_id == OWNER_ID:
        qr_url = message.text.strip()

        db = SessionLocal()
        try:
            # Update or create QR settings
            qr_settings = db.query(QRCodeSettings).filter(QRCodeSettings.is_active == True).first()
            if qr_settings:
                qr_settings.qr_code_url = qr_url
                qr_settings.updated_at = datetime.utcnow()
            else:
                qr_settings = QRCodeSettings(
                    qr_code_url=qr_url,
                    payment_number="Not Set",
                    payment_name="Not Set"
                )
                db.add(qr_settings)
            db.commit()

            await message.reply(
                "✅ **QR Code Updated!**\n\n"
                f"New QR URL: {qr_url[:50]}{'...' if len(qr_url) > 50 else ''}",
                reply_markup=get_back_to_owner()
            )
        except Exception as e:
            await message.reply("❌ Error updating QR code!", reply_markup=get_back_to_owner())
        finally:
            db.close()

        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_PAYMENT_NUMBER and user_id == OWNER_ID:
        payment_number = message.text.strip()
        user_states[user_id] = {'state': UserState.WAITING_PAYMENT_NAME, 'payment_number': payment_number}

        await message.reply(
            f"📱 Payment Number: {payment_number}\n\n"
            "ab payment name enter kare:"
        )

    elif isinstance(user_state_data, dict) and user_state_data.get('state') == UserState.WAITING_PAYMENT_NAME and user_id == OWNER_ID:
        payment_name = message.text.strip()
        payment_number = user_state_data.get('payment_number')

        db = SessionLocal()
        try:
            # Update payment details
            qr_settings = db.query(QRCodeSettings).filter(QRCodeSettings.is_active == True).first()
            if qr_settings:
                qr_settings.payment_number = payment_number
                qr_settings.payment_name = payment_name
                qr_settings.updated_at = datetime.utcnow()
            else:
                qr_settings = QRCodeSettings(
                    qr_code_url="https://via.placeholder.com/300x300.png?text=QR+CODE+PLACEHOLDER",
                    payment_number=payment_number,
                    payment_name=payment_name
                )
                db.add(qr_settings)
            db.commit()

            await message.reply(
                "✅ **Payment Details Updated!**\n\n"
                f"📱 **Number:** {payment_number}\n"
                f"👤 **Name:** {payment_name}",
                reply_markup=get_back_to_owner()
            )
        except Exception as e:
            await message.reply("❌ Error updating payment details!", reply_markup=get_back_to_owner())
        finally:
            db.close()

        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_UPI_ID_ONLY and user_id == OWNER_ID:
        upi_id = message.text.strip()
        db = SessionLocal()
        try:
            # Update UPI ID only
            qr_settings = db.query(QRCodeSettings).filter(QRCodeSettings.is_active == True).first()
            if qr_settings:
                qr_settings.payment_number = upi_id
                qr_settings.updated_at = datetime.utcnow()
            else:
                qr_settings = QRCodeSettings(
                    payment_number=upi_id,
                    payment_name="Owner"
                )
                db.add(qr_settings)
            db.commit()

            await message.reply(
                f"✅ **UPI ID Updated!**\n\n"
                f"📱 **New UPI ID:** {upi_id}",
                reply_markup=get_back_to_owner()
            )
        except Exception as e:
            await message.reply("❌ Error updating UPI ID!", reply_markup=get_back_to_owner())
        finally:
            db.close()
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_QR_UPI_SETUP and user_id == OWNER_ID:
        upi_id = message.text.strip()
        user_states[user_id] = {'state': UserState.WAITING_QR_CODE_FILE, 'upi_id': upi_id}
        await message.reply(
            f"📱 UPI ID: {upi_id}\n\n"
            "Ab QR code image bheje (photo upload kare):"
        )

@app.on_message(filters.command("cancel"))
async def cancel_command(client: Client, message: Message):
    """Handle /cancel command to clear user state"""
    user_id = message.from_user.id
    if user_id in user_states:
        user_states.pop(user_id)
        await message.reply("❌ Operation cancelled. Your state has been reset.")
    else:
        await message.reply("ℹ️ No active operation to cancel.")

@app.on_message(filters.photo)
async def handle_photo(client: Client, message: Message):
    """Handle photo uploads for QR code file ID storage"""
    user_id = message.from_user.id
    
    # Only owner can upload QR code photos
    if user_id != OWNER_ID:
        return
    
    # Check if user is in QR code upload state
    user_state_data = user_states.get(user_id, {})
    
    if user_state_data == UserState.WAITING_QR_CODE_FILE:
        # Handle QR code file upload
        try:
            file_id = message.photo.file_id
            db = SessionLocal()
            try:
                # Update QR code file ID
                qr_settings = db.query(QRCodeSettings).filter(QRCodeSettings.is_active == True).first()
                if qr_settings:
                    # Clear old file ID and URL for fresh upload
                    qr_settings.qr_code_file_id = file_id
                    qr_settings.qr_code_url = None  # Clear URL since we're using file ID now
                    qr_settings.updated_at = datetime.utcnow()
                else:
                    qr_settings = QRCodeSettings(
                        qr_code_file_id=file_id,
                        payment_number="UPI_ID_NOT_SET",
                        payment_name="Owner"
                    )
                    db.add(qr_settings)
                db.commit()

                await message.reply(
                    "✅ **QR Code Updated Successfully!**\n\n"
                    f"📱 **File ID:** {file_id[:20]}...\n"
                    "QR code ab payment requests me use hoga.",
                    reply_markup=get_back_to_owner()
                )
            except Exception as e:
                await message.reply("❌ Error updating QR code!", reply_markup=get_back_to_owner())
            finally:
                db.close()
        except Exception as e:
            await message.reply("❌ Error processing QR code image!", reply_markup=get_back_to_owner())
        
        user_states.pop(user_id, None)
    
    elif isinstance(user_state_data, dict) and user_state_data.get('state') == UserState.WAITING_QR_CODE_FILE:
        # Handle QR code upload for setup process
        try:
            file_id = message.photo.file_id
            upi_id = user_state_data.get('upi_id')
            
            db = SessionLocal()
            try:
                # Add or update QR settings with both UPI and file ID
                qr_settings = db.query(QRCodeSettings).filter(QRCodeSettings.is_active == True).first()
                if qr_settings:
                    qr_settings.qr_code_file_id = file_id
                    qr_settings.qr_code_url = None  # Clear URL
                    if upi_id:
                        qr_settings.payment_number = upi_id
                    qr_settings.updated_at = datetime.utcnow()
                else:
                    qr_settings = QRCodeSettings(
                        qr_code_file_id=file_id,
                        payment_number=upi_id or "UPI_ID_NOT_SET",
                        payment_name="Owner"
                    )
                    db.add(qr_settings)
                db.commit()

                await message.reply(
                    "✅ **QR Code & UPI Setup Complete!**\n\n"
                    f"📱 **UPI ID:** {upi_id or 'Not Set'}\n"
                    f"🖼️ **QR File ID:** {file_id[:20]}...\n"
                    "Setup successfully completed!",
                    reply_markup=get_back_to_owner()
                )
            except Exception as e:
                await message.reply("❌ Error setting up QR & UPI!", reply_markup=get_back_to_owner())
            finally:
                db.close()
        except Exception as e:
            await message.reply("❌ Error processing QR code image!", reply_markup=get_back_to_owner())
        
        user_states.pop(user_id, None)

@app.on_message(filters.document)
async def handle_document(client: Client, message: Message):
    """Handle document uploads for backup restore with PostgreSQL and SQLite support"""
    user_id = message.from_user.id
    
    # Only owner can upload backup files
    if user_id != OWNER_ID:
        return
    
    # Check if user is in backup process
    user_state_data = user_states.get(user_id, {})
    if not isinstance(user_state_data, dict):
        user_state_data = {}
    
    state = user_state_data.get('state')
    if state not in ['waiting_backup_main_db', 'waiting_backup_credit_history_db']:
        # User uploaded a file but isn't in backup restoration mode
        file_name = message.document.file_name if message.document else "Unknown"
        await message.reply(
            f"📋 **Backup File Detected!**\n\n"
            f"📄 **File:** {file_name}\n\n"
            f"⚠️ **Backup restoration mode not active.**\n\n"
            f"🔧 **To restore backup:**\n"
            f"1. Go to Owner Panel\n"
            f"2. Select Settings\n"
            f"3. Select 'Database Backup'\n"
            f"4. Choose 'Restore Backup'\n"
            f"5. Then upload your backup files\n\n"
            f"💡 **Supported formats:**\n"
            f"• `.sql`, `.dump`, `.backup` files (PostgreSQL)\n"
            f"• `.db`, `.sqlite`, `.sqlite3` files (SQLite)\n\n"
            f"कृपया backup restoration mode activate करके फिर file upload करें।",
            reply_markup=get_back_to_owner()
        )
        return
    
    # Check if document is a valid backup file
    file_name = message.document.file_name
    if not file_name:
        await message.reply(
            "❌ **Invalid File!**\n\n"
            "File name not detected.\n"
            "Kripaya valid backup file bheje."
        )
        return
    
    # Determine file type and validity - Support multiple extensions
    file_name_lower = file_name.lower()
    is_sql_file = (file_name_lower.endswith('.sql') or 
                  file_name_lower.endswith('.dump') or 
                  file_name_lower.endswith('.backup'))
    is_db_file = (file_name_lower.endswith('.db') or 
                 file_name_lower.endswith('.sqlite') or 
                 file_name_lower.endswith('.sqlite3'))
    
    if state == 'waiting_backup_main_db':
        # Main database can be either .sql (PostgreSQL) or .db (SQLite)
        if not (is_sql_file or is_db_file):
            await message.reply(
                "❌ **Invalid File Type for Main Database!**\n\n"
                "📊 **Accepted formats:**\n"
                "• `.sql`, `.dump`, `.backup` files (PostgreSQL dumps)\n"
                "• `.db`, `.sqlite`, `.sqlite3` files (SQLite databases)\n\n"
                "Kripaya valid main database backup file bheje."
            )
            return
    elif state == 'waiting_backup_credit_history_db':
        # Credit history is always SQLite (.db)
        if not is_db_file:
            await message.reply(
                "❌ **Invalid File Type for Credit History!**\n\n"
                "📊 **Required formats:** `.db`, `.sqlite`, `.sqlite3` files (SQLite)\n\n"
                "Credit history database कeval SQLite format में accept होती hai.\n"
                "Kripaya valid .db file bheje."
            )
            return
    
    try:
        # Validate file size first
        if message.document.file_size == 0:
            await message.reply(
                "❌ **Empty File Detected!**\n\n"
                "📄 **File:** " + file_name + "\n"
                "💾 **Size:** 0 bytes\n\n"
                "⚠️ **File is empty and cannot be processed**\n"
                "Kripaya valid backup file भेजें जिसमें data हो।"
            )
            return
        
        # Check minimum file size (at least 1KB for valid database)
        min_size = 1024  # 1KB minimum
        if message.document.file_size < min_size:
            await message.reply(
                f"❌ **File Too Small!**\n\n"
                f"📄 **File:** {file_name}\n"
                f"💾 **Size:** {message.document.file_size} bytes\n"
                f"⚠️ **Minimum required:** {min_size} bytes (1KB)\n\n"
                f"File is too small to be a valid database backup.\n"
                f"Kripaya proper backup file भेजें।"
            )
            return
        
        # Download the file
        downloading_msg = await message.reply("📥 **Downloading backup file...**")
        
        try:
            file_path = await message.download()
            if not file_path or not os.path.exists(file_path):
                await downloading_msg.edit_text(
                    "❌ **Download Failed!**\n\n"
                    "File download नहीं हुई। Network issue हो सकती है.\n"
                    "Kripaya फिर से try करें।"
                )
                return
                
            # Verify downloaded file size
            downloaded_size = os.path.getsize(file_path)
            if downloaded_size == 0:
                await downloading_msg.edit_text(
                    "❌ **Downloaded File is Empty!**\n\n"
                    "File download हुई लेकिन empty है.\n"
                    "Kripaya valid file भेजें।"
                )
                if os.path.exists(file_path):
                    os.remove(file_path)
                return
                
        except Exception as download_error:
            await downloading_msg.edit_text(
                f"❌ **Download Error!**\n\n"
                f"🔧 **Error:** {str(download_error)}\n"
                f"📄 **File:** {file_name}\n\n"
                f"File download में problem हुई।\n"
                f"Kripaya फिर से try करें।"
            )
            return
        
        if state == 'waiting_backup_main_db':
            # Handle main database file
            file_type = "PostgreSQL SQL Dump" if is_sql_file else "SQLite Database"
            await downloading_msg.edit_text(
                f"✅ **Main Database Downloaded!**\n\n"
                f"📄 **File:** {file_name}\n"
                f"📊 **Type:** {file_type}\n"
                f"💾 **Size:** {message.document.file_size / 1024:.1f} KB\n\n"
                f"🔄 **Processing backup...**"
            )
            
            # Handle PostgreSQL vs SQLite restoration
            import shutil
            try:
                if is_sql_file:
                    # PostgreSQL SQL dump restoration
                    await downloading_msg.edit_text(
                        f"🐘 **Restoring PostgreSQL Database...** 🐘\n\n"
                        f"📄 **File:** {file_name}\n"
                        f"💾 **Size:** {message.document.file_size / 1024:.1f} KB\n\n"
                        f"⚙️ **Executing SQL dump restoration...**"
                    )
                    
                    # Get DATABASE_URL
                    database_url = os.getenv('DATABASE_URL', 'sqlite:///./bot.db')
                    
                    if database_url.startswith('postgresql://') or database_url.startswith('postgres://'):
                        # Check if psql is available
                        import subprocess
                        try:
                            subprocess.run(['psql', '--version'], capture_output=True, check=True)
                        except (subprocess.CalledProcessError, FileNotFoundError):
                            await downloading_msg.edit_text(
                                f"❌ **PostgreSQL Client Not Found!**\n\n"
                                f"📄 **File:** {file_name} (PostgreSQL dump)\n"
                                f"⚠️ **Error:** `psql` command not available\n\n"
                                f"💡 **Solutions:**\n"
                                f"• Use SQLite backup (.db file) instead\n"
                                f"• Install PostgreSQL client tools\n"
                                f"• Ask admin to configure PostgreSQL\n\n"
                                f"Kripaya .db file भेजें या admin से help लें।"
                            )
                            user_states.pop(user_id, None)
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            return
                        
                        # Restore to PostgreSQL with better error handling
                        try:
                            await downloading_msg.edit_text(
                                f"🐘 **Restoring PostgreSQL Database...** 🐘\n\n"
                                f"📄 **File:** {file_name}\n"
                                f"💾 **Size:** {message.document.file_size / 1024:.1f} KB\n\n"
                                f"⚙️ **Executing SQL dump restoration...**\n"
                                f"⏳ **This may take a few moments...**"
                            )
                            
                            # Use subprocess for better error handling
                            restore_process = subprocess.run(
                                f"psql '{database_url}' < {file_path}",
                                shell=True,
                                capture_output=True,
                                text=True,
                                timeout=300  # 5 minute timeout
                            )
                            
                            if restore_process.returncode == 0:
                                progress_msg = await downloading_msg.edit_text(
                                f"✅ **PostgreSQL Database Restored Successfully!** ✅\n\n"
                                f"📄 **File:** {file_name}\n"
                                f"💾 **Size:** {message.document.file_size / 1024:.1f} KB\n"
                                f"🐘 **Database:** PostgreSQL\n"
                                f"🔄 **Status:** Backup data loaded into active database\n\n"
                                f"🔄 **Backup Mode Still Active**\n"
                                f"📋 **Step 2/2: Please send Transaction History file now:**\n\n"
                                f"💡 **Supported formats:** `.db`, `.sqlite`, `.sqlite3`\n"
                                f"⚠️ **Next file will complete the process**"
                            )
                            
                                # Update state for next file - maintain backup tracking  
                                backup_start_time = user_state_data.get('backup_start_time')
                                backup_msg_id = user_state_data.get('backup_msg_id') 
                                user_states[user_id] = {
                                    'state': 'waiting_backup_credit_history_db',
                                    'backup_step': 2,
                                    'backup_start_time': backup_start_time,
                                    'backup_msg_id': backup_msg_id,
                                    'main_db_completed': True
                                }
                            else:
                                error_msg = restore_process.stderr.strip() if restore_process.stderr else "Unknown error"
                                await downloading_msg.edit_text(
                                    f"❌ **PostgreSQL Restore Failed!**\n\n"
                                    f"📄 **File:** {file_name}\n"
                                    f"🔧 **Exit code:** {restore_process.returncode}\n"
                                    f"📝 **Error:** {error_msg[:200]}{'...' if len(error_msg) > 200 else ''}\n\n"
                                    f"💡 **Possible causes:**\n"
                                    f"• Invalid SQL dump format\n"
                                    f"• Database connection issues\n"
                                    f"• Permission problems\n\n"
                                    f"🔄 **Try using .db file for SQLite instead**"
                                )
                                user_states.pop(user_id, None)
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                                
                        except subprocess.TimeoutExpired:
                            await downloading_msg.edit_text(
                                f"❌ **PostgreSQL Restore Timeout!**\n\n"
                                f"📄 **File:** {file_name}\n"
                                f"⏰ **Timeout:** 5 minutes exceeded\n\n"
                                f"File is too large या process stuck हो गया।\n"
                                f"Kripaya smaller backup file भेजें।"
                            )
                            user_states.pop(user_id, None)
                            if os.path.exists(file_path):
                                os.remove(file_path)
                                
                        except Exception as psql_error:
                            await downloading_msg.edit_text(
                                f"❌ **PostgreSQL Error!**\n\n"
                                f"📄 **File:** {file_name}\n"
                                f"🔧 **Error:** {str(psql_error)}\n\n"
                                f"Database restoration में technical error हुई।\n"
                                f"Kripaya admin से contact करें।"
                            )
                            user_states.pop(user_id, None)
                            if os.path.exists(file_path):
                                os.remove(file_path)
                    else:
                        await downloading_msg.edit_text(
                            f"❌ **Configuration Mismatch!**\n\n"
                            f"📊 **File Type:** PostgreSQL SQL dump\n"
                            f"🗄️ **Current DB:** SQLite\n\n"
                            f"💡 **Options:**\n"
                            f"• Use a .db file for SQLite restoration\n"
                            f"• Configure PostgreSQL environment"
                        )
                        user_states.pop(user_id, None)
                        
                elif is_db_file:
                    # SQLite database file restoration with comprehensive validation
                    await downloading_msg.edit_text(
                        f"🗃️ **Processing SQLite Database...** 🗃️\n\n"
                        f"📄 **File:** {file_name}\n"
                        f"💾 **Size:** {message.document.file_size / 1024:.1f} KB\n\n"
                        f"🔄 **Validating database integrity...**"
                    )
                    
                    # Comprehensive SQLite validation
                    import sqlite3
                    try:
                        # Test SQLite file validity
                        test_conn = sqlite3.connect(file_path)
                        test_cursor = test_conn.cursor()
                        
                        # Check if file is a valid SQLite database
                        test_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tables = test_cursor.fetchall()
                        test_conn.close()
                        
                        if not tables:
                            await downloading_msg.edit_text(
                                f"❌ **Empty SQLite Database!**\n\n"
                                f"📄 **File:** {file_name}\n"
                                f"⚠️ **Issue:** Database contains no tables\n\n"
                                f"File is valid SQLite लेकिन empty है.\n"
                                f"Kripaya proper backup file भेजें।"
                            )
                            user_states.pop(user_id, None)
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            return
                            
                        await downloading_msg.edit_text(
                            f"✅ **SQLite Validation Passed!**\n\n"
                            f"📄 **File:** {file_name}\n"
                            f"💾 **Size:** {message.document.file_size / 1024:.1f} KB\n"
                            f"📊 **Tables found:** {len(tables)}\n\n"
                            f"🔄 **Replacing main database...**"
                        )
                        
                    except sqlite3.DatabaseError as db_error:
                        await downloading_msg.edit_text(
                            f"❌ **Invalid SQLite File!**\n\n"
                            f"📄 **File:** {file_name}\n"
                            f"🔧 **SQLite Error:** {str(db_error)}\n\n"
                            f"File is corrupted या invalid format में है.\n"
                            f"Kripaya valid .db file भेजें।"
                        )
                        user_states.pop(user_id, None)
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        return
                    except Exception as validation_error:
                        await downloading_msg.edit_text(
                            f"❌ **File Validation Error!**\n\n"
                            f"📄 **File:** {file_name}\n"
                            f"🔧 **Error:** {str(validation_error)}\n\n"
                            f"File validation में problem हुई.\n"
                            f"Kripaya valid backup file भेजें।"
                        )
                        user_states.pop(user_id, None)
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        return
                    
                    # Safe database replacement with backup
                    try:
                        from datetime import datetime as dt3
                        if os.path.exists('bot.db'):
                            backup_name = f"bot_backup_{dt3.now().strftime('%Y%m%d_%H%M%S')}.db"
                            shutil.copy('bot.db', backup_name)
                            os.remove('bot.db')  # Remove current database
                        
                        shutil.move(file_path, 'bot.db')  # Move uploaded file to bot.db
                        
                    except Exception as file_error:
                        await downloading_msg.edit_text(
                            f"❌ **File Replacement Error!**\n\n"
                            f"📄 **File:** {file_name}\n"
                            f"🔧 **Error:** {str(file_error)}\n\n"
                            f"Database file replacement में error हुई.\n"
                            f"Kripaya admin से contact करें।"
                        )
                        user_states.pop(user_id, None)
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        return
                    
                    await downloading_msg.edit_text(
                        f"✅ **SQLite Database Restored Successfully!** ✅\n\n"
                        f"📄 **File:** {file_name}\n"
                        f"💾 **Size:** {message.document.file_size / 1024:.1f} KB\n"
                        f"🗃️ **Database:** SQLite\n"
                        f"🗄️ **Saved as:** bot.db\n\n"
                        f"📋 **Step 2: Please send Transaction History file (credit_history.db) now:**\n\n"
                        f"⚠️ **keval credit_history.db file accept होगी**"
                    )
                    
                    # Update state for next file
                    user_states[user_id] = {'state': 'waiting_backup_credit_history_db'}
                
                # Clean up downloaded file if it still exists
                if os.path.exists(file_path) and file_path != 'bot.db':
                    try:
                        os.remove(file_path)
                    except:
                        pass
                        
            except Exception as e:
                await downloading_msg.edit_text(
                    f"❌ **Error restoring main database!**\n\n"
                    f"🔧 **Error:** {str(e)}\n"
                    f"📄 **File:** {file_name}\n"
                    f"📊 **Type:** {file_type}\n\n"
                    f"💡 Kuch technical issue hui hai.\n"
                    f"Kripaya valid backup file bheje."
                )
                user_states.pop(user_id, None)
                
                # Clean up on error
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                
        elif state == 'waiting_backup_credit_history_db':
            # Handle credit history database file (SQLite only)
            await downloading_msg.edit_text(
                f"✅ **Transaction History Downloaded!**\n\n"
                f"📄 **File:** {file_name}\n"
                f"💾 **Size:** {message.document.file_size / 1024:.1f} KB\n\n"
                f"🔄 **Processing backup...**"
            )
            
            # Validate SQLite file
            try:
                import sqlite3
                # Test if file is a valid SQLite database
                test_conn = sqlite3.connect(file_path)
                test_cursor = test_conn.cursor()
                # Check if credit_history table exists
                test_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='credit_history'")
                if not test_cursor.fetchone():
                    test_conn.close()
                    await downloading_msg.edit_text(
                        f"❌ **Invalid Credit History Database!**\n\n"
                        f"📄 **File:** {file_name}\n"
                        f"⚠️ File does not contain credit_history table\n\n"
                        f"Kripaya valid credit_history.db file bheje."
                    )
                    user_states.pop(user_id, None)
                    return
                test_conn.close()
                
                # Replace current credit_history.db with uploaded file
                import shutil
                backup_created = False
                
                # Create backup of current file if it exists
                if os.path.exists('credit_history.db'):
                    backup_name = f"credit_history_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                    shutil.copy('credit_history.db', backup_name)
                    backup_created = True
                    os.remove('credit_history.db')  # Remove current database
                
                shutil.move(file_path, 'credit_history.db')  # Move uploaded file
                
                # Calculate total time taken
                backup_start_time = user_state_data.get('backup_start_time')
                total_time = ""
                if backup_start_time:
                    elapsed = datetime.now() - backup_start_time
                    total_time = f"⏱️ **Total Time:** {elapsed.seconds}s"
                
                completion_msg = await downloading_msg.edit_text(
                    f"🎉 **BACKUP RESTORATION COMPLETED!** 🎉\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ **PROCESS SUCCESSFULLY FINISHED**\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📄 **Last File:** {file_name}\n"
                    f"💾 **Size:** {message.document.file_size / 1024:.1f} KB\n"
                    f"🗄️ **Database:** SQLite (Credit History)\n"
                    f"📅 **Completed at:** {datetime.now().strftime('%H:%M:%S')}\n"
                    f"{total_time}\n\n"
                    f"✅ **Restoration Summary:**\n"
                    f"• Main database - ✅ Restored\n"
                    f"• Transaction history - ✅ Restored\n"
                    f"• User data - ✅ Imported\n"
                    f"• Settings - ✅ Applied\n\n"
                    f"🔄 **Backup mode automatically deactivated**\n"
                    f"⚡ **Bot returned to normal operation**\n\n"
                    f"💡 **All data successfully restored from backup!**",
                    reply_markup=get_owner_panel()
                )
                
                # Refresh database connections by recreating engine (for SQLite only)
                try:
                    database_url = os.getenv('DATABASE_URL', 'sqlite:///./bot.db')
                    if database_url.startswith('sqlite'):
                        from database import engine, SessionLocal
                        engine.dispose()  # Close all connections
                        print("🔄 SQLite database connections refreshed after restore")
                except Exception as refresh_error:
                    print(f"⚠️ Database refresh warning: {refresh_error}")
                
                # Clear backup state - automatic exit from backup mode
                user_states.pop(user_id, None)
                
                # Auto-delete completion message after 15 seconds
                try:
                    from message_deletion import track_sent_message
                    await track_sent_message(
                        completion_msg.chat.id,
                        completion_msg.id,
                        user_id,
                        'admin',
                        scheduled_deletion=True,
                        custom_delay=15,
                        context='backup_completed'
                    )
                except:
                    pass
                
            except sqlite3.Error as sqlite_error:
                await downloading_msg.edit_text(
                    f"❌ **Invalid SQLite Database!**\n\n"
                    f"📄 **File:** {file_name}\n"
                    f"🔧 **SQLite Error:** {str(sqlite_error)}\n\n"
                    f"File is corrupted ya invalid format mai hai.\n"
                    f"Kripaya valid .db file bheje."
                )
                user_states.pop(user_id, None)
                # Clean up invalid file
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                        
            except Exception as e:
                await downloading_msg.edit_text(
                    f"❌ **Error restoring transaction history database!**\n\n"
                    f"🔧 **Error:** {str(e)}\n"
                    f"📄 **File:** {file_name}\n\n"
                    f"Kuch technical issue hui hai.\n"
                    f"Kripaya फिर se try kare."
                )
                user_states.pop(user_id, None)
                # Clean up on error
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
    
    except Exception as e:
        print(f"Error handling backup file upload: {e}")
        await message.reply(
            f"❌ **Error processing backup file!**\n\n"
            f"kuch technical issue hui hai.\n"
            f"Kripaya फिर se try kare."
        )
        user_states.pop(user_id, None)


async def check_bot_reactivation():
    """Check if bot should be reactivated based on time"""
    while True:
        try:
            db = SessionLocal()
            try:
                bot_status = db.query(BotStatus).first()
                if (bot_status and not bot_status.is_active and
                    bot_status.deactivated_until and
                    datetime.utcnow() >= bot_status.deactivated_until):

                    # Reactivate bot
                    bot_status.is_active = True
                    bot_status.deactivated_reason = None
                    bot_status.deactivated_until = None
                    bot_status.updated_at = datetime.utcnow()
                    db.commit()

                    print("Bot automatically reactivated!")
            finally:
                db.close()
        except Exception as e:
            print(f"Reactivation check error: {e}")

        await asyncio.sleep(60)  # Check every minute

def main():
    """Main function to start the bot with optimized database initialization"""
    try:
        # Check if database initialization is needed
        print("Checking database...")
        if create_tables():
            print("Database initialized successfully")
        else:
            print("Database check completed")
            
        # Initialize credit history database
        print("Initializing credit history database...")
        create_credit_history_tables()
        print("Credit history database initialized successfully")
    except Exception as e:
        print(f"Database initialization error: {e}")
        print("Continuing with bot startup...")

    print("Starting TTS Bot...")

    try:
        # Start background tasks
        loop = asyncio.get_event_loop()
        loop.create_task(check_bot_reactivation())

        # Load connected channel from database
        loop.run_until_complete(load_connected_channel())
        
        # Initialize message deletion service
        print("🧹 Initializing message deletion service...")
        deletion_service = initialize_deletion_service(app)
        loop.run_until_complete(deletion_service.start_deletion_service())
        print("✅ Message deletion service started successfully")
        
        # Start database backup scheduler if channel is available
        target_channel = connected_channel_id or CHANNEL_ID
        if target_channel:
            loop.create_task(database_backup_scheduler())
            print(f"🗄️ Database backup scheduler started - backing up every 10 minutes to channel")
            print(f"📍 Using channel: {'Runtime Connected' if connected_channel_id else 'Environment Variable'} ({target_channel})")
        else:
            print("⚠️ No channel configured/connected, database backup disabled")
            print("💡 Add bot to channel and use /connect command to enable backups")

        app.run()
    except Exception as e:
        print(f"Bot startup error: {e}")
        raise e

if __name__ == "__main__":
    main()
