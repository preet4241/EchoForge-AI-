"""
Message Deletion Service for Telegram TTS Bot
Provides comprehensive message tracking and automated deletion for cleaner chats
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
from pyrogram.client import Client
from pyrogram.types import Message, CallbackQuery
from sqlalchemy.orm import Session
from database import SessionLocal, MessageTracking

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MessageType:
    """Message type classifications for deletion timing"""
    # Quick cleanup - delete after user interaction
    STATUS = "status"                    # Status/confirmation messages
    PROMPT = "prompt"                   # Input prompts that expect user response
    ERROR = "error"                     # Error messages
    
    # Medium cleanup - delete after reasonable time
    MENU = "menu"                       # Menu/keyboard messages
    INFO = "info"                       # Information displays
    TTS_RESULT = "tts_result"          # TTS audio result messages
    
    # Sensitive cleanup - delete quickly for privacy
    PAYMENT = "payment"                 # Payment-related messages
    ADMIN = "admin"                     # Owner/admin operations
    
    # Long-term - keep longer for reference
    WELCOME = "welcome"                 # Welcome/onboarding messages
    HELP = "help"                       # Help and documentation
    
    # Permanent - don't auto-delete
    PERMANENT = "permanent"             # Important messages to keep

class MessageDeletionService:
    """
    Comprehensive message deletion service with tracking and scheduling
    """
    
    def __init__(self, bot_client: Client):
        self.bot = bot_client
        self.deletion_timings = {
            MessageType.STATUS: 10,      # 10 seconds
            MessageType.PROMPT: 30,      # 30 seconds (or when user responds)
            MessageType.ERROR: 15,       # 15 seconds
            MessageType.MENU: 60,        # 1 minute
            MessageType.INFO: 45,        # 45 seconds
            MessageType.TTS_RESULT: 0,   # Never delete - keep audio files permanently
            MessageType.PAYMENT: 8,      # 8 seconds (quick for privacy)
            MessageType.ADMIN: 20,       # 20 seconds
            MessageType.WELCOME: 300,    # 5 minutes
            MessageType.HELP: 180,       # 3 minutes
            MessageType.PERMANENT: 0     # Never delete
        }
        self._deletion_tasks: Dict[str, asyncio.Task] = {}
        self._running = False

    async def start_deletion_service(self):
        """Start the background deletion service"""
        if self._running:
            return
        
        self._running = True
        logger.info("🧹 Message deletion service started")
        
        # Start the cleanup task
        asyncio.create_task(self._periodic_cleanup())

    async def stop_deletion_service(self):
        """Stop the background deletion service"""
        self._running = False
        
        # Cancel all pending deletion tasks
        for task in self._deletion_tasks.values():
            if not task.done():
                task.cancel()
        
        self._deletion_tasks.clear()
        logger.info("🛑 Message deletion service stopped")

    def track_message(
        self,
        message: Union[Message, int],
        chat_id: Optional[int] = None,
        message_type: str = MessageType.INFO,
        user_id: Optional[int] = None,
        custom_delay: Optional[int] = None,
        context: Optional[str] = None,
        related_message_id: Optional[int] = None
    ) -> bool:
        """
        Track a message for future deletion
        
        Args:
            message: Message object or message ID
            chat_id: Chat ID (required if message is int)
            message_type: Type of message for deletion timing
            user_id: User associated with message
            custom_delay: Custom deletion delay in seconds
            context: Additional context about the message
            related_message_id: ID of related message (for linking)
            
        Returns:
            bool: Success status
        """
        try:
            # Extract message info
            if isinstance(message, Message):
                msg_id = message.id
                chat_id = message.chat.id
                if not user_id and message.from_user:
                    user_id = message.from_user.id
            else:
                msg_id = message
                if not chat_id:
                    logger.error("Chat ID required when tracking message by ID")
                    return False

            # Skip permanent messages
            if message_type == MessageType.PERMANENT:
                logger.debug(f"Skipping permanent message tracking: {msg_id}")
                return True

            # Determine deletion timing
            delete_after = custom_delay or self.deletion_timings.get(message_type, 30)
            scheduled_delete_at = datetime.utcnow() + timedelta(seconds=delete_after)

            # Store in database
            db = SessionLocal()
            try:
                tracking_entry = MessageTracking(
                    chat_id=chat_id,
                    message_id=msg_id,
                    user_id=user_id,
                    message_type=message_type,
                    delete_after_seconds=delete_after,
                    scheduled_delete_at=scheduled_delete_at,
                    related_message_id=related_message_id,
                    context=context
                )
                
                db.add(tracking_entry)
                db.commit()
                
                # Schedule deletion task (only if not permanent)
                if delete_after > 0:
                    task_key = f"{chat_id}_{msg_id}"
                    task = asyncio.create_task(
                        self._schedule_deletion(chat_id, msg_id, delete_after, tracking_entry.id)
                    )
                    self._deletion_tasks[task_key] = task
                
                if delete_after == 0:
                    logger.debug(f"📝 Tracked message {msg_id} in chat {chat_id} as PERMANENT (no deletion)")
                else:
                    logger.debug(f"📝 Tracked message {msg_id} in chat {chat_id} for deletion in {delete_after}s")
                return True
                
            except Exception as db_error:
                logger.error(f"Database error tracking message: {db_error}")
                db.rollback()
                return False
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error tracking message: {e}")
            return False

    async def track_and_schedule_deletion(
        self,
        sent_message: Message,
        message_type: str = MessageType.INFO,
        user_id: Optional[int] = None,
        custom_delay: Optional[int] = None,
        context: Optional[str] = None
    ) -> Message:
        """
        Convenience method to track a just-sent message
        
        Args:
            sent_message: The message that was just sent
            message_type: Type of message for deletion timing
            user_id: User associated with message
            custom_delay: Custom deletion delay in seconds
            context: Additional context about the message
            
        Returns:
            Message: The original message (for chaining)
        """
        if sent_message:
            self.track_message(
                sent_message,
                message_type=message_type,
                user_id=user_id,
                custom_delay=custom_delay,
                context=context
            )
        return sent_message

    async def delete_related_messages(self, user_id: int, context: str):
        """
        Delete all messages with specific context for a user
        
        Args:
            user_id: User ID to filter messages
            context: Context to match
        """
        db = SessionLocal()
        try:
            messages = db.query(MessageTracking).filter(
                MessageTracking.user_id == user_id,
                MessageTracking.context == context,
                MessageTracking.is_deleted == False
            ).all()
            
            for msg_entry in messages:
                await self._delete_single_message(msg_entry.chat_id, msg_entry.message_id)
                msg_entry.is_deleted = True
                msg_entry.delete_attempted_at = datetime.utcnow()
            
            db.commit()
            logger.info(f"🧹 Deleted {len(messages)} related messages for user {user_id}, context: {context}")
            
        except Exception as e:
            logger.error(f"Error deleting related messages: {e}")
            db.rollback()
        finally:
            db.close()

    async def cancel_deletion(self, chat_id: int, message_id: int):
        """
        Cancel scheduled deletion for a specific message
        
        Args:
            chat_id: Chat ID
            message_id: Message ID
        """
        task_key = f"{chat_id}_{message_id}"
        
        # Cancel the scheduled task
        if task_key in self._deletion_tasks:
            task = self._deletion_tasks[task_key]
            if not task.done():
                task.cancel()
            del self._deletion_tasks[task_key]
        
        # Update database
        db = SessionLocal()
        try:
            tracking_entry = db.query(MessageTracking).filter(
                MessageTracking.chat_id == chat_id,
                MessageTracking.message_id == message_id
            ).first()
            
            if tracking_entry:
                tracking_entry.is_deleted = True  # Mark as processed
                tracking_entry.delete_error = "Deletion cancelled"
                db.commit()
                
        except Exception as e:
            logger.error(f"Error cancelling deletion: {e}")
            db.rollback()
        finally:
            db.close()

    async def _schedule_deletion(self, chat_id: int, message_id: int, delay: int, tracking_id: int):
        """
        Schedule deletion of a message after delay
        
        Args:
            chat_id: Chat ID
            message_id: Message ID
            delay: Delay in seconds
            tracking_id: Database tracking entry ID
        """
        try:
            await asyncio.sleep(delay)
            await self._delete_single_message(chat_id, message_id)
            
            # Update database
            db = SessionLocal()
            try:
                tracking_entry = db.query(MessageTracking).get(tracking_id)
                if tracking_entry:
                    tracking_entry.is_deleted = True
                    tracking_entry.delete_attempted_at = datetime.utcnow()
                    db.commit()
            except Exception as db_error:
                logger.error(f"Error updating deletion status: {db_error}")
                db.rollback()
            finally:
                db.close()
                
        except asyncio.CancelledError:
            logger.debug(f"Deletion cancelled for message {message_id} in chat {chat_id}")
        except Exception as e:
            logger.error(f"Error in scheduled deletion: {e}")
            
            # Update database with error
            db = SessionLocal()
            try:
                tracking_entry = db.query(MessageTracking).get(tracking_id)
                if tracking_entry:
                    tracking_entry.delete_attempted_at = datetime.utcnow()
                    tracking_entry.delete_error = str(e)
                    db.commit()
            except Exception as db_error:
                logger.error(f"Error updating deletion error: {db_error}")
                db.rollback()
            finally:
                db.close()
        finally:
            # Clean up task reference
            task_key = f"{chat_id}_{message_id}"
            self._deletion_tasks.pop(task_key, None)

    async def _delete_single_message(self, chat_id: int, message_id: int):
        """
        Attempt to delete a single message
        
        Args:
            chat_id: Chat ID
            message_id: Message ID
        """
        try:
            await self.bot.delete_messages(chat_id, message_id)
            logger.debug(f"✅ Deleted message {message_id} in chat {chat_id}")
        except Exception as e:
            error_msg = str(e).lower()
            
            # Handle common deletion errors gracefully
            if any(phrase in error_msg for phrase in ['message not found', 'message to delete not found']):
                logger.debug(f"Message {message_id} already deleted in chat {chat_id}")
            elif 'message can\'t be deleted' in error_msg:
                logger.warning(f"Cannot delete message {message_id} in chat {chat_id} (permissions/old message)")
            else:
                logger.error(f"Failed to delete message {message_id} in chat {chat_id}: {e}")
            raise

    async def _periodic_cleanup(self):
        """
        Periodic cleanup of orphaned deletion tasks and expired messages
        """
        while self._running:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                
                db = SessionLocal()
                try:
                    # Find messages that should have been deleted but weren't
                    current_time = datetime.utcnow()
                    orphaned_messages = db.query(MessageTracking).filter(
                        MessageTracking.scheduled_delete_at < current_time,
                        MessageTracking.is_deleted == False,
                        MessageTracking.delete_attempted_at.is_(None)
                    ).all()
                    
                    if orphaned_messages:
                        logger.info(f"🧹 Found {len(orphaned_messages)} orphaned messages for cleanup")
                        
                        for msg_entry in orphaned_messages:
                            try:
                                await self._delete_single_message(msg_entry.chat_id, msg_entry.message_id)
                                msg_entry.is_deleted = True
                            except:
                                pass  # Ignore errors in cleanup
                            
                            msg_entry.delete_attempted_at = current_time
                        
                        db.commit()
                    
                    # Clean up old tracking entries (older than 24 hours)
                    cleanup_threshold = current_time - timedelta(hours=24)
                    old_entries = db.query(MessageTracking).filter(
                        MessageTracking.created_at < cleanup_threshold
                    )
                    deleted_count = old_entries.count()
                    old_entries.delete()
                    db.commit()
                    
                    if deleted_count > 0:
                        logger.info(f"🗑️ Cleaned up {deleted_count} old tracking entries")
                        
                except Exception as db_error:
                    logger.error(f"Database error in periodic cleanup: {db_error}")
                    db.rollback()
                finally:
                    db.close()
                    
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get deletion service statistics
        
        Returns:
            Dict with service statistics
        """
        db = SessionLocal()
        try:
            total_tracked = db.query(MessageTracking).count()
            deleted_count = db.query(MessageTracking).filter(MessageTracking.is_deleted == True).count()
            pending_count = db.query(MessageTracking).filter(MessageTracking.is_deleted == False).count()
            
            return {
                'total_tracked': total_tracked,
                'successfully_deleted': deleted_count,
                'pending_deletion': pending_count,
                'active_tasks': len(self._deletion_tasks),
                'service_running': self._running
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {'error': str(e)}
        finally:
            db.close()

# Global instance
message_deletion_service: Optional[MessageDeletionService] = None

def get_deletion_service() -> Optional[MessageDeletionService]:
    """Get the global message deletion service instance"""
    return message_deletion_service

def initialize_deletion_service(bot_client: Client):
    """Initialize the global message deletion service"""
    global message_deletion_service
    message_deletion_service = MessageDeletionService(bot_client)
    return message_deletion_service

# Message type classification helpers
def classify_message_type(text: str, callback_data: Optional[str] = None, is_owner: bool = False) -> str:
    """
    Automatically classify message type based on content
    
    Args:
        text: Message text content
        callback_data: Callback data if from inline button
        is_owner: Whether message is for/from owner
        
    Returns:
        str: Message type classification
    """
    if not text:
        return MessageType.INFO
    
    text_lower = text.lower()
    
    # Payment-related messages
    if any(word in text_lower for word in ['payment', 'rupees', 'transaction', 'qr code', 'screenshot']):
        return MessageType.PAYMENT
    
    # Admin/Owner messages
    if is_owner or any(word in text_lower for word in ['owner', 'admin', 'control panel', 'master']):
        return MessageType.ADMIN
    
    # Error messages
    if any(word in text_lower for word in ['error', 'failed', 'invalid', 'kuch galat', 'technical issue']):
        return MessageType.ERROR
    
    # Status/confirmation messages
    if any(word in text_lower for word in ['success', 'completed', 'confirmed', 'done', 'saved', 'updated']):
        return MessageType.STATUS
    
    # Prompts expecting user input
    if any(word in text_lower for word in ['send', 'enter', 'type', 'provide', 'kripaya', 'bheje']):
        return MessageType.PROMPT
    
    # Welcome messages
    if any(word in text_lower for word in ['welcome', 'namaste', 'namaskar', 'hello']):
        return MessageType.WELCOME
    
    # Help messages
    if any(word in text_lower for word in ['help', 'guide', 'how to', 'instructions']):
        return MessageType.HELP
    
    # TTS results (contains audio file indicators)
    if any(word in text_lower for word in ['audio', 'voice', 'tts', 'speech']):
        return MessageType.TTS_RESULT
    
    # Menu/keyboard messages (based on callback data)
    if callback_data or any(word in text_lower for word in ['select', 'choose', 'option', 'menu']):
        return MessageType.MENU
    
    # Default to info
    return MessageType.INFO

def get_context_from_callback(callback_data: str) -> str:
    """
    Extract context from callback data for message grouping
    
    Args:
        callback_data: Telegram callback data
        
    Returns:
        str: Context for grouping related messages
    """
    if not callback_data:
        return "general"
    
    # Payment flows
    if callback_data.startswith(('buy_credit', 'payment', 'confirm_payment', 'cancel_payment')):
        return "payment_flow"
    
    # Owner panels
    if callback_data.startswith(('owner_', 'back_to_owner')):
        return "owner_panel"
    
    # User panels
    if callback_data.startswith(('user_', 'back_to_user')):
        return "user_panel"
    
    # Settings
    if callback_data.startswith('settings_'):
        return "settings"
    
    # TTS
    if callback_data.startswith(('tts_', 'voice_')):
        return "tts_flow"
    
    # Credits
    if callback_data.startswith(('credit', 'referral')):
        return "credit_system"
    
    return "general"

# Enhanced convenience wrapper functions
async def track_message_for_deletion(
    message: Union[Message, int],
    message_type: Optional[str] = None,
    chat_id: Optional[int] = None,
    user_id: Optional[int] = None,
    custom_delay: Optional[int] = None,
    context: Optional[str] = None,
    auto_classify: bool = True
) -> bool:
    """
    Convenience function to track a message for deletion with auto-classification
    
    Args:
        message: Message object or message ID
        message_type: Type of message (if None, will auto-classify)
        chat_id: Chat ID (required if message is int)
        user_id: User associated with message
        custom_delay: Custom deletion delay in seconds
        context: Context for grouping (if None, will auto-determine)
        auto_classify: Whether to auto-classify message type
        
    Returns:
        bool: Success status
    """
    service = get_deletion_service()
    if not service:
        return False
    
    # Auto-classify message type if not provided
    if message_type is None and auto_classify and isinstance(message, Message):
        is_owner = user_id == int(os.getenv('OWNER_ID', '0')) if user_id else False
        message_type = classify_message_type(message.text or "", is_owner=is_owner)
    
    # Use default if still None
    if message_type is None:
        message_type = MessageType.INFO
    
    return service.track_message(
        message=message,
        chat_id=chat_id,
        message_type=message_type,
        user_id=user_id,
        custom_delay=custom_delay,
        context=context
    )

async def track_sent_message(
    sent_message: Message,
    message_type: Optional[str] = None,
    user_id: Optional[int] = None,
    custom_delay: Optional[int] = None,
    context: Optional[str] = None
) -> Message:
    """
    Track a message that was just sent and return it for chaining
    
    Args:
        sent_message: The message that was sent
        message_type: Type of message (auto-classified if None)
        user_id: User associated with message
        custom_delay: Custom deletion delay in seconds
        context: Context for grouping
        
    Returns:
        Message: The original message (for method chaining)
    """
    if sent_message:
        await track_message_for_deletion(
            sent_message,
            message_type=message_type,
            user_id=user_id,
            custom_delay=custom_delay,
            context=context
        )
    return sent_message

async def delete_messages_by_context(user_id: int, context: str):
    """
    Convenience function to delete messages by context
    """
    service = get_deletion_service()
    if service:
        await service.delete_related_messages(user_id, context)

async def cleanup_conversation(user_id: int, keep_last_n: int = 1):
    """
    Clean up conversation keeping only the last N messages
    
    Args:
        user_id: User ID to clean up conversation for
        keep_last_n: Number of most recent messages to keep
    """
    service = get_deletion_service()
    if not service:
        return
    
    db = SessionLocal()
    try:
        # Get user's messages ordered by creation time
        user_messages = db.query(MessageTracking).filter(
            MessageTracking.user_id == user_id,
            MessageTracking.is_deleted == False
        ).order_by(MessageTracking.created_at.desc()).all()
        
        # Skip the most recent N messages
        messages_to_delete = user_messages[keep_last_n:] if len(user_messages) > keep_last_n else []
        
        for msg_entry in messages_to_delete:
            try:
                await service._delete_single_message(msg_entry.chat_id, msg_entry.message_id)
                msg_entry.is_deleted = True
                msg_entry.delete_attempted_at = datetime.utcnow()
            except:
                pass  # Ignore deletion errors
        
        if messages_to_delete:
            db.commit()
            logger.info(f"🧹 Cleaned up {len(messages_to_delete)} old messages for user {user_id}")
            
    except Exception as e:
        logger.error(f"Error in conversation cleanup: {e}")
        db.rollback()
    finally:
        db.close()