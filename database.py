import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./bot.db')

# Add connection pooling and retry logic for better stability
if DATABASE_URL.startswith('sqlite'):
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        echo=False,
        connect_args={
            "check_same_thread": False,
            "timeout": 30,
            "isolation_level": None
        },
        poolclass=None
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        echo=False,
        client_encoding='utf8'
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_banned = Column(Boolean, default=False)
    credits = Column(Float, default=10.0)  # Free credits for new users
    join_date = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)

class TTSRequest(Base):
    __tablename__ = "tts_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)
    text = Column(String)
    language = Column(String, default='hi')
    timestamp = Column(DateTime, default=datetime.utcnow)
    credits_used = Column(Float, default=1.0)

class LinkShortner(Base):
    __tablename__ = "link_shortners"
    
    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String, unique=True, index=True)
    api_key = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class BotSettings(Base):
    __tablename__ = "bot_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    setting_name = Column(String, unique=True, index=True)
    setting_value = Column(Float)
    description = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)

class BotStatus(Base):
    __tablename__ = "bot_status"
    
    id = Column(Integer, primary_key=True, index=True)
    is_active = Column(Boolean, default=True)
    deactivated_reason = Column(String, nullable=True)
    deactivated_until = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)

class BotRating(Base):
    __tablename__ = "bot_ratings"
    
    id = Column(Integer, primary_key=True, index=True)
    rating = Column(Integer)  # 1-5 stars
    fake_rating = Column(Boolean, default=True)  # Since these are fake ratings
    created_at = Column(DateTime, default=datetime.utcnow)

class Feedback(Base):
    __tablename__ = "feedbacks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)
    rating = Column(Integer)  # 1-5 stars
    timestamp = Column(DateTime, default=datetime.utcnow)

class CreditTransaction(Base):
    __tablename__ = "credit_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)
    amount = Column(Float)  # Positive for credits added, negative for credits used
    transaction_type = Column(String)  # 'welcome', 'admin_give', 'tts_used', 'referral', 'purchase', etc.
    description = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

class ReferralSystem(Base):
    __tablename__ = "referrals"
    
    id = Column(Integer, primary_key=True, index=True)
    referrer_id = Column(BigInteger, index=True)  # User who referred
    referred_id = Column(BigInteger, index=True)  # User who was referred
    referral_code = Column(String, unique=True, index=True)
    credits_earned = Column(Float, default=0.0)
    is_claimed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class PaymentRequest(Base):
    __tablename__ = "payment_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)
    amount = Column(Float)  # Payment amount in rupees
    credits_to_add = Column(Float)  # Credits to be added after confirmation
    transaction_id = Column(String)  # User provided transaction ID
    status = Column(String, default='pending')  # pending, confirmed, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    verified_at = Column(DateTime, nullable=True)

class QRCodeSettings(Base):
    __tablename__ = "qr_code_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    qr_code_url = Column(String)  # QR code image URL or file path
    payment_number = Column(String)  # UPI ID or phone number for payments
    payment_name = Column(String)  # Name for payments
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow)

class ShortLinks(Base):
    __tablename__ = "short_links"
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, index=True)  # The shortened URL
    payload = Column(String, unique=True, index=True)  # The token used in the long URL
    status = Column(String, default='active')  # active, expired, inactive
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

class UserLinks(Base):
    __tablename__ = "user_links" 
    
    id = Column(Integer, primary_key=True, index=True)
    userid = Column(BigInteger, index=True)
    linkid = Column(Integer, index=True)
    assignedat = Column(DateTime, default=datetime.utcnow)
    creditgiven = Column(Boolean, default=False)
    creditedat = Column(DateTime, nullable=True)

def get_setting(setting_name: str, default=0.0):
    """Get bot setting value with enhanced error handling"""
    # Input validation
    if not setting_name or not isinstance(setting_name, str):
        print(f"Invalid setting_name: {setting_name}")
        return default
        
    db = None
    try:
        db = SessionLocal()
        setting = db.query(BotSettings).filter(BotSettings.setting_name == setting_name).first()
        if setting and setting.setting_value is not None:
            return setting.setting_value
        else:
            print(f"Setting {setting_name} not found, using default: {default}")
            return default
    except Exception as e:
        print(f"Error getting setting {setting_name}: {e}")
        return default
    finally:
        if db:
            try:
                db.close()
            except Exception as close_error:
                print(f"Error closing database in get_setting: {close_error}")

def update_setting(setting_name: str, value: float, description: str = None):
    """Update bot setting with enhanced error handling"""
    # Input validation
    if not setting_name or not isinstance(setting_name, str):
        print(f"Invalid setting_name: {setting_name}")
        return False
        
    if not isinstance(value, (int, float)):
        print(f"Invalid value type for setting {setting_name}: {value}")
        return False
    
    db = None
    try:
        db = SessionLocal()
        setting = db.query(BotSettings).filter(BotSettings.setting_name == setting_name).first()
        if setting:
            setting.setting_value = float(value)
            setting.updated_at = datetime.utcnow()
            if description and isinstance(description, str):
                setting.description = description[:500]  # Limit description length
        else:
            setting = BotSettings(
                setting_name=setting_name[:100],  # Limit name length
                setting_value=float(value),
                description=description[:500] if description and isinstance(description, str) else None
            )
            db.add(setting)
        db.commit()
        print(f"Successfully updated setting: {setting_name} = {value}")
        return True
    except Exception as e:
        print(f"Error updating setting {setting_name}: {e}")
        if db:
            try:
                db.rollback()
            except Exception as rollback_error:
                print(f"Error during rollback in update_setting: {rollback_error}")
        return False
    finally:
        if db:
            try:
                db.close()
            except Exception as close_error:
                print(f"Error closing database in update_setting: {close_error}")

def create_tables():
    """Create database tables only if needed and initialize default settings with error handling"""
    tables_created = False
    
    try:
        # Check if tables already exist by inspecting the database metadata
        from sqlalchemy import inspect
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        # Check if our main tables exist
        required_tables = ['users', 'tts_requests', 'bot_settings', 'bot_status']
        missing_tables = [table for table in required_tables if table not in existing_tables]
        
        if missing_tables:
            print(f"Creating missing database tables: {', '.join(missing_tables)}")
            Base.metadata.create_all(bind=engine)
            print("Database tables created successfully")
            tables_created = True
        else:
            print("Database tables already exist")
            tables_created = False
            
    except Exception as e:
        print(f"Error checking database tables: {e}")
        # Fallback: try to create all tables
        try:
            print("Attempting to create database tables as fallback...")
            Base.metadata.create_all(bind=engine)
            tables_created = True
        except Exception as fallback_error:
            print(f"Fallback table creation failed: {fallback_error}")
            return False
    
    # Initialize default settings if not exist (only if tables were just created or settings are missing)
    db = None
    try:
        db = SessionLocal()
        default_settings = [
            ("welcome_credit", 10.0, "Credits given to new users"),
            ("tts_charge", 0.05, "Credits charged per word for TTS"),
            ("earn_credit", 1.0, "Credits earned per short link process"),
            ("bot_active", 1.0, "Bot active/inactive status"),
            ("min_payment_amount", 10.0, "Minimum payment amount in rupees"),
            ("max_payment_amount", 100.0, "Maximum payment amount in rupees"),
            ("payment_rate", 10.0, "Credits per 1 rupee (10 credits per rupee)")
        ]
        
        settings_created = 0
        status_created = False
        qr_created = False
        
        # Initialize default QR code settings only if not exists
        try:
            qr_settings = db.query(QRCodeSettings).first()
            if not qr_settings:
                qr_settings = QRCodeSettings(
                    qr_code_url="https://via.placeholder.com/300x300.png?text=QR+CODE+PLACEHOLDER",
                    payment_number="1234567890@paytm",
                    payment_name="Bot Owner",
                    is_active=True
                )
                db.add(qr_settings)
                qr_created = True
                if tables_created:
                    print("Created default QR code settings")
        except Exception as qr_error:
            print(f"Error creating QR code settings: {qr_error}")
        
        # Initialize default settings only if missing
        for setting_name, value, description in default_settings:
            try:
                existing = db.query(BotSettings).filter(BotSettings.setting_name == setting_name).first()
                if not existing:
                    setting = BotSettings(
                        setting_name=setting_name,
                        setting_value=value,
                        description=description
                    )
                    db.add(setting)
                    settings_created += 1
            except Exception as setting_error:
                print(f"Error creating setting {setting_name}: {setting_error}")
                continue
        
        # Initialize bot status if not exist
        try:
            bot_status = db.query(BotStatus).first()
            if not bot_status:
                bot_status = BotStatus(is_active=True)
                db.add(bot_status)
                status_created = True
                if tables_created:
                    print("Created default bot status")
        except Exception as status_error:
            print(f"Error creating bot status: {status_error}")
        
        db.commit()
        
        # Only show detailed log if something was actually created
        if tables_created or settings_created > 0 or status_created or qr_created:
            print(f"Database initialization completed. Created {settings_created} default settings")
            return True
        else:
            return False  # Nothing was created, database was already initialized
        
    except Exception as e:
        print(f"Error initializing database: {e}")
        if db:
            try:
                db.rollback()
            except Exception as rollback_error:
                print(f"Error during rollback in create_tables: {rollback_error}")
        return False
    finally:
        if db:
            try:
                db.close()
            except Exception as close_error:
                print(f"Error closing database in create_tables: {close_error}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()