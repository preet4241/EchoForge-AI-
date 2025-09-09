import os
from datetime import datetime
from database import SessionLocal, User, ReferralSystem, CreditTransaction

def create_user_referral_code(user_id):
    """Create simple referral code using user ID"""
    return f"ref_{user_id}"

def get_user_referral_link(user_id):
    """Get user's referral link"""
    referral_code = create_user_referral_code(user_id)
    bot_username = os.getenv('BOT_USERNAME', 'your_bot_username')
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    return referral_link, referral_code

def get_user_referral_stats(user_id):
    """Get user's referral statistics with actual data"""
    db = SessionLocal()
    try:
        # Count successful referrals by this user
        successful_referrals = db.query(ReferralSystem).filter(
            ReferralSystem.referrer_id == user_id,
            ReferralSystem.is_claimed == True
        ).count()
        
        # Total credits earned from referrals
        from sqlalchemy import func
        total_referral_credits = db.query(func.sum(ReferralSystem.credits_earned)).filter(
            ReferralSystem.referrer_id == user_id,
            ReferralSystem.is_claimed == True
        ).scalar() or 0.0
        
        # Get recent referred users (last 5)
        recent_referrals = db.query(ReferralSystem).filter(
            ReferralSystem.referrer_id == user_id,
            ReferralSystem.is_claimed == True
        ).order_by(ReferralSystem.created_at.desc()).limit(5).all()
        
        referred_users = []
        for ref in recent_referrals:
            referred_user = db.query(User).filter(User.user_id == ref.referred_id).first()
            if referred_user:
                referred_users.append({
                    'name': referred_user.first_name or 'Unknown',
                    'joined_date': ref.created_at.strftime('%d/%m/%Y'),
                    'credits_earned': ref.credits_earned
                })
        
        return {
            'user_referral_code': create_user_referral_code(user_id),
            'successful_referrals': successful_referrals,
            'total_referral_credits': total_referral_credits,
            'referred_users': referred_users
        }
        
    except Exception as e:
        print(f"Error getting referral stats: {e}")
        return {
            'user_referral_code': create_user_referral_code(user_id),
            'successful_referrals': 0,
            'total_referral_credits': 0.0,
            'referred_users': []
        }
    finally:
        db.close()

def process_referral(referral_code, new_user_id):
    """Process referral when new user joins using referral code"""
    db = SessionLocal()
    try:
        # Extract referrer ID from code (format: ref_{user_id})
        if not referral_code.startswith("ref_"):
            return False, "Invalid referral code format"
        
        try:
            referrer_id = int(referral_code.replace("ref_", ""))
        except ValueError:
            return False, "Invalid referral code"
        
        # Check if user is trying to refer themselves
        if referrer_id == new_user_id:
            return False, "You cannot refer yourself"
        
        # Check if referrer exists and is active
        referrer = db.query(User).filter(
            User.user_id == referrer_id,
            User.is_active == True,
            User.is_banned == False
        ).first()
        
        if not referrer:
            return False, "Referrer not found or inactive"
        
        # Check if new user already was referred
        existing_referral = db.query(ReferralSystem).filter(
            ReferralSystem.referred_id == new_user_id
        ).first()
        
        if existing_referral:
            return False, "User already referred by someone else"
        
        # Give rewards
        referrer_bonus = 20.0  # Credits for referrer
        referred_bonus = 15.0  # Credits for new user
        
        # Update referrer credits
        referrer.credits = float(referrer.credits) + referrer_bonus
        
        # Log referrer transaction
        referrer_transaction = CreditTransaction(
            user_id=referrer_id,
            amount=referrer_bonus,
            transaction_type='referral_bonus',
            description=f'Referral bonus for referring user {new_user_id}'
        )
        db.add(referrer_transaction)
        
        # Update referred user credits
        referred_user = db.query(User).filter(User.user_id == new_user_id).first()
        if referred_user:
            referred_user.credits = float(referred_user.credits) + referred_bonus
            
            # Log referred user transaction
            referred_transaction = CreditTransaction(
                user_id=new_user_id,
                amount=referred_bonus,
                transaction_type='referral_welcome',
                description=f'Welcome bonus for using referral code {referral_code}'
            )
            db.add(referred_transaction)
        
        # Create referral record
        new_referral = ReferralSystem(
            referrer_id=referrer_id,
            referred_id=new_user_id,
            referral_code=referral_code,
            credits_earned=referrer_bonus,
            is_claimed=True
        )
        db.add(new_referral)
        
        db.commit()
        
        return True, {
            'referrer_id': referrer_id,
            'referrer_bonus': referrer_bonus,
            'referred_bonus': referred_bonus,
            'referrer_name': referrer.first_name if referrer else 'Unknown',
            'referred_name': referred_user.first_name if referred_user else 'Unknown'
        }
        
    except Exception as e:
        print(f"Error processing referral: {e}")
        db.rollback()
        return False, "Error processing referral"
    finally:
        db.close()