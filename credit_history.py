"""
Credit History Database and Tracking System
Separate database for detailed credit transaction history
"""
import os
import sqlite3
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, BigInteger, Float, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Create separate database for credit history
DATABASE_URL = "sqlite:///credit_history.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class CreditHistory(Base):
    """Detailed credit transaction history"""
    __tablename__ = "credit_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)
    amount = Column(Float)  # Positive for earned, negative for spent
    transaction_type = Column(String)  # 'earned', 'spent', 'bonus', 'referral', 'purchase', 'admin_give'
    source = Column(String)  # 'tts_usage', 'free_link', 'referral_bonus', 'payment', 'admin', 'welcome_bonus'
    description = Column(String)
    transaction_id = Column(String, unique=True, index=True, nullable=True)  # 16-digit unique transaction ID
    reference_id = Column(String, nullable=True)  # Reference to payment, link, or other transaction
    balance_before = Column(Float)  # Credit balance before transaction
    balance_after = Column(Float)  # Credit balance after transaction
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_processed = Column(Boolean, default=True)

class UserCreditSummary(Base):
    """Summary of user's credit activity"""
    __tablename__ = "user_credit_summary"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, index=True)
    total_earned = Column(Float, default=0.0)
    total_spent = Column(Float, default=0.0)
    current_balance = Column(Float, default=0.0)
    total_transactions = Column(Integer, default=0)
    first_transaction = Column(DateTime, nullable=True)
    last_transaction = Column(DateTime, nullable=True)
    # Breakdown by source
    earned_welcome = Column(Float, default=0.0)
    earned_referral = Column(Float, default=0.0)
    earned_links = Column(Float, default=0.0)
    earned_purchase = Column(Float, default=0.0)
    earned_admin = Column(Float, default=0.0)
    spent_tts = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow)

def create_credit_history_tables():
    """Create credit history database tables"""
    Base.metadata.create_all(bind=engine)
    print("✅ Credit history database tables created successfully!")

def get_credit_history_db() -> Session:
    """Get credit history database session"""
    db = SessionLocal()
    try:
        return db
    except Exception as e:
        db.close()
        raise e

def log_credit_history(user_id: int, amount: float, transaction_type: str, source: str, 
                      description: str, transaction_id: str = None, reference_id: str = None, 
                      balance_before: float = 0.0, balance_after: float = 0.0):
    """Log detailed credit transaction history"""
    db = get_credit_history_db()
    try:
        # Create credit history entry
        history_entry = CreditHistory(
            user_id=user_id,
            amount=amount,
            transaction_type=transaction_type,
            source=source,
            description=description,
            transaction_id=transaction_id,
            reference_id=reference_id,
            balance_before=balance_before,
            balance_after=balance_after
        )
        db.add(history_entry)
        
        # Update or create user summary
        summary = db.query(UserCreditSummary).filter(UserCreditSummary.user_id == user_id).first()
        if not summary:
            summary = UserCreditSummary(
                user_id=user_id,
                first_transaction=datetime.utcnow()
            )
            db.add(summary)
        
        # Update summary totals
        summary.total_transactions += 1
        summary.current_balance = balance_after
        summary.last_transaction = datetime.utcnow()
        summary.updated_at = datetime.utcnow()
        
        if amount > 0:  # Credits earned
            summary.total_earned += amount
            if source == 'welcome_bonus':
                summary.earned_welcome += amount
            elif source == 'referral_bonus':
                summary.earned_referral += amount
            elif source == 'free_link':
                summary.earned_links += amount
            elif source == 'payment':
                summary.earned_purchase += amount
            elif source == 'admin':
                summary.earned_admin += amount
        else:  # Credits spent
            summary.total_spent += abs(amount)
            if source == 'tts_usage':
                summary.spent_tts += abs(amount)
        
        db.commit()
        print(f"✅ Credit history logged: User {user_id}, Amount {amount}, Type {transaction_type}")
        
    except Exception as e:
        print(f"❌ Error logging credit history: {e}")
        db.rollback()
    finally:
        db.close()

def get_user_credit_history(user_id: int, limit: int = 50):
    """Get user's credit transaction history"""
    db = get_credit_history_db()
    try:
        history = db.query(CreditHistory).filter(
            CreditHistory.user_id == user_id
        ).order_by(CreditHistory.timestamp.desc()).limit(limit).all()
        return history
    except Exception as e:
        print(f"❌ Error getting credit history: {e}")
        return []
    finally:
        db.close()

def get_user_credit_summary(user_id: int):
    """Get user's credit summary"""
    db = get_credit_history_db()
    try:
        summary = db.query(UserCreditSummary).filter(UserCreditSummary.user_id == user_id).first()
        return summary
    except Exception as e:
        print(f"❌ Error getting credit summary: {e}")
        return None
    finally:
        db.close()

def get_all_users_credit_stats():
    """Get credit statistics for all users"""
    db = get_credit_history_db()
    try:
        stats = db.query(UserCreditSummary).all()
        return stats
    except Exception as e:
        print(f"❌ Error getting all users credit stats: {e}")
        return []
    finally:
        db.close()

# Initialize credit history database
if __name__ == "__main__":
    create_credit_history_tables()