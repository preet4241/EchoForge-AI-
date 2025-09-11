import os
import asyncio
import tempfile
import re
import unicodedata
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import edge_tts

class TTSService:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=3)
        
        # 10 Completely UNIQUE High-Quality Voice Mapping (5 Male + 5 Female)
        # Each voice uses a different neural voice for maximum variety
        self.voice_mapping = {
            # === MALE VOICES (5 completely different) ===
            'male1': {
                'voice': 'hi-IN-MadhurNeural', 
                'name': 'Deep Bass',
                'lang': 'hi',
                'description': 'Deep masculine Hindi voice, perfect for narration'
            },
            'male2': {
                'voice': 'en-IN-PrabhatNeural', 
                'name': 'Ocean Calm',
                'lang': 'en',
                'description': 'Calm, professional English India voice'
            },
            'male3': {
                'voice': 'hi-IN-ArjunNeural', 
                'name': 'Professional',
                'lang': 'hi', 
                'description': 'Clear, authoritative Hindi business voice'
            },
            'male4': {
                'voice': 'en-IN-ArjunNeural', 
                'name': 'Energetic',
                'lang': 'en',
                'description': 'Dynamic, energetic English India voice'
            },
            'male5': {
                'voice': 'hi-IN-RehaanNeural', 
                'name': 'Warm Tone',
                'lang': 'hi',
                'description': 'Warm, friendly Hindi conversational voice'
            },
            
            # === FEMALE VOICES (5 completely different) ===
            'female1': {
                'voice': 'hi-IN-SwaraNeural', 
                'name': 'Honey Sweet',
                'lang': 'hi',
                'description': 'Sweet, melodious Hindi voice with emotional depth'
            },
            'female2': {
                'voice': 'en-IN-NeerjaNeural', 
                'name': 'Crystal Clear',
                'lang': 'en',
                'description': 'Clear, crisp English India voice, perfect for announcements'
            },
            'female3': {
                'voice': 'hi-IN-AnanyaNeural', 
                'name': 'Soft Whisper',
                'lang': 'hi',
                'description': 'Gentle, soothing Hindi voice, ideal for relaxation'
            },
            'female4': {
                'voice': 'en-IN-AashiNeural', 
                'name': 'Bright Star',
                'lang': 'en',
                'description': 'Bright, cheerful English India voice, great for storytelling'
            },
            'female5': {
                'voice': 'hi-IN-KavyaNeural', 
                'name': 'Melodic Angel',
                'lang': 'hi',
                'description': 'Melodic, expressive Hindi voice with artistic flair'
            },
            
            # === ADDITIONAL UNIQUE VOICES for proper pairing ===
            'male6': {
                'voice': 'en-IN-KunalNeural', 
                'name': 'Strong Voice',
                'lang': 'en',
                'description': 'Strong, confident English India voice'
            },
            'female6': {
                'voice': 'en-IN-AartiNeural', 
                'name': 'Gentle Tone',
                'lang': 'en',
                'description': 'Gentle, caring English India voice'
            }
        }
    
    async def text_to_speech_with_voice(self, text: str, voice_type: str = 'male1') -> BytesIO | None:
        """Convert text to speech with specific voice type using intelligent language detection"""
        try:
            # Get voice configuration
            voice_config = self.voice_mapping.get(voice_type, self.voice_mapping['male1'])
            
            # Language detection for optimization (but NO auto-switching)
            detected_lang = self._detect_language(text)
            
            # Use EXACT voice selected by user - NO auto-switching to ensure unique voices
            selected_voice = voice_config['voice']
            
            # Debug: Show exactly what text is being processed
            print(f"🎤 Voice: {voice_config['name']} | Detected: {detected_lang} | Using: {selected_voice} (NO AUTO-SWITCH)")
            print(f"📝 Text to convert: '{text}' (Length: {len(text)} chars, Words: {len(text.split())})")
            
            # Generate high-quality audio with enhanced settings
            audio_data = await self._generate_enhanced_edge_tts(text, selected_voice, detected_lang)
            return audio_data
            
        except Exception as e:
            print(f"🔴 Edge TTS Error: {e}")
            # Intelligent fallback with voice preference
            return await self._intelligent_fallback(text, voice_type)
    
    def _detect_language(self, text: str) -> str:
        """Advanced language detection for Hindi (Devanagari + Roman), English text"""
        try:
            # Clean text for analysis
            clean_text = text.strip().lower()
            
            # Count Devanagari characters (Hindi)
            hindi_chars = sum(1 for char in clean_text if '\u0900' <= char <= '\u097F')
            
            # Count Latin characters (English/Roman Hindi)
            english_chars = sum(1 for char in clean_text if char.isascii() and char.isalpha())
            
            # Roman Hindi detection - strictly Hindi words only (removed ambiguous English words)
            roman_hindi_words = {
                # Greetings and common expressions
                'namaste', 'namaskar', 'dhanyawad', 'shukriya', 'alvida', 'jai', 'hind',
                # Basic Hindi words 
                'kya', 'hai', 'hain', 'ka', 'ki', 'ke', 'ko', 'se', 'me', 'par', 'mein',
                'aur', 'ya', 'nahi', 'nahin', 'haan', 'han', 'ji', 'sahab', 'bhai', 'didi', 'papa', 'mama',
                # Hindi-specific words (not commonly used in English)
                'ghar', 'paisa', 'paise', 'rupya', 'rupee', 'samay', 'din', 'rat', 'subah', 'sham', 'dopahar',
                'khana', 'paani', 'chai', 'doodh', 'roti', 'chawal', 'dal', 'sabzi', 'acha', 'accha',
                'bura', 'burra', 'thik', 'theek', 'sahi', 'galat', 'kaise', 'kahan', 'kab', 'kyun', 'kyu', 'kaun',
                'kitna', 'kitni', 'kitne', 'bohot', 'bahut', 'thoda', 'zyada', 'jyada', 'kam', 'jaldi', 'der',
                'chalo', 'aao', 'jao', 'ruko', 'dekho', 'suno', 'bolo', 'kaho', 'batao', 'poocho', 'pucho',
                'samjha', 'samjhi', 'samjhe', 'pata', 'malum', 'jaanta', 'jaanti', 'jaante', 'karta', 'karti', 'karte',
                'hota', 'hoti', 'hote', 'deta', 'deti', 'dete', 'leta', 'leti', 'lete', 'aata', 'aati', 'aate',
                'jaata', 'jaati', 'jaate', 'rahta', 'rahti', 'rahte', 'khelna', 'padhna', 'likhna', 'dekhna',
                'sunna', 'bolna', 'kehna', 'batana', 'puchna', 'samajhna', 'seekhna', 'sikhna', 'karna', 'hona',
                'dena', 'lena', 'aana', 'jana', 'rehna', 'rahna', 'kyunki', 'isliye', 'lekin',
                # Additional distinctly Hindi words
                'bharat', 'hindustan', 'desh', 'sarkar', 'vidya', 'gyan', 'shaadi', 'byah', 'ganga', 'yamuna'
            }
            
            # Split text into words and check for Roman Hindi
            words = re.findall(r'\b[a-z]+\b', clean_text)
            roman_hindi_count = sum(1 for word in words if word in roman_hindi_words)
            
            # Calculate percentages
            total_chars = len([c for c in clean_text if c.isalpha()])
            total_words = len(words) if words else 1
            
            if total_chars == 0:
                return 'en'  # Default to English for non-alphabetic text
            
            hindi_ratio = hindi_chars / total_chars
            roman_hindi_ratio = roman_hindi_count / total_words
            
            print(f"🔍 Language Analysis: Devanagari={hindi_ratio:.2f}, Roman Hindi={roman_hindi_ratio:.2f}")
            
            # Enhanced language detection logic with stricter thresholds
            if hindi_ratio > 0.6:  # 60% Devanagari Hindi characters
                print("🎯 Detected: Devanagari Hindi")
                return 'hi'
            elif roman_hindi_ratio >= 0.4:  # 40% Roman Hindi words - increased threshold
                print("🎯 Detected: Roman Hindi")
                return 'hi'
            elif hindi_ratio > 0.3:  # Substantial Devanagari presence
                print("🎯 Detected: Mixed Hindi (Devanagari dominant)")
                return 'hi'
            else:
                print("🎯 Detected: English")
                return 'en'  # Default to English
                
        except Exception as e:
            print(f"⚠️ Language detection error: {e}")
            return 'en'  # Default fallback
    
    def _get_optimized_voice(self, voice_config: dict, detected_lang: str, voice_type: str) -> str:
        """Get optimized voice based on detected language and user preference with explicit EN↔HI pairing"""
        try:
            user_voice = voice_config['voice']
            voice_lang = voice_config['lang']
            
            # If detected language matches voice language, use as-is
            if detected_lang == voice_lang:
                return user_voice
            
            # Explicit same-gender EN↔HI voice pairing dictionary
            voice_language_pairs = {
                # Male Hindi ↔ Male English pairings
                'male1': 'male2',  # Hindi Deep Bass ↔ English Ocean Calm
                'male2': 'male1',  # English Ocean Calm ↔ Hindi Deep Bass
                'male3': 'male4',  # Hindi Professional ↔ English Energetic
                'male4': 'male3',  # English Energetic ↔ Hindi Professional
                'male5': 'male6',  # Hindi Warm Tone ↔ English Strong Voice (UNIQUE!)
                'male6': 'male5',  # English Strong Voice ↔ Hindi Warm Tone
                
                # Female Hindi ↔ Female English pairings
                'female1': 'female2',  # Hindi Honey Sweet ↔ English Crystal Clear
                'female2': 'female1',  # English Crystal Clear ↔ Hindi Honey Sweet
                'female3': 'female4',  # Hindi Soft Whisper ↔ English Bright Star
                'female4': 'female3',  # English Bright Star ↔ Hindi Soft Whisper
                'female5': 'female6',  # Hindi Melodic Angel ↔ English Gentle Tone (UNIQUE!)
                'female6': 'female5',  # English Gentle Tone ↔ Hindi Melodic Angel
            }
            
            # Smart voice switching for language mismatch using explicit pairing
            if detected_lang != voice_lang and voice_type in voice_language_pairs:
                paired_voice_type = voice_language_pairs[voice_type]
                
                if paired_voice_type in self.voice_mapping:
                    paired_voice_config = self.voice_mapping[paired_voice_type]
                    
                    # Verify the paired voice matches the detected language
                    if paired_voice_config['lang'] == detected_lang:
                        print(f"🔄 Auto-switched from {voice_config['name']} ({voice_lang.upper()}) to {paired_voice_config['name']} ({detected_lang.upper()})")
                        return paired_voice_config['voice']
            
            # Fallback to user's selected voice if no pairing found
            print(f"⚠️ No language pair found for {voice_type}, using original voice")
            return user_voice
            
        except Exception as e:
            print(f"⚠️ Voice optimization error: {e}")
            return voice_config['voice']
    
    async def _generate_enhanced_edge_tts(self, text: str, voice: str, detected_lang: str) -> BytesIO:
        """Generate high-quality TTS using Edge TTS with enhanced settings and connection stability"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                print(f"🔄 TTS Attempt {attempt + 1}/{max_retries} for voice: {voice}")
                
                # Clean the text to ensure no extra content
                clean_text = text.strip()
                print(f"🧹 Cleaned text: '{clean_text}' (Length: {len(clean_text)} chars)")
                
                # Simple direct text-to-speech (NO SSML to avoid markup being read as text)
                if len(clean_text) > 0:
                    print(f"🎯 Direct TTS: Using voice '{voice}' for text: '{clean_text}'")
                    # Direct TTS without SSML to ensure clean, short audio
                    communicate = edge_tts.Communicate(clean_text, voice)
                else:
                    raise Exception("Empty text provided for TTS")
                
                # Generate high-quality audio data with timeout
                audio_data = BytesIO()
                try:
                    # Set timeout for streaming
                    stream_timeout = 30  # 30 seconds timeout
                    start_time = asyncio.get_event_loop().time()
                    
                    async for chunk in communicate.stream():
                        # Check for timeout
                        if asyncio.get_event_loop().time() - start_time > stream_timeout:
                            raise asyncio.TimeoutError("TTS streaming timeout")
                            
                        if chunk["type"] == "audio":
                            audio_data.write(chunk["data"])
                    
                except asyncio.TimeoutError as te:
                    print(f"⏰ TTS streaming timeout on attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        raise te
                
                audio_data.seek(0)
                audio_data.name = "enhanced_tts_audio.mp3"
                
                # Validate audio data
                if audio_data.getvalue():
                    print(f"✅ Generated {len(audio_data.getvalue())} bytes of audio on attempt {attempt + 1}")
                    return audio_data
                else:
                    raise Exception("Empty audio data generated")
                    
            except Exception as e:
                print(f"🔴 TTS attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    print(f"⏳ Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5  # Exponential backoff
                else:
                    print(f"🔴 All {max_retries} attempts failed")
                    raise e
    
    async def _intelligent_fallback(self, text: str, voice_type: str) -> BytesIO | None:
        """Enhanced intelligent fallback with robust connection handling and multiple retry strategies"""
        try:
            print(f"🔄 Attempting intelligent fallback for voice: {voice_type}")
            
            # Strategy 1: Try alternative voice of same gender with retry logic
            gender = 'male' if 'male' in voice_type else 'female'
            alternative_voices = [
                (alt_voice_type, alt_config) 
                for alt_voice_type, alt_config in self.voice_mapping.items() 
                if gender in alt_voice_type and alt_voice_type != voice_type
            ]
            
            for alt_voice_type, alt_config in alternative_voices:
                for retry_attempt in range(2):  # 2 attempts per alternative voice
                    try:
                        print(f"🔄 Trying alternative voice: {alt_config['name']} (attempt {retry_attempt + 1})")
                        communicate = edge_tts.Communicate(text, alt_config['voice'])
                        audio_data = BytesIO()
                        
                        # Add timeout for fallback attempts
                        start_time = asyncio.get_event_loop().time()
                        timeout = 20  # Shorter timeout for fallbacks
                        
                        async for chunk in communicate.stream():
                            if asyncio.get_event_loop().time() - start_time > timeout:
                                raise asyncio.TimeoutError("Fallback streaming timeout")
                            if chunk["type"] == "audio":
                                audio_data.write(chunk["data"])
                        
                        audio_data.seek(0)
                        audio_data.name = "fallback_tts_audio.mp3"
                        if audio_data.getvalue():
                            print(f"✅ Fallback successful with {alt_config['name']}")
                            return audio_data
                            
                    except Exception as fallback_error:
                        print(f"⚠️ Alternative voice {alt_config['name']} failed (attempt {retry_attempt + 1}): {fallback_error}")
                        if retry_attempt == 0:  # Only wait between attempts, not after last attempt
                            await asyncio.sleep(1)
                        continue
            
            # Strategy 2: Use enhanced gTTS as last resort (removed cross-gender fallback)
            print(f"🔄 Using enhanced gTTS fallback...")
            return await self._generate_gtts_fallback_enhanced(text)
            
        except Exception as e:
            print(f"🔴 All fallback strategies failed: {e}")
            return None
    
    async def _generate_gtts_fallback_enhanced(self, text: str) -> BytesIO | None:
        """Enhanced gTTS fallback with language detection"""
        try:
            from gtts import gTTS
            
            # Detect language for gTTS
            detected_lang = self._detect_language(text)
            gtts_lang = 'hi' if detected_lang == 'hi' else 'en'
            
            print(f"🔄 gTTS fallback using language: {gtts_lang}")
            
            # Use thread pool for blocking gTTS operation
            loop = asyncio.get_event_loop()
            audio_data = await loop.run_in_executor(
                self.executor, self._generate_gtts_with_lang, text, gtts_lang
            )
            return audio_data
            
        except Exception as e:
            print(f"🔴 Enhanced gTTS fallback error: {e}")
            return None
    
    def _generate_gtts_with_lang(self, text: str, lang: str) -> BytesIO:
        """Generate enhanced gTTS with proper language detection"""
        from gtts import gTTS
        
        try:
            tts = gTTS(text=text, lang=lang, slow=False)
            audio_buffer = BytesIO()
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)
            audio_buffer.name = f"gtts_fallback_{lang}.mp3"
            print(f"✅ gTTS fallback generated successfully ({lang})")
            return audio_buffer
        except Exception as e:
            print(f"🔴 gTTS generation error: {e}")
            raise e
    
    async def text_to_speech(self, text: str, lang: str = 'hi') -> BytesIO | None:
        """Legacy method for backward compatibility"""
        return await self.text_to_speech_with_voice(text, 'male1')
    
    def get_available_voices(self):
        """Get list of all 10 available voice types with detailed descriptions"""
        return {
            voice_type: {
                'display_name': config['name'],
                'description': config['description'],
                'language': 'Hindi' if config['lang'] == 'hi' else 'English (India)',
                'gender': 'Male' if 'male' in voice_type else 'Female',
                'voice_id': config['voice']
            }
            for voice_type, config in self.voice_mapping.items()
        }
    
    def get_supported_languages(self):
        """Get list of supported languages with auto-detection"""
        return {
            'auto': 'Auto-Detect (Recommended)',
            'hi': 'Hindi (हिंदी)',
            'en': 'English (India)',
            'mixed': 'Hindi-English Mixed'
        }
    
    def get_voice_statistics(self):
        """Get statistics about available voices"""
        stats = {
            'total_voices': len(self.voice_mapping),
            'male_voices': len([v for v in self.voice_mapping.keys() if 'male' in v]),
            'female_voices': len([v for v in self.voice_mapping.keys() if 'female' in v]),
            'hindi_voices': len([v for v in self.voice_mapping.values() if v['lang'] == 'hi']),
            'english_voices': len([v for v in self.voice_mapping.values() if v['lang'] == 'en']),
            'languages_supported': list(set([v['lang'] for v in self.voice_mapping.values()])),
            'voice_engines': ['Edge TTS (Primary)', 'gTTS (Fallback)']
        }
        return stats