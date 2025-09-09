import os
import asyncio
import tempfile
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import edge_tts

class TTSService:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # High-quality voice mapping with proper male/female voices
        self.voice_mapping = {
            'male1': {'voice': 'hi-IN-MadhurNeural', 'name': 'Deep Male Voice'},          # Hindi Male - Deep
            'male2': {'voice': 'en-US-RyanNeural', 'name': 'Professional Male Voice'},    # English Male - Professional  
            'male3': {'voice': 'hi-IN-MadhurNeural', 'name': 'Warm Male Voice'},          # Hindi Male - Warm
            'female1': {'voice': 'hi-IN-SwaraNeural', 'name': 'Sweet Female Voice'},      # Hindi Female - Sweet
            'female2': {'voice': 'en-US-JennyNeural', 'name': 'Clear Female Voice'},      # English Female - Clear
            'female3': {'voice': 'hi-IN-SwaraNeural', 'name': 'Soft Female Voice'},       # Hindi Female - Soft
        }
    
    async def text_to_speech_with_voice(self, text: str, voice_type: str = 'male1') -> BytesIO | None:
        """Convert text to speech with specific voice type using Edge TTS"""
        try:
            # Get voice configuration
            voice_config = self.voice_mapping.get(voice_type, self.voice_mapping['male1'])
            voice_name = voice_config['voice']
            
            # Run Edge TTS
            audio_data = await self._generate_edge_tts(text, voice_name)
            return audio_data
            
        except Exception as e:
            print(f"Edge TTS Error: {e}")
            # Fallback to old gTTS if Edge TTS fails
            return await self._fallback_gtts(text)
    
    async def _generate_edge_tts(self, text: str, voice: str) -> BytesIO:
        """Generate TTS using Edge TTS with proper voice"""
        try:
            # Create communicate instance with specified voice
            communicate = edge_tts.Communicate(text, voice)
            
            # Generate audio data
            audio_data = BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.write(chunk["data"])
            
            audio_data.seek(0)
            audio_data.name = "tts_audio.mp3"
            return audio_data
            
        except Exception as e:
            print(f"Edge TTS generation error: {e}")
            raise e
    
    async def _fallback_gtts(self, text: str) -> BytesIO | None:
        """Fallback to gTTS if Edge TTS fails"""
        try:
            from gtts import gTTS
            
            # Use thread pool for blocking gTTS operation
            loop = asyncio.get_event_loop()
            audio_data = await loop.run_in_executor(
                self.executor, self._generate_gtts_fallback, text
            )
            return audio_data
            
        except Exception as e:
            print(f"Fallback gTTS error: {e}")
            return None
    
    def _generate_gtts_fallback(self, text: str) -> BytesIO:
        """Generate fallback TTS using gTTS"""
        from gtts import gTTS
        
        tts = gTTS(text=text, lang='hi', slow=False)
        audio_buffer = BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        audio_buffer.name = "tts_audio.mp3"
        return audio_buffer
    
    async def text_to_speech(self, text: str, lang: str = 'hi') -> BytesIO | None:
        """Legacy method for backward compatibility"""
        return await self.text_to_speech_with_voice(text, 'male1')
    
    def get_available_voices(self):
        """Get list of available voice types"""
        return {
            'male1': 'Deep Male Voice (Hindi)',
            'male2': 'Professional Male Voice (English)', 
            'male3': 'Warm Male Voice (Hindi)',
            'female1': 'Sweet Female Voice (Hindi)',
            'female2': 'Clear Female Voice (English)',
            'female3': 'Soft Female Voice (Hindi)'
        }
    
    def get_supported_languages(self):
        """Get list of supported languages"""
        return {
            'hi': 'Hindi',
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
        }