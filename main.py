import os
import asyncio
import sqlite3
import shutil
from datetime import datetime, timedelta
from pyrogram.client import Client
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery
from sqlalchemy.orm import Session
from database import create_tables, get_db, User, TTSRequest, LinkShortner, BotSettings, BotStatus, BotRating, CreditTransaction, ReferralSystem, SessionLocal, get_setting, update_setting, QRCodeSettings # Import QRCodeSettings
from keyboards import (
    get_owner_panel, get_user_panel, get_about_keyboard,
    get_back_to_owner, get_back_to_user, get_tts_languages,
    get_users_panel, get_shortner_panel, get_shortner_add_panel, get_shortner_info_panel,
    get_voice_selection, get_voice_selection_owner,
    get_settings_panel, get_credits_settings_panel, get_settings_confirmation_panel,
    get_rating_panel, get_deactivate_confirmation_panel, get_user_credit_panel,
    get_support_contact_panel, get_payment_cancel_panel, get_payment_verification_panel, get_payment_settings_panel, get_qr_management_panel,
    get_referral_panel, get_referral_share_panel, get_owner_referral_panel, get_simple_referral_panel, get_free_credit_referral_panel
)
from tts_service import TTSService
from referral_system import get_user_referral_link, get_user_referral_stats, process_referral

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

# Database backup function
async def create_and_send_db_backup():
    """Create database backup and send to channel every 10 minutes"""
    try:
        # Use connected channel instead of environment variable
        target_channel = connected_channel_id or CHANNEL_ID
        if not target_channel:
            print("⚠️ No channel connected for backup, skipping database backup")
            return

        # Create backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"tts_bot_backup_{timestamp}.db"

        # Copy database file
        try:
            # Check if database file exists
            db_file = 'bot.db'
            if not os.path.exists(db_file):
                print(f"⚠️ Database file {db_file} not found, skipping backup")
                return
                
            shutil.copy(db_file, backup_filename)
            print(f"📁 Database backup created: {backup_filename}")

            # Send to channel
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
                
                await app.send_document(
                    target_id,
                    backup_filename,
                    caption=f"🗄️ **Database Backup**\n\n"
                            f"📅 Date: {datetime.now().strftime('%d/%m/%Y')}\n"
                            f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}\n"
                            f"📊 Auto-backup every 10 minutes\n\n"
                            f"🔒 Keep this backup secure!"
                )
                print(f"✅ Database backup sent to channel successfully!")

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
                            f"कृपया channel connection check करें!"
                        )
                except Exception as owner_notify_error:
                    print(f"❌ Failed to notify owner about backup error: {owner_notify_error}")

        except Exception as backup_error:
            print(f"❌ Error creating backup: {backup_error}")

        # Clean up backup file
        try:
            os.remove(backup_filename)
        except:
            pass

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
        transaction = CreditTransaction(
            user_id=user_id,
            amount=float(amount),
            transaction_type=transaction_type[:50],  # Limit length to prevent overflow
            description=description[:200] if description else None  # Limit description length
        )
        db.add(transaction)
        db.commit()
        return True
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
                    from referral_system import get_referrer_details
                    referrer_name = get_referrer_details(param)
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
            # Better channel ID validation and conversion
            if target_channel.startswith('-100'):
                target_id = int(target_channel)
            elif target_channel.startswith('-'):
                target_id = int(target_channel)
            elif target_channel.startswith('@'):
                target_id = target_channel
            else:
                target_id = f"@{target_channel}"
                
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
                    f"🙏 **धन्यवाद मुझे इस {chat_info.type} में add करने के लिए!** 🙏\n\n"
                    f"🏷️ **{chat_info.type.title()}:** {chat_info.title}\n"
                    f"🆔 **ID:** `{chat_info.id}`\n"
                    f"👥 **Members:** {chat_info.members_count or 'Unknown'}\n\n"
                    f"📋 **Instructions for Owner:**\n"
                    f"🔹 अब owner को इस channel में `/connect` command send करना है\n"
                    f"🔹 तब मैं इस channel को notifications के लिए use करूंगा\n"
                    f"🔹 New users, payments, और database backups यहाँ आएंगे\n\n"
                    f"⚠️ **Note:** केवल Owner ही `/connect` command use कर सकते हैं"
                )
                
                # Notify owner about new channel addition
                try:
                    if OWNER_ID and OWNER_ID != 0:
                        await app.send_message(
                            OWNER_ID,
                            f"🎉 **Bot को नए channel में add किया गया!**\n\n"
                            f"🏷️ **{chat_info.type.title()}:** {chat_info.title}\n"
                            f"🆔 **ID:** `{chat_info.id}`\n"
                            f"👥 **Members:** {chat_info.members_count or 'Unknown'}\n\n"
                            f"💡 **Action Required:**\n"
                            f"📱 उस channel में जाकर `/connect` command send करें\n"
                            f"🔗 तब channel notifications के लिए connected हो जाएगा"
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
            await message.reply("❌ केवल Owner ही इस command का use कर सकते हैं!")
            return
        
        # Get current chat info
        chat_info = message.chat
        
        # Check if it's a group or channel
        if chat_info.type not in ["group", "supergroup", "channel"]:
            await message.reply("❌ यह command केवल groups/channels में use करें!")
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
            f"📋 **अब यह channel receive करेगा:**\n"
            f"🔹 नए user join notifications\n"
            f"🔹 Database backups (हर 10 minutes)\n"
            f"🔹 Payment request notifications\n"
            f"🔹 System alerts और updates\n\n"
            f"🚀 **Channel connection active है!**"
        )
        
        # Notify in private message too
        try:
            await app.send_message(
                OWNER_ID,
                f"✅ **Channel Connected Successfully!**\n\n"
                f"🏷️ **{chat_info.type.title()}:** {chat_info.title}\n"
                f"🆔 **ID:** `{chat_info.id}`\n\n"
                f"अब सभी bot notifications इस channel पर आएंगे। 🎉"
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
        await message.reply("❌ **Commands को private message में भेजें, channel में नहीं!**\n\nBot को private message में `/test_channel` command send करें।")
        return
        
    user_id = message.from_user.id
    
    if user_id != OWNER_ID:
        await message.reply("❌ This command is for owner only.")
        return
    
    target_channel = connected_channel_id or CHANNEL_ID
    if not target_channel:
        await message.reply("❌ **No Channel Connected!**\n\n📋 **Options:**\n🔹 Bot को channel में add करें\n🔹 Channel में `/connect` command send करें\n🔹 या CHANNEL_ID environment variable set करें")
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
            f"💡 **या bot को channel में add करके `/connect` command use करें!**"
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
                        f"✅ आपको {result['referrer_name']} ने refer किया है\n"
                        f"🎁 **आपको मिले:** {result['referred_bonus']} credits\n"
                        f"💰 **{result['referrer_name']} को मिले:** {result['referrer_bonus']} credits\n\n"
                        f"🚀 अब आप bot use कर सकते हैं अपने bonus credits के साथ",
                        reply_markup=get_user_panel()
                    )

                    # Send notification to referrer
                    try:
                        await app.send_message(
                            result['referrer_id'],
                            f"🎉 **नया Referral Success**\n\n"
                            f"👤 **नया User:** {result['referred_name']}\n"
                            f"💰 **आपको मिले:** {result['referrer_bonus']} credits\n"
                            f"🎁 **उन्हें मिले:** {result['referred_bonus']} credits\n\n"
                            f"📈 आपकी referral link से यह user आया है\n"
                            f"🙏 हमारे community को बढ़ाने के लिए धन्यवाद"
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
                        f"कृपया कुछ समय बाद try करें।"
                    )
                    return
                elif not bot_status.deactivated_until:
                    await message.reply(
                        f"🤖 **Bot Deactivated**\n\n"
                        f"📝 Reason: {bot_status.deactivated_reason or 'Maintenance'}\n\n"
                        f"कृपया कुछ समय बाद try करें।"
                    )
                    return
        finally:
            db.close()

    # Check if user is owner
    if user_id == OWNER_ID:
        await message.reply(
            "🌟═══════════════════════🌟\n"
            "👑 **MASTER CONTROL PANEL** 👑\n"
            "🌟═══════════════════════🌟\n\n"
            "🎯 **Ready to take control?** ⚡\n"
            "💫 नीचे दिए गए powerful options से अपनी पसंद चुनें:\n"
            "🔥 **Your command is my wish** 🔥",
            reply_markup=get_owner_panel()
        )
    else:
        # Check user status
        if user.is_banned == True:
            await message.reply("❌ आप इस bot का इस्तेमाल नहीं कर सकते।")
            return

        if user.is_active == False:
            await message.reply("⚠️ आपका account deactive है। Admin से संपर्क करें।")
            return

        # Check if new user (joined today and this is first interaction)
        is_new_user = (user.join_date.date() == datetime.utcnow().date() and
                      abs((user.last_active - user.join_date).total_seconds()) < 60)

        if is_new_user:
            # Send new user notification to channel
            await send_new_user_notification(message, user)
            
            # New user - show about page
            await message.reply(
                "🎉 **Welcome to TTS Bot!** 🎉\n\n"
                "यह एक advanced Text-to-Speech bot है जो आपके text को natural voice में convert करता है।\n\n"
                "**Features:**\n"
                "🎤 Multiple voice types\n"
                "⚡ Fast conversion\n"
                "🆓 Free credits for new users\n"
                "💰 Credit system\n\n"
                "आपको **10 free credits** मिले हैं!\n"
                "हर word के लिए 0.05 credit charge होता है।",
                reply_markup=get_about_keyboard()
            )
        else:
            # Existing user - show user panel
            await message.reply(
                f"🌟 **स्वागत है** {user.first_name}! 🌟\n\n"
                f"💎 **आपके Credits:** {user.credits}\n"
                f"🚀 **Ready for TTS Magic?** ✨\n\n"
                f"🎯 नीचे दिए गए options में से choose करें:",
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
            "🌟═══════════════════════🌟\n"
            "👑 **MASTER CONTROL PANEL** 👑\n"
            "🌟═══════════════════════🌟\n\n"
            "🎯 **Ready to take control?** ⚡\n"
            "💫 नीचे दिए गए powerful options से अपनी पसंद चुनें:\n"
            "🔥 **Your command is my wish** 🔥",
            reply_markup=get_owner_panel()
        )

    elif data == "owner_tts":
        await callback_query.edit_message_text(
            "🎤 **Owner TTS**\n\n"
            "कृपया अपनी पसंदीदा voice select करें:",
            reply_markup=get_voice_selection_owner()
        )

    elif data == "owner_users":
        await callback_query.edit_message_text(
            "👥 **User Management**\n\n"
            "यहां से आप users को manage कर सकते हैं:",
            reply_markup=get_users_panel()
        )

    elif data == "owner_broadcast":
        user_states[user_id] = UserState.WAITING_BROADCAST_TEXT
        await callback_query.edit_message_text(
            "📢 **Broadcast Message**\n\n"
            "कृपया वह message भेजें जो आप सभी users को send करना चाहते हैं:\n\n"
            "**Available Placeholders:**\n"
            "• `{first_name}` - User का नाम\n"
            "• `{last_name}` - User का surname\n"
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
            "📊 **Gathering Comprehensive Bot Statistics...**\n\n"
            "🔄 Please wait while we analyze all data..."
        )
        
        # Gather all statistics with error handling
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
            except:
                total_payments = confirmed_payments = pending_payments = total_revenue = 0
            
            # Referral statistics
            total_referrals = db.query(ReferralSystem).filter(ReferralSystem.is_claimed == True).count()
            referral_credits_distributed = db.query(func.sum(ReferralSystem.credits_earned)).scalar() or 0
            
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
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 **Bot Information:**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔋 **Status:** {bot_active_status}\n"
                f"⏱️ **Uptime:** {uptime_text}\n"
                f"💾 **Database Size:** {db_size}\n"
                f"📅 **Report Date:** {datetime.utcnow().strftime('%d/%m/%Y %H:%M UTC')}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👥 **USER STATISTICS:**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 **Total Users:** {total_users:,}\n"
                f"✅ **Active Users:** {active_users:,}\n"
                f"🚫 **Banned Users:** {banned_users:,}\n"
                f"📊 **Active Rate:** {(active_users/total_users*100):.1f}% of total\n\n"
                f"🔥 **ACTIVITY METRICS:**\n"
                f"📅 **Today Active:** {today_users:,} users\n"
                f"📊 **This Week:** {week_users:,} users\n"
                f"⚡ **Engagement:** {(today_users/total_users*100):.1f}% daily activity\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎤 **TTS USAGE STATISTICS:**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Total Requests:** {total_tts_requests:,}\n"
                f"📝 **Words Processed:** {total_words_processed:,}\n"
                f"📅 **Today's TTS:** {today_tts:,}\n"
                f"📊 **This Week:** {week_tts:,}\n"
                f"📈 **Avg per User:** {avg_tts_per_user:.1f} requests\n"
                f"📝 **Avg Words/TTS:** {avg_words_per_tts:.0f} words\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 **FINANCIAL OVERVIEW:**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💳 **Total Payments:** {total_payments:,}\n"
                f"✅ **Confirmed:** {confirmed_payments:,}\n"
                f"⏳ **Pending:** {pending_payments:,}\n"
                f"💰 **Total Revenue:** ₹{total_revenue:,.0f}\n"
                f"📊 **Success Rate:** {(confirmed_payments/total_payments*100):.1f if total_payments > 0 else 0}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💎 **CREDIT SYSTEM:**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 **Credits Given:** {total_credits_given:,.0f}\n"
                f"📉 **Credits Used:** {total_credits_used:,.0f}\n"
                f"💹 **Net Flow:** {(total_credits_given - total_credits_used):+.0f}\n"
                f"🎁 **Referral Credits:** {referral_credits_distributed:.0f}\n"
                f"👥 **Total Referrals:** {total_referrals:,}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 **PERFORMANCE INSIGHTS:**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔥 **User Retention:** {(week_users/total_users*100):.1f}% weekly\n"
                f"⚡ **Daily Growth:** +{today_users - week_users + today_users if week_users > 0 else 0} new today\n"
                f"💡 **TTS Adoption:** {(total_tts_requests > 0)}, {total_users} users tried TTS\n"
                f"🎯 **Revenue/User:** ₹{(total_revenue/confirmed_payments):.0f if confirmed_payments > 0 else 0} avg\n"
                f"{top_users_text}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
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
                    f"📊 कुछ technical issue हुई है statistics gather करते समय।\n\n"
                    f"**Error Details:**\n"
                    f"`{str(e)[:100]}...`\n\n"
                    f"🔧 कृपया बाद में try करें या database check करें।\n"
                    f"📱 अगर problem persist करे तो code review करें।",
                    reply_markup=get_back_to_owner()
                )
            except Exception as edit_error:
                print(f"Failed to edit message with error: {edit_error}")
                try:
                    await callback_query.answer("Statistics loading failed. Check console for details.", show_alert=True)
                except:
                    pass

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
                    "❌ कोई link shortner add नहीं है।",
                    reply_markup=get_shortner_add_panel()
                )
        finally:
            db.close()

    elif data == "owner_referrals":
        await callback_query.edit_message_text(
            "👥 **Referral Management**\n\n"
            "यहां से आप referral system को manage कर सकते हैं:",
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
            "Bot की सभी settings यहां manage करें:",
            reply_markup=get_settings_panel()
        )

    elif data == "settings_credits":
        await callback_query.edit_message_text(
            "💰 **Credits Settings**\n\n"
            "यहां से आप credit system के settings manage कर सकते हैं:",
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
                    "कृपया deactivation का reason enter करें:",
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
                    "Bot अब सभी users के लिए active है।",
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
                    "Bot को successfully shutdown कर दिया गया।\n"
                    "सभी users के लिए bot अब unavailable है।",
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
                    "Bot को successfully start कर दिया गया।\n"
                    "सभी users के लिए bot अब available है।",
                    reply_markup=get_back_to_owner()
                )
        finally:
            db.close()

    elif data == "settings_rating":
        user_states[user_id] = UserState.WAITING_RATING_COUNT
        await callback_query.edit_message_text(
            "⭐ **Add Fake Ratings**\n\n"
            "कितने fake ratings add करना चाहते हैं?\n"
            "कृपया number enter करें:",
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
            from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            ok_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👌 OK", callback_data="back_to_owner")]
            ])

            await callback_query.edit_message_text(
                f"✅ **Bot Deactivated Successfully!**\n\n"
                f"📝 Reason: {reason}\n"
                f"{time_text}\n\n"
                f"Bot अब users के लिए unavailable है।\n"
                f"(Owner access बना रहेगा)",
                reply_markup=ok_keyboard
            )
        finally:
            db.close()

        user_states.pop(user_id, None)

    # User callbacks
    elif data == "start_bot":
        await callback_query.edit_message_text(
            f"🌟 **स्वागत है** {callback_query.from_user.first_name}! 🌟\n\n"
            f"💎 **आपके Credits:** 10\n"
            f"🚀 **Ready for TTS Magic?** ✨\n\n"
            f"🎯 नीचे दिए गए options में से choose करें:",
            reply_markup=get_user_panel()
        )

    elif data == "back_to_user":
        user = get_user_from_db(user_id)
        await callback_query.edit_message_text(
            f"🌟 **स्वागत है** {callback_query.from_user.first_name}! 🌟\n\n"
            f"💎 **आपके Credits:** {user.credits}\n"
            f"🚀 **Ready for TTS Magic?** ✨\n\n"
            f"🎯 नीचे दिए गए options में से choose करें:",
            reply_markup=get_user_panel()
        )

    elif data == "user_tts":
        await callback_query.edit_message_text(
            "🎤 **Text to Speech**\n\n"
            "कृपया अपनी पसंदीदा voice select करें:",
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
                "कृपया अपना text भेजें (Maximum 3000 characters):\n\n"
                "⭐ **Owner:** Free unlimited access",
                reply_markup=get_back_to_owner()
            )
        else:
            await callback_query.edit_message_text(
                f"🎤 **TTS - {voice_names.get(voice_type, 'Unknown')}**\n\n"
                "कृपया अपना text भेजें (Maximum 3000 characters):\n\n"
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
            last_request_date = last_request.timestamp.strftime('%d/%m/%Y %H:%M') if last_request else "कभी नहीं"
            
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
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 **नाम:** {callback_query.from_user.first_name or 'User'} {callback_query.from_user.last_name or ''}\n"
                f"👤 **Username:** @{callback_query.from_user.username or 'None'}\n"
                f"🆔 **User ID:** `{user_id}`\n"
                f"📅 **Join Date:** {user.join_date.strftime('%d/%m/%Y %H:%M')}\n"
                f"📈 **Days Active:** {days_since_join} days\n"
                f"🕐 **Last Active:** {user.last_active.strftime('%d/%m/%Y %H:%M')}\n"
                f"🏆 **Membership:** {membership}\n"
                f"📊 **Status:** {account_status}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 **Credit Information** 💰\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💎 **Current Balance:** {user.credits:.2f} credits\n"
                f"📈 **Total Earned:** {total_credits_earned:.2f} credits\n"
                f"📉 **Total Spent:** {total_credits_spent:.2f} credits\n"
                f"💸 **TTS Usage:** {total_credits_used:.2f} credits\n"
                f"🎁 **Referral Earnings:** {referral_credits_earned:.2f} credits\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎤 **TTS Statistics** 🎤\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Total Requests:** {user_requests}\n"
                f"📝 **Average Words:** {avg_words} per request\n"
                f"🕒 **Last TTS Request:** {last_request_date}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👥 **Referral Information** 👥\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
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
            "यहां से आप अपने credits manage कर सकते हैं:",
            reply_markup=get_user_credit_panel()
        )

    elif data == "free_credit":
        # Now shows referral link instead of free credit link
        try:
            referral_link, referral_code = get_user_referral_link(user_id)

            await callback_query.edit_message_text(
                f"🆓 **Free Credits - Referral System**\n\n"
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
            print(f"Error in free credit referral handler: {error}")
            try:
                await callback_query.edit_message_text(
                    f"🆓 **Free Credits**\n\n"
                    f"❌ Service temporarily unavailable!\n"
                    f"कृपया बाद में try करें या admin से contact करें।",
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
        await callback_query.edit_message_text(
            f"💳 **Buy Credits**\n\n"
            f"💰 **Rate:** ₹1 = {payment_rate} credits\n"
            f"📊 **Minimum:** ₹{min_amount} ({min_credits} credits)\n"
            f"📊 **Maximum:** ₹{max_amount} ({max_credits} credits)\n\n"
            f"कृपया amount enter करें (₹{min_amount} - ₹{max_amount}):",
            reply_markup=get_back_to_user()
        )

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
                    f"कृपया बाद में try करें या admin से contact करें।",
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
                    recent_referrals_text += f"... और {len(stats['referred_users']) - 3} referrals"
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
                    await client.send_message(
                        payment.user_id,
                        f"✅ **Payment Confirmed!**\n\n"
                        f"💳 Amount: ₹{payment.amount}\n"
                        f"💰 Credits Added: {payment.credits_to_add}\n"
                        f"💎 Current Balance: {user.credits:.0f} credits\n"
                        f"🆔 Transaction ID: {payment.transaction_id}\n"
                        f"📅 Verified: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}\n\n"
                        f"🎉 Thank you for your purchase!\n"
                        f"🎆 आप अब TTS का use कर सकते हैं!",
                        reply_markup=get_user_panel()
                    )
                    print(f"✅ Payment confirmation sent to user {payment.user_id}")
                except Exception as notify_error:
                    print(f"⚠️ Error notifying user about payment confirmation: {notify_error}")

                await callback_query.edit_message_text(
                    f"✅ **Payment Confirmed Successfully!**\n\n"
                    f"👤 User ID: {payment.user_id}\n"
                    f"💰 Amount: ₹{payment.amount}\n"
                    f"💎 Credits Added: {payment.credits_to_add}\n"
                    f"🆔 Transaction ID: {payment.transaction_id}\n"
                    f"📅 Processed: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}\n\n"
                    f"✅ User has been notified and credits added!",
                    reply_markup=get_back_to_owner()
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
                        f"😔 आपकी payment request cancel हो गई है।\n"
                        f"👤 यदि आपको लगता है यह mistake है तो owner से contact करें।",
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

    elif data == "contact_support":
        await callback_query.edit_message_text(
            "📞 **Contact Support**\n\n"
            "Support के लिए owner से संपर्क करें:",
            reply_markup=get_support_contact_panel()
        )

    elif data == "i_know_that":
        user = get_user_from_db(user_id)
        await callback_query.edit_message_text(
            f"🌟 **स्वागत है** {callback_query.from_user.first_name}! 🌟\n\n"
            f"💎 **आपके Credits:** {user.credits}\n"
            f"🚀 **Ready for TTS Magic?** ✨\n\n"
            f"🎯 नीचे दिए गए options में से choose करें:",
            reply_markup=get_user_panel()
        )

    elif data == "user_help":
        # Get user's current info for personalized help
        user = get_user_from_db(user_id)
        
        await callback_query.edit_message_text(
            f"❓ **Complete Help Guide** ❓\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎤 **TTS Usage Guide:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"1️⃣ 🎤 **Start TTS** button दबाएं\n"
            f"2️⃣ 🎵 अपनी पसंदीदा voice select करें\n"
            f"3️⃣ 📝 Text type करें (max 3000 characters)\n"
            f"4️⃣ 🎧 Audio file receive करें\n"
            f"5️⃣ ⭐ Quality rate करें\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 **Credit Information:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 **Your Current Balance:** {user.credits:.2f}\n"
            f"💸 **Per Word Cost:** 0.05 credits\n"
            f"🎁 **Free Credits:** Referral system\n"
            f"💳 **Buy Credits:** Payment options available\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎵 **Voice Options:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👨 **Male Voices:** Deep, Calm, Professional, Energetic, Warm\n"
            f"👩 **Female Voices:** Sweet, Clear, Soft, Bright, Melodic\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 **Pro Tips:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 Use punctuation for natural pauses\n"
            f"🔹 Break long text into smaller chunks\n"
            f"🔹 Try different voices for best results\n"
            f"🔹 Rate audio quality to help us improve\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 **Available Commands:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 `/start` - Bot को शुरू करें\n"
            f"❌ `/cancel` - Current operation cancel करें\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆘 **Need Support?**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📞 Contact admin for technical issues\n"
            f"💬 Report bugs or suggestions\n"
            f"🎯 Join our community for updates\n\n"
            f"✨ **Happy TTS-ing!** ✨",
            reply_markup=get_back_to_user()
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
            "ℹ️ **About TTS Bot**\n\n"
            "🤖 **Version:** 1.0.0\n"
            "👨‍💻 **Developer:** @YourUsername\n"
            "🎤 **Features:** Multi-language TTS\n"
            "⚡ **Speed:** Fast conversion\n"
            "🆓 **Credits:** Free for new users\n"
            f"{rating_text}\n"
            "यह bot Edge TTS का इस्तेमाल करता है।",
            reply_markup=get_back_to_user()
        )

    # Feedback callbacks
    elif data.startswith("feedback_"):
        if data == "feedback_back":
            # Back to voice selection
            await callback_query.edit_message_text(
                "🎤 **Voice Selection**\n\n"
                "कृपया अपनी पसंदीदा voice select करें:",
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

                await callback_query.answer(f"धन्यवाद! आपकी {rating}⭐ rating मिल गई।", show_alert=True)

                # Redirect to voice selection
                await callback_query.edit_message_text(
                    "🎤 **Voice Selection**\n\n"
                    "कृपया अपनी पसंदीदा voice select करें:",
                    reply_markup=get_voice_selection() if user_id != OWNER_ID else get_voice_selection_owner()
                )
            except Exception as e:
                print(f"Feedback storage error: {e}")
                await callback_query.answer("धन्यवाद! आपकी feedback मिल गई।", show_alert=True)
                await callback_query.edit_message_text(
                    "🎤 **Voice Selection**\n\n"
                    "कृपया अपनी पसंदीदा voice select करें:",
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
                "कृपया अपना text भेजें (Maximum 3000 characters):\n\n"
                "⭐ **Owner:** Free unlimited access",
                reply_markup=get_back_to_owner()
            )
        else:
            await callback_query.edit_message_text(
                f"🎤 **TTS - {lang_names.get(lang, 'Unknown')}**\n\n"
                "कृपया अपना text भेजें (Maximum 3000 characters):\n\n"
                "💰 **Charges:** 0.05 credits per word",
                reply_markup=get_back_to_user()
            )

    # New Owner Panel Features
    elif data == "give_credit":
        user_states[user_id] = UserState.WAITING_GIVE_CREDIT_USER_ID
        await callback_query.edit_message_text(
            "💰 **Give Credit to User**\n\n"
            "कृपया user ID enter करें:",
            reply_markup=get_back_to_owner()
        )

    elif data == "give_credit_all":
        user_states[user_id] = UserState.WAITING_GIVE_CREDIT_ALL_AMOUNT
        await callback_query.edit_message_text(
            "💰 **Give Credit to All Users**\n\n"
            "कृपया credit amount enter करें जो सभी users को देना है:",
            reply_markup=get_back_to_owner()
        )

    elif data == "ban_user":
        user_states[user_id] = UserState.WAITING_BAN_USER_ID
        await callback_query.edit_message_text(
            "🚫 **Ban User**\n\n"
            "कृपया user ID enter करें जिसे ban करना है:",
            reply_markup=get_back_to_owner()
        )

    elif data == "unban_user":
        user_states[user_id] = UserState.WAITING_UNBAN_USER_ID
        await callback_query.edit_message_text(
            "✅ **Unban User**\n\n"
            "कृपया user ID enter करें जिसे unban करना है:",
            reply_markup=get_back_to_owner()
        )

    elif data == "user_specific_info":
        user_states[user_id] = UserState.WAITING_USER_INFO_ID
        await callback_query.edit_message_text(
            "🔍 **Get User Info**\n\n"
            "कृपया User ID या Username enter करें:\n\n"
            "Example: 123456789 या @username",
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
                    "❌ कोई link shortner नहीं मिला।",
                    reply_markup=get_back_to_owner()
                )
        finally:
            db.close()

    elif data == "add_shortner":
        user_states[user_id] = UserState.WAITING_SHORTNER_DOMAIN
        await callback_query.edit_message_text(
            "➕ **Add Link Shortner**\n\n"
            "कृपया domain name enter करें (जैसे: short.ly):",
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
                    f"Domain {shortner.domain} को successfully remove कर दिया गया।",
                    reply_markup=get_back_to_owner()
                )
            else:
                await callback_query.edit_message_text(
                    "❌ कोई active link shortner नहीं मिला।",
                    reply_markup=get_back_to_owner()
                )
        finally:
            db.close()

    # Settings panel callbacks
    elif data == "settings_welcome_credit":
        current_welcome_credit = get_setting("welcome_credit", default=10.0)
        await callback_query.edit_message_text(
            f"⚙️ **Welcome Credit Settings**\n\n"
            f"वर्तमान में नए users को **{current_welcome_credit}** credits मिलते हैं।\n\n"
            "नए credit amount enter करें:",
            reply_markup=get_settings_confirmation_panel("welcome_credit")
        )
        user_states[user_id] = UserState.WAITING_WELCOME_CREDIT

    elif data == "settings_tts_charge":
        current_tts_charge = get_setting("tts_charge", default=0.05)
        await callback_query.edit_message_text(
            f"⚙️ **TTS Charge Settings**\n\n"
            f"वर्तमान में प्रति word **{current_tts_charge}** credits charge होते हैं।\n\n"
            "नया charge amount enter करें (प्रति word):",
            reply_markup=get_settings_confirmation_panel("tts_charge")
        )
        user_states[user_id] = UserState.WAITING_TTS_CHARGE

    elif data == "settings_earn_credit":
        current_earn_credit = get_setting("earn_credit", default=0.01)
        await callback_query.edit_message_text(
            f"⚙️ **Earn Credit Settings**\n\n"
            f"वर्तमान में short link process करने पर **{current_earn_credit}** credits मिलते हैं।\n\n"
            "नया earn amount enter करें:",
            reply_markup=get_settings_confirmation_panel("earn_credit")
        )
        user_states[user_id] = UserState.WAITING_EARN_CREDIT

    elif data == "settings_payment":
        min_amount = get_setting("min_payment_amount", default=10.0)
        max_amount = get_setting("max_payment_amount", default=100.0)
        payment_rate = get_setting("payment_rate", default=10.0)

        await callback_query.edit_message_text(
            f"💳 **Payment Settings**\n\n"
            f"💰 **Minimum Amount:** ₹{min_amount}\n"
            f"💰 **Maximum Amount:** ₹{max_amount}\n"
            f"💎 **Credit Rate:** {payment_rate} credits per ₹1\n\n"
            "कौन सी setting change करना चाहते हैं?",
            reply_markup=get_payment_settings_panel()
        )

    elif data == "settings_min_payment":
        current_min = get_setting("min_payment_amount", default=10.0)
        await callback_query.edit_message_text(
            f"⚙️ **Minimum Payment Amount**\n\n"
            f"वर्तमान minimum amount: **₹{current_min}**\n\n"
            "नया minimum amount enter करें (rupees में):",
            reply_markup=get_settings_confirmation_panel("min_payment")
        )
        user_states[user_id] = UserState.WAITING_MIN_PAYMENT

    elif data == "settings_max_payment":
        current_max = get_setting("max_payment_amount", default=100.0)
        await callback_query.edit_message_text(
            f"⚙️ **Maximum Payment Amount**\n\n"
            f"वर्तमान maximum amount: **₹{current_max}**\n\n"
            "नया maximum amount enter करें (rupees में):",
            reply_markup=get_settings_confirmation_panel("max_payment")
        )
        user_states[user_id] = UserState.WAITING_MAX_PAYMENT

    elif data == "settings_payment_rate":
        current_rate = get_setting("payment_rate", default=10.0)
        await callback_query.edit_message_text(
            f"⚙️ **Payment Credit Rate**\n\n"
            f"वर्तमान rate: **{current_rate} credits per ₹1**\n\n"
            "नया credit rate enter करें (per rupee):",
            reply_markup=get_settings_confirmation_panel("payment_rate")
        )
        user_states[user_id] = UserState.WAITING_PAYMENT_RATE

    # QR Code Settings Callbacks
    elif data == "settings_qr_code":
        await callback_query.edit_message_text(
            "🖼️ **QR Code Settings**\n\n"
            "यहां आप QR code और payment details manage कर सकते हैं:",
            reply_markup=get_qr_management_panel() # QR code management panel
        )

    elif data == "update_qr_code_url":
        user_states[user_id] = UserState.WAITING_QR_CODE_URL
        await callback_query.edit_message_text(
            "🖼️ **Update QR Code URL**\n\n"
            "कृपया QR code का URL enter करें:",
            reply_markup=get_back_to_owner()
        )

    elif data == "update_payment_details":
        user_states[user_id] = UserState.WAITING_PAYMENT_NUMBER
        await callback_query.edit_message_text(
            "📱 **Update Payment Details**\n\n"
            "कृपया payment number (UPI ID or phone number) enter करें:",
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
                    "कृपया पहले settings में जाकर QR code और payment details set करें।",
                    reply_markup=get_back_to_owner()
                )
        finally:
            db.close()


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
                await message.reply("❌ Text too long! Maximum 3000 characters allowed.")
                user_states.pop(user_id, None)
                return

            if len(text) == 0:
                await message.reply("❌ Please send some text to convert to speech.")
                user_states.pop(user_id, None)
                return

            # Calculate cost based on word count
            word_count = len(text.split())
            credits_needed = word_count * 0.05

            # Check user credits (only for non-owners)
            if user_id != OWNER_ID:
                user = get_user_from_db(user_id)
                if user.credits < credits_needed:
                    await message.reply(f"❌ Insufficient credits! You need {credits_needed:.2f} credits but have {user.credits:.2f}")
                    user_states.pop(user_id, None)
                    return

                # Show processing message
                processing_msg = await message.reply(f"🔄 Processing your request...\n💰 Cost: {credits_needed:.2f} credits ({word_count} words)")
            else:
                # Owner gets free access
                processing_msg = await message.reply(f"🔄 Processing your request...\n⭐ Owner: Free unlimited access")

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
                await message.reply_audio(
                    audio_data,
                    caption=f"🎤 **Text:** {text[:50]}{'...' if len(text) > 50 else ''}\n🌐 **Language:** {lang.upper()}\n{'💰 **Cost:** ' + str(credits_needed) + ' credits' if user_id != OWNER_ID else '⭐ **Owner Access**'}",
                    title="TTS Audio"
                )

                # Wait 2 seconds then show feedback buttons
                await asyncio.sleep(2)

                from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
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

                await message.reply("⭐ **Rate this audio quality:**", reply_markup=feedback_keyboard)

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
            await message.reply(f"💰 User ID: {target_user_id}\n\nकृपया credit amount enter करें:")
        except ValueError:
            await message.reply("❌ Invalid user ID! कृपया valid number enter करें।")
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
            await message.reply("❌ Invalid amount! कृपया valid number enter करें।")
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
            await message.reply("❌ Invalid amount! कृपया valid number enter करें।")
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
            await message.reply("❌ Invalid user ID! कृपया valid number enter करें।")
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
            await message.reply("❌ Invalid user ID! कृपया valid number enter करें।")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_SHORTNER_DOMAIN and user_id == OWNER_ID:
        domain = message.text.strip()
        user_states[user_id] = {'state': UserState.WAITING_SHORTNER_API, 'domain': domain}
        await message.reply(f"🌐 Domain: {domain}\n\nकृपया API key enter करें:")

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
            from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
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
                    f"User ID या Username '{user_input}' database में नहीं मिला।\n\n"
                    f"कृपया valid User ID या Username enter करें।",
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
                await message.reply("❌ Credit amount नहीं हो सकती negative!")
                user_states.pop(user_id, None)
                return

            update_setting("welcome_credit", credit_amount, "Credits given to new users")
            await message.reply(
                f"✅ **Welcome Credit Updated!**\n\n"
                f"नए users को अब {credit_amount} credits मिलेंगे।",
                reply_markup=get_back_to_owner()
            )
        except ValueError:
            await message.reply("❌ Invalid amount! कृपया valid number enter करें।")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_TTS_CHARGE and user_id == OWNER_ID:
        try:
            charge_amount = float(message.text.strip())
            if charge_amount < 0:
                await message.reply("❌ Charge amount नहीं हो सकती negative!")
                user_states.pop(user_id, None)
                return

            update_setting("tts_charge", charge_amount, "Credits charged per word for TTS")
            await message.reply(
                f"✅ **TTS Charge Updated!**\n\n"
                f"अब per word {charge_amount} credits charge होंगे।",
                reply_markup=get_back_to_owner()
            )
        except ValueError:
            await message.reply("❌ Invalid amount! कृपया valid number enter करें।")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_EARN_CREDIT and user_id == OWNER_ID:
        try:
            earn_amount = float(message.text.strip())
            if earn_amount < 0:
                await message.reply("❌ Earn amount नहीं हो सकती negative!")
                user_states.pop(user_id, None)
                return

            update_setting("earn_credit", earn_amount, "Credits earned per short link process")
            await message.reply(
                f"✅ **Earn Credit Updated!**\n\n"
                f"अब short link process करने पर {earn_amount} credits मिलेंगे।",
                reply_markup=get_back_to_owner()
            )
        except ValueError:
            await message.reply("❌ Invalid amount! कृपया valid number enter करें।")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_DEACTIVATE_REASON and user_id == OWNER_ID:
        reason = message.text.strip()
        user_states[user_id] = {'state': UserState.WAITING_DEACTIVATE_TIME, 'reason': reason}
        await message.reply(
            f"📝 Reason: {reason}\n\n"
            f"कितने minutes के लिए bot को deactivate करना है?\n"
            f"(0 enter करें permanent के लिए):"
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
                f"क्या आप confirm करते हैं?",
                reply_markup=get_deactivate_confirmation_panel()
            )
        except ValueError:
            await message.reply("❌ Invalid number! कृपया valid number enter करें।")
            user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_RATING_COUNT and user_id == OWNER_ID:
        try:
            rating_count = int(message.text.strip())
            if rating_count <= 0:
                await message.reply("❌ Count 0 से ज्यादा होनी चाहिए!")
                user_states.pop(user_id, None)
                return

            user_states[user_id] = {'rating_count': rating_count}

            await message.reply(
                f"⭐ **Add {rating_count} Fake Ratings**\n\n"
                f"कृपया rating select करें:",
                reply_markup=get_rating_panel()
            )
        except ValueError:
            await message.reply("❌ Invalid number! कृपया valid number enter करें।")
            user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_MIN_PAYMENT and user_id == OWNER_ID:
        try:
            min_amount = float(message.text.strip())
            if min_amount <= 0:
                await message.reply("❌ Amount 0 से ज्यादा होनी चाहिए!")
                user_states.pop(user_id, None)
                return

            update_setting("min_payment_amount", min_amount, "Minimum payment amount in rupees")
            await message.reply(
                f"✅ **Minimum Payment Amount Updated!**\n\n"
                f"नया minimum amount: ₹{min_amount}",
                reply_markup=get_back_to_owner()
            )
        except ValueError:
            await message.reply("❌ Invalid amount! कृपया valid number enter करें।")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_MAX_PAYMENT and user_id == OWNER_ID:
        try:
            max_amount = float(message.text.strip())
            min_amount = get_setting("min_payment_amount", default=10.0)

            if max_amount <= min_amount:
                await message.reply(f"❌ Maximum amount minimum amount (₹{min_amount}) से ज्यादा होनी चाहिए!")
                user_states.pop(user_id, None)
                return

            update_setting("max_payment_amount", max_amount, "Maximum payment amount in rupees")
            await message.reply(
                f"✅ **Maximum Payment Amount Updated!**\n\n"
                f"नया maximum amount: ₹{max_amount}",
                reply_markup=get_back_to_owner()
            )
        except ValueError:
            await message.reply("❌ Invalid amount! कृपया valid number enter करें।")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_PAYMENT_RATE and user_id == OWNER_ID:
        try:
            payment_rate = float(message.text.strip())
            if payment_rate <= 0:
                await message.reply("❌ Rate 0 से ज्यादा होनी चाहिए!")
                user_states.pop(user_id, None)
                return

            update_setting("payment_rate", payment_rate, "Credits per rupee")
            await message.reply(
                f"✅ **Payment Credit Rate Updated!**\n\n"
                f"नया rate: {payment_rate} credits per ₹1",
                reply_markup=get_back_to_owner()
            )
        except ValueError:
            await message.reply("❌ Invalid amount! कृपया valid number enter करें।")
        user_states.pop(user_id, None)

    elif user_state_data == UserState.WAITING_PAYMENT_AMOUNT:
        try:
            amount = float(message.text.strip())
            min_amount = get_setting("min_payment_amount", default=10.0)
            max_amount = get_setting("max_payment_amount", default=100.0)
            payment_rate = get_setting("payment_rate", default=10.0)

            if amount < min_amount or amount > max_amount:
                await message.reply(f"❌ Amount ₹{min_amount} से ₹{max_amount} के बीच होना चाहिए!")
                user_states.pop(user_id, None)
                return

            # Calculate credits based on current rate
            credits_to_add = int(amount * payment_rate)

            user_states[user_id] = {'state': UserState.WAITING_TRANSACTION_ID, 'amount': amount, 'credits': credits_to_add}

            # Get QR code from database
            db = SessionLocal()
            try:
                qr_settings = db.query(QRCodeSettings).filter(QRCodeSettings.is_active == True).first()
                if qr_settings:
                    qr_code_url = qr_settings.qr_code_url
                    payment_number = qr_settings.payment_number
                    payment_name = qr_settings.payment_name
                else:
                    qr_code_url = "https://via.placeholder.com/300x300.png?text=QR+CODE+NOT+SET"
                    payment_number = "Not Set"
                    payment_name = "Not Set"
            except:
                qr_code_url = "https://via.placeholder.com/300x300.png?text=QR+CODE+ERROR"
                payment_number = "Error"
                payment_name = "Error"
            finally:
                db.close()

            # Send QR code with payment details
            try:
                await message.reply_photo(
                    qr_code_url,
                    caption=f"💳 **Payment Details**\n\n"
                    f"💰 **Amount:** ₹{amount}\n"
                    f"💎 **Credits:** {credits_to_add}\n"
                    f"📱 **Pay to:** {payment_name}\n"
                    f"🆔 **UPI/Number:** {payment_number}\n\n"
                    f"📱 इस QR code को scan करके payment करें\n"
                    f"⏰ 2 minutes के अंदर transaction ID send करें\n\n"
                    f"❌ Cancel करने के लिए /cancel type करें"
                )
            except:
                # Fallback if QR image fails
                await message.reply(
                    f"💳 **Payment Details**\n\n"
                    f"💰 **Amount:** ₹{amount}\n"
                    f"💎 **Credits:** {credits_to_add}\n"
                    f"📱 **Pay to:** {payment_name}\n"
                    f"🆔 **UPI/Number:** {payment_number}\n\n"
                    f"⏰ Transaction ID send करें\n"
                    f"❌ Cancel करने के लिए /cancel type करें"
                )
        except ValueError:
            await message.reply("❌ Invalid amount! कृपया valid number enter करें।")
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

            # Send confirmation message to user
            confirmation_msg = await message.reply(
                f"✅ **Payment Request Submitted!**\n\n"
                f"💰 Amount: ₹{amount}\n"
                f"💎 Credits: {credits_to_add}\n"
                f"🆔 Transaction ID: {transaction_id}\n\n"
                f"📋 आपकी payment request admin को manually check किया जाएगा\n"
                f"⏰ Usually processed within 1-2 hours\n"
                f"🕐 अगर कुछ delay हो तो max 12 hours\n"
                f"🙏 Please be patient!\n\n"
                f"🎁 **Bonus:** Delay के लिए 10 extra credits मिलेंगे!"
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
                        f"आपको patience के लिए 10 extra credits मिले हैं!\n"
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
                        f"आपकी payment request admin को भेज दी गई है।\n"
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
                        f"✅ आपकी payment request save हो गई है\n"
                        f"🔔 Request ID: #{payment_request.id}\n"
                        f"⚠️ Admin notification में technical issue\n\n"
                        f"📱 कृपया manually owner से contact करें:\n"
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
            "कोई changes नहीं किए गए।",
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
            "अब payment name enter करें:"
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

@app.on_message(filters.command("cancel"))
async def cancel_command(client: Client, message: Message):
    """Handle /cancel command to clear user state"""
    user_id = message.from_user.id
    if user_id in user_states:
        user_states.pop(user_id)
        await message.reply("❌ Operation cancelled. Your state has been reset.")
    else:
        await message.reply("ℹ️ No active operation to cancel.")


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