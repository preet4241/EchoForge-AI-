from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import os

OWNER_ID = int(os.getenv('OWNER_ID', '0'))

# Owner Panel Keyboard
def get_owner_panel():
    """Main owner control panel"""
    keyboard = [
        [InlineKeyboardButton("🎤 TTS", callback_data="owner_tts")],
        [InlineKeyboardButton("👑 User Management", callback_data="owner_users"), InlineKeyboardButton("📢 Broadcast Message", callback_data="owner_broadcast")],
        [InlineKeyboardButton("📊 Bot Analytics", callback_data="owner_status"), InlineKeyboardButton("💰 Credit Handler", callback_data="owner_credit_handler")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="owner_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

# User Panel Keyboard
def get_user_panel():
    keyboard = [
        [InlineKeyboardButton("🎤 Start TTS", callback_data="user_tts")],
        [
            InlineKeyboardButton("👤 Profile", callback_data="user_profile"),
            InlineKeyboardButton("💰 Get Credits", callback_data="user_credits")
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data="user_help"),
            InlineKeyboardButton("ℹ️ About Bot", callback_data="user_about")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# About page for new users
def get_about_keyboard():
    keyboard = [
        [InlineKeyboardButton("🚀 Start Using Bot", callback_data="start_bot")]
    ]
    return InlineKeyboardMarkup(keyboard)

# New About page keyboard with owner details and support
def get_user_about_keyboard():
    keyboard = [
        [InlineKeyboardButton("🆘 Contact Support", callback_data="contact_support")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_user")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Owner details keyboard
def get_owner_details_keyboard():
    keyboard = [
        [InlineKeyboardButton("⬅️ Back to About", callback_data="user_about")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Support message confirmation keyboard
def get_support_confirmation_keyboard():
    keyboard = [
        [InlineKeyboardButton("✅ OK", callback_data="back_to_user")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Contact support request keyboard
def get_contact_support_keyboard():
    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="user_about")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Credit Management Panel for Users
def get_user_credit_panel():
    keyboard = [
        [
            InlineKeyboardButton("🆓 Free Credit", callback_data="free_credit"),
            InlineKeyboardButton("💳 Buy Credit", callback_data="buy_credit")
        ],
        [InlineKeyboardButton("👥 Referral", callback_data="referral_system")],
        [InlineKeyboardButton("📊 My Transaction", callback_data="my_transaction")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_user")]
    ]
    return InlineKeyboardMarkup(keyboard)

# My Transaction Panel for Users
def get_my_transaction_panel():
    keyboard = [
        [InlineKeyboardButton("📥 Download Transactions", callback_data="download_transactions")],
        [
            InlineKeyboardButton("📋 Track Trans", callback_data="track_transactions"),
            InlineKeyboardButton("🔍 Track Custom Trans", callback_data="track_custom_transaction")
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="user_credits")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Users Management Panel
def get_users_panel():
    keyboard = [
        [
            InlineKeyboardButton("💰 Give Credit", callback_data="give_credit"),
            InlineKeyboardButton("💰 Give Credit All", callback_data="give_credit_all")
        ],
        [
            InlineKeyboardButton("🚫 Ban User", callback_data="ban_user"),
            InlineKeyboardButton("✅ Unban User", callback_data="unban_user")
        ],
        [
            InlineKeyboardButton("🔍 User Info", callback_data="user_specific_info"),
            InlineKeyboardButton("📊 Transaction", callback_data="transaction_history")
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_owner")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Credit Handler Panel
def get_credit_handler_panel():
    """Credit handler panel with buy credit and link shortener options"""
    keyboard = [
        [InlineKeyboardButton("💳 Buy Credit", callback_data="credit_handler_buy"), InlineKeyboardButton("🔗 Link Shortener", callback_data="owner_shortner")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_owner")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Link Shortner Panel (when shortner exists)
def get_shortner_panel():
    keyboard = [
        [InlineKeyboardButton("ℹ️ Info", callback_data="shortner_info")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_owner")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Link Shortner Panel (when no shortner)
def get_shortner_add_panel():
    keyboard = [
        [InlineKeyboardButton("➕ Add", callback_data="add_shortner")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_owner")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Shortner Info Panel
def get_shortner_info_panel():
    keyboard = [
        [
            InlineKeyboardButton("🗑️ Remove", callback_data="remove_shortner"),
            InlineKeyboardButton("⬅️ Back", callback_data="owner_shortner")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Settings Panel
def get_settings_panel():
    # Check bot status
    from database import SessionLocal, BotStatus
    db = SessionLocal()
    try:
        bot_status = db.query(BotStatus).first()
        if not bot_status:
            bot_status = BotStatus(is_active=True)
            db.add(bot_status)
            db.commit()

        active_text = "✅ Active" if bot_status.is_active else "❌ Deactive"
        shutdown_text = "🔴 Shutdown" if bot_status.is_active else "🟢 Start"
    except:
        active_text = "✅ Active"
        shutdown_text = "🔴 Shutdown"
    finally:
        db.close()

    keyboard = [
        [InlineKeyboardButton("💰 Credits", callback_data="settings_credits")],
        [
            InlineKeyboardButton(active_text, callback_data="settings_toggle"),
            InlineKeyboardButton(shutdown_text, callback_data="settings_shutdown")
        ],
        [
            InlineKeyboardButton("⭐ Rating", callback_data="settings_rating"),
            InlineKeyboardButton("💾 Bot Backup", callback_data="bot_backup")
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_owner")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Rating Panel
def get_rating_panel():
    keyboard = [
        [
            InlineKeyboardButton("1⭐", callback_data="add_rating_1"),
            InlineKeyboardButton("2⭐", callback_data="add_rating_2"),
            InlineKeyboardButton("3⭐", callback_data="add_rating_3"),
            InlineKeyboardButton("4⭐", callback_data="add_rating_4"),
            InlineKeyboardButton("5⭐", callback_data="add_rating_5")
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="owner_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Deactivate Confirmation Panel
def get_deactivate_confirmation_panel():
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data="confirm_deactivate"),
            InlineKeyboardButton("❌ Cancel", callback_data="owner_settings")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Credits Settings Panel
def get_credits_settings_panel():
    keyboard = [
        [InlineKeyboardButton("🎁 Welcome Credit", callback_data="settings_welcome_credit")],
        [
            InlineKeyboardButton("💸 TTS Charge", callback_data="settings_tts_charge"),
            InlineKeyboardButton("⏱️ Link Timeout", callback_data="settings_link_timeout")
        ],
        [
            InlineKeyboardButton("🆓 Free Credit", callback_data="settings_free_credit"),
            InlineKeyboardButton("💳 Buy Credit", callback_data="settings_buy_credit")
        ],
        [InlineKeyboardButton("👥 Referral", callback_data="settings_referral")],
        [InlineKeyboardButton("⬅️ Back", callback_data="owner_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Referral Settings Panel
def get_referral_settings_panel():
    keyboard = [
        [InlineKeyboardButton("👤 Referred User Credit", callback_data="settings_referred_user_credit")],
        [InlineKeyboardButton("👥 Referrer Credit", callback_data="settings_referrer_credit")],
        [InlineKeyboardButton("⬅️ Back", callback_data="settings_credits")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Settings Confirmation Panel
def get_settings_confirmation_panel(setting_type):
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"settings_confirm_{setting_type}"),
            InlineKeyboardButton("❌ Cancel", callback_data="settings_cancel")
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="settings_credits")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Payment Verification Panel for Owner
def get_payment_verification_panel(payment_id):
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_payment_{payment_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_payment_{payment_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Enhanced Payment Cancel Panel for User
def get_payment_cancel_panel():
    """Keyboard for payment cancellation"""
    keyboard = [
        [InlineKeyboardButton("💳 Try Payment Again", callback_data="buy_credit")],
        [InlineKeyboardButton("📞 Contact Support", callback_data="contact_support")],
        [InlineKeyboardButton("⬅️ Back to Credits", callback_data="user_credits")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_simple_referral_panel(referral_code, referral_link):
    """Simple referral panel with share, copy, status and back buttons"""
    # Share text for Telegram
    share_text = f"🤖 Join this amazing TTS Bot and get bonus credits!%0A%0A🎁 Use my referral link: {referral_link}%0A💰 Get 15 bonus credits instantly!"
    share_url = f"https://t.me/share/url?url={share_text}"
    
    keyboard = [
        [
            InlineKeyboardButton("📤 Share", url=share_url),
            InlineKeyboardButton("📋 Copy", callback_data=f"copy_referral_{referral_code}")
        ],
        [InlineKeyboardButton("📊 Status", callback_data="referral_status")],
        [InlineKeyboardButton("⬅️ Back", callback_data="user_credits")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_referral_panel():
    """Keyboard for referral system"""
    keyboard = [
        [InlineKeyboardButton("📊 My Referral Stats", callback_data="my_referral_stats")],
        [InlineKeyboardButton("🎁 Share Referral Code", callback_data="share_referral")],
        [InlineKeyboardButton("🏆 Referral Leaderboard", callback_data="referral_leaderboard")],
        [InlineKeyboardButton("ℹ️ How Referrals Work", callback_data="referral_info")],
        [InlineKeyboardButton("⬅️ Back to Credits", callback_data="user_credits")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_referral_share_panel(referral_code):
    """Keyboard for sharing referral code"""
    # Get bot username from environment
    import os
    bot_username = os.getenv('BOT_USERNAME', 'your_bot_username')
    
    share_text = f"🤖 Join this amazing TTS Bot and get bonus credits!%0A%0A🎁 Use: /start {referral_code}%0A💰 Get 15 bonus credits instantly!%0A%0ABot: @{bot_username}"
    share_url = f"https://t.me/share/url?url={share_text}"

    keyboard = [
        [InlineKeyboardButton("📤 Share on Telegram", url=share_url)],
        [InlineKeyboardButton("📋 Copy Code", callback_data=f"copy_referral_{referral_code}")],
        [InlineKeyboardButton("⬅️ Back to Referrals", callback_data="referral_system")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_owner_referral_panel():
    """Owner panel for referral management"""
    keyboard = [
        [InlineKeyboardButton("📊 Referral Statistics", callback_data="owner_referral_stats")],
        [InlineKeyboardButton("🏆 Top Referrers", callback_data="owner_top_referrers")],
        [InlineKeyboardButton("⚙️ Referral Settings", callback_data="owner_referral_settings")],
        [InlineKeyboardButton("⬅️ Back to Owner Panel", callback_data="back_to_owner")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Support Contact Panel removed - now handled directly in callback


# Support confirmation keyboard
def get_support_confirmation_keyboard():
    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="back_to_user")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Back buttons
def get_back_to_owner():
    keyboard = [[InlineKeyboardButton("⬅️ Back to Main", callback_data="back_to_owner")]]
    return InlineKeyboardMarkup(keyboard)

def get_back_to_user():
    keyboard = [[InlineKeyboardButton("⬅️ Back to Main", callback_data="back_to_user")]]
    return InlineKeyboardMarkup(keyboard)

# Help section keyboard with contact support
def get_help_section_keyboard():
    keyboard = [
        [InlineKeyboardButton("🆘 Contact Support", callback_data="contact_support")],
        [InlineKeyboardButton("⬅️ Back to Main", callback_data="back_to_user")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Enhanced Voice Selection for Users - Perfectly Synced with Backend
def get_voice_selection():
    """Get voice selection keyboard perfectly synchronized with TTS backend"""
    try:
        keyboard = [
            # Info header with auto-detection feature
            [InlineKeyboardButton("🎤 10 Premium Voices • Auto Language Detection", callback_data="dummy")],
            
            # Male Voices Section
            [InlineKeyboardButton("👨 MALE VOICES (5) - हिंदी & English", callback_data="dummy")],
            
            # Male Voices Row 1: Deep Bass (Hindi) + Ocean Calm (English)
            [
                InlineKeyboardButton("🎵 Deep Bass", callback_data="voice_male1"),
                InlineKeyboardButton("🎵 Ocean Calm", callback_data="voice_male2")
            ],
            
            # Male Voices Row 2: Professional (Hindi) + Energetic (English)
            [
                InlineKeyboardButton("🎵 Professional", callback_data="voice_male3"),
                InlineKeyboardButton("🎵 Energetic", callback_data="voice_male4")
            ],
            
            # Male Voices Row 3: Warm Tone (Hindi)
            [InlineKeyboardButton("🎵 Warm Tone", callback_data="voice_male5")],
            
            # Female Voices Section
            [InlineKeyboardButton("👩 FEMALE VOICES (5) - हिंदी & English", callback_data="dummy")],
            
            # Female Voices Row 1: Honey Sweet (Hindi) + Crystal Clear (English)
            [
                InlineKeyboardButton("🎶 Honey Sweet", callback_data="voice_female1"),
                InlineKeyboardButton("🎶 Crystal Clear", callback_data="voice_female2")
            ],
            
            # Female Voices Row 2: Soft Whisper (Hindi) + Bright Star (English)
            [
                InlineKeyboardButton("🎶 Soft Whisper", callback_data="voice_female3"),
                InlineKeyboardButton("🎶 Bright Star", callback_data="voice_female4")
            ],
            
            # Female Voices Row 3: Melodic Angel (Hindi)
            [InlineKeyboardButton("🎶 Melodic Angel ", callback_data="voice_female5")],
            
            # Back button
            [InlineKeyboardButton("⬅️ Back to Main", callback_data="back_to_user")]
        ]
        return InlineKeyboardMarkup(keyboard)
    except Exception as e:
        print(f"❌ Error creating voice selection keyboard: {e}")
        # Return enhanced fallback keyboard
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👨 Male Voice", callback_data="voice_male1")],
            [InlineKeyboardButton("👩 Female Voice ", callback_data="voice_female1")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_user")]
        ])

# Enhanced Voice Selection for Owner - Premium TTS Panel
def get_voice_selection_owner():
    """Get voice selection keyboard for owner - perfectly synced with backend"""
    try:
        keyboard = [
            # Owner header with technical details
            [InlineKeyboardButton("👑 OWNER TTS - 10 Premium Neural Voices", callback_data="dummy")],
            [InlineKeyboardButton("🎤 Edge TTS • Language Detection • SSML Enhanced", callback_data="dummy")],
            
            # Male Voices Section
            [InlineKeyboardButton("👨 MALE VOICES (5)", callback_data="dummy")],
            
            # Male Voices - Compact owner view with technical names
            [
                InlineKeyboardButton("🎵 Deep Bass ", callback_data="voice_male1"), # MadhurNeural
                InlineKeyboardButton("🎵 Ocean Calm", callback_data="voice_male2") # PrabhatNeural
            ],
            [
                InlineKeyboardButton("🎵 Professional", callback_data="voice_male3"), #
                InlineKeyboardButton("🎵 Energetic", callback_data="voice_male4") # ArjunIndicNeural
            ],
            [InlineKeyboardButton("🎵 Warm Tone", callback_data="voice_male5")], # RehaanNeural
            
            # Female Voices Section
            [InlineKeyboardButton("👩 FEMALE VOICES (5)", callback_data="dummy")],
            
            # Female Voices - Compact owner view with technical names
            [
                InlineKeyboardButton("🎶 Honey Sweet", callback_data="voice_female1"), # SwaraNeural
                InlineKeyboardButton("🎶 Crystal Clear ", callback_data="voice_female2") # NeerjaNeural
            ],
            [
                InlineKeyboardButton("🎶 Soft Whisper ", callback_data="voice_female3"), # AnanyaNeural
                InlineKeyboardButton("🎶 Bright Star", callback_data="voice_female4") # AashiNeural
            ],
            [InlineKeyboardButton("🎶 Melodic Angel", callback_data="voice_female5")], # KavyaNeural
            
            # Owner controls
            [InlineKeyboardButton("⬅️ Back to Owner Panel", callback_data="back_to_owner")]
        ]
        return InlineKeyboardMarkup(keyboard)
    except Exception as e:
        print(f"❌ Error creating owner voice selection keyboard: {e}")
        # Return enhanced fallback keyboard
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👨 Male Voice (Premium)", callback_data="voice_male1")],
            [InlineKeyboardButton("👩 Female Voice (Premium)", callback_data="voice_female1")],
            [InlineKeyboardButton("⬅️ Back to Owner", callback_data="back_to_owner")]
        ])

# Enhanced TTS Language Selection with Auto-Detection
def get_tts_languages():
    """Enhanced language selection with intelligent auto-detection"""
    keyboard = [
        # Recommended option
        [InlineKeyboardButton("🤖 Auto-Detect Language (Recommended)", callback_data="tts_lang_auto")],
        
        # Manual language selection
        [
            InlineKeyboardButton("🇮🇳 हिंदी (Hindi)", callback_data="tts_lang_hi"),
            InlineKeyboardButton("🇺🇸 English (India)", callback_data="tts_lang_en")
        ],
        
        # Mixed content option
        [InlineKeyboardButton("🌐 Mixed Hindi-English", callback_data="tts_lang_mixed")],
        
        # Legacy options (if needed)
        [
            InlineKeyboardButton("🇪🇸 Español", callback_data="tts_lang_es"),
            InlineKeyboardButton("🇫🇷 Français", callback_data="tts_lang_fr")
        ],
        
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_user")]
    ]
    return InlineKeyboardMarkup(keyboard)



# Payment Settings Panel
def get_payment_settings_panel():
    keyboard = [
        [InlineKeyboardButton("💰 Minimum Amount", callback_data="settings_min_payment")],
        [InlineKeyboardButton("💰 Maximum Amount", callback_data="settings_max_payment")],
        [InlineKeyboardButton("💎 Payment Rate", callback_data="settings_payment_rate")],
        [InlineKeyboardButton("🏦 QR Code Settings", callback_data="settings_qr_code")],
        [InlineKeyboardButton("⬅️ Back", callback_data="settings_credits")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Buy Credit Management Panel
def get_buy_credit_management_panel():
    """Buy credit management panel with QR and UPI options"""
    keyboard = [
        [InlineKeyboardButton("🖼️ Change QR", callback_data="change_qr_code"), InlineKeyboardButton("📱 Change UPI/No. ID", callback_data="change_upi_id")],
        [InlineKeyboardButton("⬅️ Back", callback_data="owner_credit_handler")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Buy Credit Setup Panel (when QR/UPI not available)
def get_buy_credit_setup_panel():
    """Panel for setting up QR and UPI when not available"""
    keyboard = [
        [InlineKeyboardButton("➕ Add QR & UPI ID", callback_data="add_qr_upi")],
        [InlineKeyboardButton("⬅️ Back", callback_data="owner_credit_handler")]
    ]
    return InlineKeyboardMarkup(keyboard)

# QR Code Management Panel
def get_qr_management_panel():
    keyboard = [
        [InlineKeyboardButton("📷 View Current QR", callback_data="view_qr_code")],
        [InlineKeyboardButton("🖼️ Update QR Code", callback_data="update_qr_code_url")],
        [InlineKeyboardButton("📱 Update Payment Details", callback_data="update_payment_details")],
        [InlineKeyboardButton("⬅️ Back", callback_data="settings_payment")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_free_credit_referral_panel(referral_link):
    """Keyboard for free credit referral with Share, Status, Back buttons"""
    import urllib.parse
    
    # Create proper share text
    share_text = f"🤖 Join this amazing TTS Bot and get bonus credits!\n\n🎁 Use my referral link: {referral_link}\n💰 Get free credits instantly!"
    # Properly encode the text for URL
    encoded_text = urllib.parse.quote(share_text)
    share_url = f"https://t.me/share/url?url={encoded_text}"
    
    keyboard = [
        [
            InlineKeyboardButton("📤 Share", url=share_url),
            InlineKeyboardButton("📊 Status", callback_data="referral_status")
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="user_credits")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Transaction History Panel
def get_transaction_history_panel():
    keyboard = [
        [
            InlineKeyboardButton("📅 Yesterday", callback_data="tx_yesterday"),
            InlineKeyboardButton("🎯 Custom", callback_data="tx_custom"),
            InlineKeyboardButton("📅 Today", callback_data="tx_today")
        ],
        [
            InlineKeyboardButton("📊 Last Week", callback_data="tx_last_week"),
            InlineKeyboardButton("📈 Last Month", callback_data="tx_last_month")
        ],
        [
            InlineKeyboardButton("🔍 Track Payment", callback_data="tx_track_payment")
        ],
        [
            InlineKeyboardButton("📋 All Transactions", callback_data="tx_all_transactions")
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="owner_users")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Date Range Selection Panel for Custom Transaction History
def get_custom_date_panel():
    keyboard = [
        [InlineKeyboardButton("⏭️ Skip Second Date", callback_data="tx_custom_single")],
        [InlineKeyboardButton("⬅️ Back", callback_data="transaction_history")]
    ]
    return InlineKeyboardMarkup(keyboard)