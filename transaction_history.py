"""
Transaction History System for TTS Bot
Complete transaction tracking, analysis, and file export system
"""
import os
import json
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from database import SessionLocal, User, CreditTransaction, PaymentRequest
from credit_history import get_credit_history_db, CreditHistory, UserCreditSummary

class TransactionHistoryManager:
    def __init__(self):
        self.temp_dir = "temp_files"
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
    
    def get_today_transactions_summary(self) -> Dict:
        """Get today's transaction summary"""
        db = SessionLocal()
        today = datetime.utcnow().date()
        today_start = datetime.combine(today, datetime.min.time())
        
        try:
            # Free credit transactions (via links)
            free_credit_users = db.query(CreditTransaction).filter(
                and_(
                    CreditTransaction.timestamp >= today_start,
                    CreditTransaction.transaction_type == 'free_link'
                )
            ).count()
            
            free_credit_amount = db.query(func.sum(CreditTransaction.amount)).filter(
                and_(
                    CreditTransaction.timestamp >= today_start,
                    CreditTransaction.transaction_type == 'free_link'
                )
            ).scalar() or 0
            
            # Buy credit transactions (payments)
            buy_credit_users = db.query(PaymentRequest).filter(
                and_(
                    PaymentRequest.created_at >= today_start,
                    PaymentRequest.status == 'confirmed'
                )
            ).count()
            
            buy_credit_amount = db.query(func.sum(PaymentRequest.credits_to_add)).filter(
                and_(
                    PaymentRequest.created_at >= today_start,
                    PaymentRequest.status == 'confirmed'
                )
            ).scalar() or 0
            
            # Referral transactions
            referral_users = db.query(CreditTransaction).filter(
                and_(
                    CreditTransaction.timestamp >= today_start,
                    CreditTransaction.transaction_type == 'referral'
                )
            ).count()
            
            referral_amount = db.query(func.sum(CreditTransaction.amount)).filter(
                and_(
                    CreditTransaction.timestamp >= today_start,
                    CreditTransaction.transaction_type == 'referral'
                )
            ).scalar() or 0
            
            # Total unique users who made transactions today
            total_users = db.query(func.count(func.distinct(CreditTransaction.user_id))).filter(
                CreditTransaction.timestamp >= today_start
            ).scalar() or 0
            
            return {
                'total_users': total_users,
                'free_credit': {
                    'users': free_credit_users,
                    'amount': int(free_credit_amount)
                },
                'buy_credit': {
                    'users': buy_credit_users,
                    'amount': int(buy_credit_amount)
                },
                'referral': {
                    'users': referral_users,
                    'amount': int(referral_amount)
                }
            }
            
        except Exception as e:
            print(f"Error getting today's transaction summary: {e}")
            return {
                'total_users': 0,
                'free_credit': {'users': 0, 'amount': 0},
                'buy_credit': {'users': 0, 'amount': 0},
                'referral': {'users': 0, 'amount': 0}
            }
        finally:
            db.close()
    
    def get_transactions_by_date_range(self, start_date: datetime, end_date: Optional[datetime] = None) -> List[Dict]:
        """Get transactions within a date range"""
        db = SessionLocal()
        
        if end_date is None:
            end_date = start_date + timedelta(days=1)
        
        try:
            transactions = []
            
            # Credit transactions
            credit_txs = db.query(CreditTransaction).filter(
                and_(
                    CreditTransaction.timestamp >= start_date,
                    CreditTransaction.timestamp < end_date
                )
            ).all()
            
            for tx in credit_txs:
                user = db.query(User).filter(User.user_id == tx.user_id).first()
                transactions.append({
                    'type': 'credit_transaction',
                    'user_id': tx.user_id,
                    'username': user.username if user else 'Unknown',
                    'amount': tx.amount,
                    'transaction_type': tx.transaction_type,
                    'description': tx.description,
                    'timestamp': tx.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                })
            
            # Payment requests
            payments = db.query(PaymentRequest).filter(
                and_(
                    PaymentRequest.created_at >= start_date,
                    PaymentRequest.created_at < end_date
                )
            ).all()
            
            for payment in payments:
                user = db.query(User).filter(User.user_id == payment.user_id).first()
                transactions.append({
                    'type': 'payment_request',
                    'user_id': payment.user_id,
                    'username': user.username if user else 'Unknown',
                    'amount': payment.amount,
                    'credits': payment.credits_to_add,
                    'transaction_id': payment.transaction_id,
                    'unique_id': payment.unique_id,
                    'status': payment.status,
                    'timestamp': payment.created_at.strftime('%Y-%m-%d %H:%M:%S')
                })
            
            return sorted(transactions, key=lambda x: x['timestamp'], reverse=True)
            
        except Exception as e:
            print(f"Error getting transactions by date range: {e}")
            return []
        finally:
            db.close()
    
    def create_transaction_file(self, transactions: List[Dict], filename: str) -> str:
        """Create CSV file with transaction data"""
        filepath = os.path.join(self.temp_dir, filename)
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                if not transactions:
                    csvfile.write("No transactions found for the specified period.\n")
                    return filepath
                
                fieldnames = ['timestamp', 'type', 'user_id', 'username', 'amount', 'description', 'status', 'transaction_id', 'unique_id']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for tx in transactions:
                    writer.writerow({
                        'timestamp': tx.get('timestamp', ''),
                        'type': tx.get('type', ''),
                        'user_id': tx.get('user_id', ''),
                        'username': tx.get('username', ''),
                        'amount': tx.get('amount', tx.get('credits', '')),
                        'description': tx.get('description', tx.get('transaction_type', '')),
                        'status': tx.get('status', 'completed'),
                        'transaction_id': tx.get('transaction_id', ''),
                        'unique_id': tx.get('unique_id', '')
                    })
            
            return filepath
        except Exception as e:
            print(f"Error creating transaction file: {e}")
            return None
    
    def get_payment_by_transaction_id(self, transaction_id: str) -> Optional[Dict]:
        """Track payment by transaction ID"""
        db = SessionLocal()
        
        try:
            # Search by user-provided transaction ID
            payment = db.query(PaymentRequest).filter(
                or_(
                    PaymentRequest.transaction_id == transaction_id,
                    PaymentRequest.unique_id == transaction_id
                )
            ).first()
            
            if payment:
                user = db.query(User).filter(User.user_id == payment.user_id).first()
                return {
                    'payment_id': payment.id,
                    'unique_id': payment.unique_id,
                    'user_id': payment.user_id,
                    'username': user.username if user else 'Unknown',
                    'amount': payment.amount,
                    'credits': payment.credits_to_add,
                    'transaction_id': payment.transaction_id,
                    'status': payment.status,
                    'created_at': payment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'verified_at': payment.verified_at.strftime('%Y-%m-%d %H:%M:%S') if payment.verified_at else None
                }
            
            return None
            
        except Exception as e:
            print(f"Error tracking payment: {e}")
            return None
        finally:
            db.close()
    
    def get_yesterday_transactions(self) -> List[Dict]:
        """Get yesterday's transactions"""
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        return self.get_transactions_by_date_range(
            datetime.combine(yesterday, datetime.min.time()),
            datetime.combine(yesterday + timedelta(days=1), datetime.min.time())
        )
    
    def get_last_week_transactions(self) -> List[Dict]:
        """Get last week's transactions"""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)
        return self.get_transactions_by_date_range(start_date, end_date)
    
    def get_last_month_transactions(self) -> List[Dict]:
        """Get last month's transactions"""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        return self.get_transactions_by_date_range(start_date, end_date)
    
    def cleanup_temp_files(self):
        """Clean up temporary files older than 1 hour"""
        try:
            if os.path.exists(self.temp_dir):
                for filename in os.listdir(self.temp_dir):
                    filepath = os.path.join(self.temp_dir, filename)
                    if os.path.isfile(filepath):
                        file_age = datetime.utcnow() - datetime.fromtimestamp(os.path.getctime(filepath))
                        if file_age > timedelta(hours=1):
                            os.remove(filepath)
        except Exception as e:
            print(f"Error cleaning up temp files: {e}")

# Global instance
transaction_manager = TransactionHistoryManager()