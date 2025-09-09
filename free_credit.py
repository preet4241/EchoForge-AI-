import random
import string
import requests
from datetime import datetime, timedelta
from database import SessionLocal, User, CreditTransaction, ShortLinks, UserLinks

# Helper functions
def generate_random_payload(length=12):
    """Generate random payload for credit links"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def call_shortener_api(long_url):
    """Call URL shortener API using configured shortener"""
    from database import SessionLocal, LinkShortner
    
    db = SessionLocal()
    try:
        # Get active shortener from database
        shortener = db.query(LinkShortner).filter(LinkShortner.is_active == True).first()
        
        if not shortener:
            print("No active shortener configured")
            return None
        
        # Universal API handler for any shortener
        print(f"Trying to shorten URL with {shortener.domain}")
        
        # Simple and fast API attempts - most common patterns
        try:
            import urllib.parse
            encoded_url = urllib.parse.quote(long_url, safe=':/?#[]@!$&\'()*+,;=')
            
            # Quick successful formats first
            quick_tests = [
                # NEW FORMAT - User provided
                (f"https://{shortener.domain}/api?api={shortener.api_key}&url={encoded_url}", "GET"),
                (f"https://{shortener.domain}/api?api={shortener.api_key}&url={encoded_url}&alias=", "GET"),
                # Standard formats
                (f"https://{shortener.domain}/api?key={shortener.api_key}&url={encoded_url}", "GET"),
                (f"https://api.{shortener.domain}/shorten?key={shortener.api_key}&url={encoded_url}", "GET"),
                (f"https://{shortener.domain}/shorten?api={shortener.api_key}&url={encoded_url}", "GET"),
                (f"https://{shortener.domain}/create?api={shortener.api_key}&url={encoded_url}", "GET"),
            ]
            
            for test_url, method in quick_tests:
                try:
                    print(f"🔄 Trying: {test_url}")
                    response = requests.get(test_url, timeout=5)
                    print(f"📊 Status: {response.status_code}")
                    
                    if response.status_code == 200:
                        result = response.text.strip()
                        print(f"📝 Response: {result[:100]}...")
                        
                        # Direct URL response
                        if result.startswith('http') and len(result) < 200 and '\n' not in result and not 'html' in result.lower():
                            print(f"✅ SUCCESS: {result}")
                            return result
                        
                        # JSON response
                        try:
                            json_data = response.json()
                            short_url = (json_data.get('shortenedUrl') or 
                                       json_data.get('short_url') or 
                                       json_data.get('shortUrl') or 
                                       json_data.get('url') or 
                                       json_data.get('link'))
                            if short_url and short_url != long_url:
                                print(f"✅ SUCCESS: {short_url}")
                                return short_url
                        except:
                            pass
                        
                        # Check what kind of response we got
                        if 'html' in result.lower():
                            print("❌ HTML response detected - not an API")
                        elif 'error' in result.lower():
                            print(f"❌ Error response: {result}")
                        else:
                            print(f"❓ Unknown response format: {result[:50]}")
                    else:
                        print(f"❌ HTTP {response.status_code}")
                        
                except Exception as e:
                    print(f"❌ Request failed: {e}")
                    continue
            
            # POST API attempts
            post_endpoints = [
                f"https://{shortener.domain}/api/shorten",
                f"https://api.{shortener.domain}/shorten",
                f"https://{shortener.domain}/shorten",
                f"https://{shortener.domain}/create"
            ]
            
            headers = {'Content-Type': 'application/json'}
            data = {'url': long_url, 'api_key': shortener.api_key}
            
            for endpoint in post_endpoints:
                try:
                    response = requests.post(endpoint, headers=headers, json=data, timeout=5)
                    if response.status_code in [200, 201]:
                        try:
                            result = response.json()
                            short_url = (result.get('shortenedUrl') or 
                                       result.get('short_url') or 
                                       result.get('shortUrl') or 
                                       result.get('url') or 
                                       result.get('link'))
                            if short_url and short_url != long_url:
                                print(f"✅ SUCCESS: {short_url}")
                                return short_url
                        except:
                            result = response.text.strip()
                            if result.startswith('http') and len(result) < 200:
                                print(f"✅ SUCCESS: {result}")
                                return result
                except:
                    continue
                    
        except Exception as e:
            print(f"API test failed: {e}")
            pass
        
        # If configured API fails, return None
        print(f"API shortening failed for {shortener.domain}")
        return None
            
    except Exception as e:
        print(f"Error in shortener API: {e}")
        return None
    finally:
        if db:
            db.close()

def on_free_credit_button(user_id):
    """Handle free credit button press with enhanced error handling"""
    db = SessionLocal()
    try:
        # First check if required tables exist
        try:
            from sqlalchemy import text
            db.execute(text("SELECT 1 FROM short_links LIMIT 1"))
            db.execute(text("SELECT 1 FROM user_links LIMIT 1"))
        except Exception as table_error:
            print(f"Tables missing for free credit system: {table_error}")
            return None, "❌ Free credit system is being set up. Please try again in a few minutes!"
        
        # No daily limit - users can earn unlimited credits
        
        # 1. Find any active short link this specific user has NOT used yet
        subquery = db.query(UserLinks.linkid).filter(UserLinks.userid == user_id)
        
        unused_link = db.query(ShortLinks).filter(
            ShortLinks.status == 'active',
            ~ShortLinks.id.in_(subquery)
        ).first()

        if unused_link:
            # 2a. Assign that link to this user
            user_link = UserLinks(
                userid=user_id,
                linkid=unused_link.id,
                assignedat=datetime.utcnow(),
                creditgiven=False
            )
            db.add(user_link)
            db.commit()
            
            return unused_link.url, "🔗 Click this link to earn 10 free credits! (Valid for 10 minutes)"

        else:
            # 2b. User exhausted all their unused links → generate a new one
            payload = generate_random_payload()
            
            # Create the long URL with bot start parameter
            import os
            bot_username = os.getenv('BOT_USERNAME', 'your_bot_username')
            long_url = f"https://t.me/{bot_username}?start=credit_{payload}"
            short_url = call_shortener_api(long_url)
            
            # Only proceed if we got a proper short URL
            if not short_url or short_url == long_url:
                return None, "❌ Link shortening service unavailable. Please try again later."

            # 3. Save the new link globally
            short_link = ShortLinks(
                url=short_url,
                payload=payload,
                status='active',
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(minutes=10)  # Link expires in 10 minutes
            )
            db.add(short_link)
            db.flush()  # Flush to get the ID
            
            # 4. Assign the new link to this user
            user_link = UserLinks(
                userid=user_id,
                linkid=short_link.id,
                assignedat=datetime.utcnow(),
                creditgiven=False
            )
            db.add(user_link)
            db.commit()
            
            return short_url, "🔗 New link created! Click to earn 10 free credits! (Valid for 10 minutes)"
                
    except Exception as e:
        print(f"Error in free credit button handler: {e}")
        if db:
            try:
                db.rollback()
            except:
                pass
        
        # Return user-friendly error message
        if "does not exist" in str(e):
            return None, "❌ Free credit system setup में है। कुछ देर बाद try करें!"
        else:
            return None, "❌ Technical error occurred. Please contact admin!"
    finally:
        if db:
            try:
                db.close()
            except:
                pass

def on_credit_link_click(payload):
    """Handle incoming link click with credit token"""
    db = SessionLocal()
    try:
        # 1. Look up which user & link this token belongs to
        current_time = datetime.utcnow()
        
        # Join query to find user link by payload
        result = db.query(UserLinks, ShortLinks).join(
            ShortLinks, UserLinks.linkid == ShortLinks.id
        ).filter(
            ShortLinks.payload == payload,
            ShortLinks.status == 'active'
        ).first()

        if not result:
            return "❌ Invalid or expired link."

        user_link, short_link = result
        
        # Check if link has expired
        if short_link.expires_at and short_link.expires_at < current_time:
            return "❌ This link has expired."
            
        if user_link.creditgiven:
            return "⚠️ You've already claimed this credit."

        # 2. Grant credit and mark as given
        credit_amount = 10.0  # Credits to give
        
        # Update user credits
        user = db.query(User).filter(User.user_id == user_link.userid).first()
        if user:
            user.credits = user.credits + credit_amount
            
            # Mark link as used
            user_link.creditgiven = True
            user_link.creditedat = current_time
            
            # Log the transaction
            transaction = CreditTransaction(
                user_id=user_link.userid,
                amount=credit_amount,
                transaction_type='free_credit',
                description='Free credit claimed via link'
            )
            db.add(transaction)
            db.commit()
            
            # 3. Return success message
            return f"🎉 Congratulations! You've received {credit_amount} credits. Your balance is now {user.credits} credits."
        else:
            return "❌ User not found."
            
    except Exception as e:
        print(f"Error in credit link click handler: {e}")
        db.rollback()
        return "❌ An error occurred while processing your request."
    finally:
        db.close()

def check_daily_limit(user_id):
    """Check if user has reached daily free credit limit with enhanced error handling"""
    db = SessionLocal()
    try:
        # Check if table exists first
        try:
            from sqlalchemy import text
            db.execute(text("SELECT 1 FROM user_links LIMIT 1"))
        except Exception as table_error:
            print(f"UserLinks table missing in daily limit check: {table_error}")
            return False  # Allow if table doesn't exist yet
        
        # Count credits given today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        credits_today = db.query(UserLinks).filter(
            UserLinks.userid == user_id,
            UserLinks.creditgiven == True,
            UserLinks.creditedat >= today_start
        ).count()
        
        # Allow 3 free credits per day
        daily_limit = 3
        return credits_today >= daily_limit
        
    except Exception as e:
        print(f"Error checking daily limit: {e}")
        return False  # Return False on error to allow user to proceed
    finally:
        if db:
            try:
                db.close()
            except:
                pass

def get_user_credit_stats(user_id):
    """Get user's credit statistics with enhanced error handling"""
    db = SessionLocal()
    try:
        # Check if tables exist first
        try:
            from sqlalchemy import text
            db.execute(text("SELECT 1 FROM user_links LIMIT 1"))
            tables_exist = True
        except Exception as table_error:
            print(f"UserLinks table missing in credit stats: {table_error}")
            tables_exist = False
        
        if not tables_exist:
            # Return default stats if tables don't exist
            user = db.query(User).filter(User.user_id == user_id).first()
            current_balance = user.credits if user else 0.0
            return {
                'credits_today': 0,
                'total_free_credits': 0,
                'current_balance': current_balance,
                'daily_limit': 3,
                'remaining_today': 3
            }
        
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Credits earned today
        credits_today = db.query(UserLinks).filter(
            UserLinks.userid == user_id,
            UserLinks.creditgiven == True,
            UserLinks.creditedat >= today_start
        ).count()
        
        # Total credits earned via free credit system
        total_free_credits = db.query(UserLinks).filter(
            UserLinks.userid == user_id,
            UserLinks.creditgiven == True
        ).count()
        
        # Current user balance
        user = db.query(User).filter(User.user_id == user_id).first()
        current_balance = user.credits if user else 0.0
        
        return {
            'credits_today': credits_today,
            'total_free_credits': total_free_credits,
            'current_balance': current_balance,
            'daily_limit': 3,
            'remaining_today': max(0, 3 - credits_today)
        }
        
    except Exception as e:
        print(f"Error getting credit stats: {e}")
        # Return safe default values
        try:
            user = db.query(User).filter(User.user_id == user_id).first()
            current_balance = user.credits if user else 0.0
        except:
            current_balance = 0.0
        
        return {
            'credits_today': 0,
            'total_free_credits': 0,
            'current_balance': current_balance,
            'daily_limit': 3,
            'remaining_today': 3
        }
    finally:
        if db:
            try:
                db.close()
            except:
                pass