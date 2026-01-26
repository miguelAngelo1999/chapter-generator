#!/usr/bin/env python3

# CRITICAL: Prevent infinite process spawning in Windows executables
import multiprocessing
if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass

import sys
import re
import json
import os
import platform
import tempfile
import subprocess
import math
import logging
import glob
from datetime import datetime

# Setup logging to file
if getattr(sys, 'frozen', False):
    log_dir = os.path.dirname(sys.executable)
else:
    log_dir = os.path.dirname(__file__)

log_file = os.path.join(log_dir, f'chapter_generator_{datetime.now().strftime("%Y%m%d")}.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Silence Flask's werkzeug logger
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('requests').setLevel(logging.ERROR)

# Delay heavy imports until needed
requests = None
Flask = None
render_template_string = None
request = None
jsonify = None
webview = None

def lazy_import_web():
    """Import web modules only when needed"""
    global requests, Flask, render_template_string, request, jsonify, webview, send_file
    if Flask is None:
        print("Loading web modules...")
        import requests as _requests
        from flask import Flask, request, jsonify, render_template_string, send_file
        import webview as _webview
        requests = _requests
        Flask = Flask
        render_template_string = render_template_string
        request = request
        jsonify = jsonify
        send_file = send_file
        webview = _webview

# Lazy-loaded Whisper backends
WHISPER_BACKEND = "purfview"

def load_whisper_backends():
    """Check for Purfview Whisper"""
    global WHISPER_BACKEND
    print("Using Purfview Whisper (standalone binary)")

logger.info(f"Platform: {platform.system()}")
logger.info("Using Purfview Whisper for transcription")

# Set HuggingFace mirror for corporate networks
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
os.environ['HUGGINGFACE_HUB_CACHE'] = os.path.expanduser('~/.cache/huggingface')
# Enable online downloads on macOS, keep offline on other platforms
if platform.system() == "Darwin":
    os.environ['HF_HUB_OFFLINE'] = '0'  # Enable online downloads on macOS
else:
    os.environ['HF_HUB_OFFLINE'] = '1'
# Disable proxy for local connections
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

# --- Configuration ---
APP_VERSION = "1.0.0"
DEBUG = '--debug' in sys.argv 
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_SWAMA_BASE_URL = "http://0.0.0.0:28100"

# Parse command line arguments for endpoint
for arg in sys.argv:
    if arg.startswith('--endpoint='):
        DEFAULT_OLLAMA_BASE_URL = arg.split('=', 1)[1]
        logger.info(f"Using custom endpoint from command line: {DEFAULT_OLLAMA_BASE_URL}")
        break

PREFERRED_MODEL = "llama3.2:1b"
WHISPER_MODEL_SIZE = "medium"  # Options: tiny, base, small, medium, large-v2, large-v3 (multilingual models)
SUPPORTED_AUDIO_FORMATS = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.wma'}
SUPPORTED_VIDEO_FORMATS = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v'}

# Intermediate-window boundary refinement config
DEFAULT_WINDOW_SIZE = 8  # Number of SRT blocks in intermediate window (4 from each chapter)
MIN_WINDOW_SIZE = 6      # Minimum window size when expanding for low contrast
MAX_WINDOW_SIZE = 12     # Maximum window size when expanding for low contrast
SIMILARITY_THRESHOLD = 0.3  # Below this threshold, expand window for better contrast
CONTRAST_EXPANSION_FACTOR = 1.5  # How much to expand window when contrast is low

# --- HTML Template ---
def load_html_template():
    """Load HTML template from separate file"""
    # Handle both script and executable modes
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller executable
        base_path = sys._MEIPASS
        template_path = os.path.join(base_path, 'templates', 'index.html')
    else:
        # Running as script
        base_path = os.path.dirname(__file__)
        template_path = os.path.join(base_path, 'templates', 'index.html')
    
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        # Fallback to minimal template if file not found
        print(f"[ERROR] Template not found at: {template_path}")
        return f'''<!DOCTYPE html>
<html>
<head>
    <title>Chapter Generator</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; text-align: center; margin-bottom: 30px; }}
        .error {{ background: #ffebee; color: #c62828; padding: 20px; border-radius: 4px; border-left: 4px solid #c62828; }}
        .info {{ background: #e3f2fd; color: #1565c0; padding: 20px; border-radius: 4px; border-left: 4px solid #1565c0; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Chapter Generator</h1>
        <div class="error">
            <strong>Template Loading Error</strong><br>
            The HTML template could not be loaded from: {template_path}
        </div>
        <div class="info">
            <strong>Possible Solutions:</strong><br>
            1. Ensure the templates/index.html file exists<br>
            2. If running from executable, the template may not be properly bundled<br>
            3. Try running from source code instead
        </div>
    </div>
</body>
</html>'''

# --- Python Backend ---
class OllamaSession:
    def __init__(self, model, base_url):
        if not model: raise ValueError("Model name cannot be empty.")
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.is_swama = 'swama' in base_url.lower() or ':28100' in base_url
        self.is_osaurus = False
        
        # Detect if this is an Osaurus server
        try:
            import requests
            response = requests.get(f"{self.base_url}/", timeout=5)
            if "Osaurus Server" in response.text:
                self.is_osaurus = True
                print("Detected Osaurus Server")
        except:
            pass
    
    def ask(self, prompt):
        import requests
        
        if self.is_osaurus:
            # Try Osaurus API format (similar to OpenAI)
            url = f"{self.base_url}/v1/chat/completions"
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            }
        elif self.is_swama:
            url = f"{self.base_url}/v1/chat/completions"
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            }
        else:
            url = f"{self.base_url}/api/generate"
            payload = {"model": self.model, "prompt": prompt, "stream": False}
        
        try:
            session = requests.Session()
            session.trust_env = False  # Disable proxy
            if platform.system() != "Windows":
                session.verify = False
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            response = session.post(url, json=payload, timeout=180)
            response.raise_for_status()
            data = response.json()
            
            if self.is_osaurus or self.is_swama:
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                return data.get("response", "")
        except requests.exceptions.RequestException as e:
            service = "Osaurus" if self.is_osaurus else ("Swama" if self.is_swama else "Ollama")
            error_msg = f"[Error calling {service} API at {self.base_url}: {e}]"
            print(error_msg)
            
            # If this is a remote server and fails, suggest using localhost
            if "192.168" in self.base_url or "localhost" not in self.base_url:
                print("Tip: Make sure the remote server is accessible, or try using localhost:11434 with Ollama running locally")
            
            return error_msg
    def close(self): pass

def extract_audio_from_video(video_path, output_audio_path):
    """Extract audio from video file using ffmpeg"""
    process = None
    try:
        # Try different ffmpeg executable names based on platform
        ffmpeg_cmd = 'ffmpeg.exe' if platform.system() == 'Windows' else 'ffmpeg'
        cmd = [ffmpeg_cmd, '-i', video_path, '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', '-y', output_audio_path]
        if platform.system() == 'Windows':
            process = subprocess.run(cmd, check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            process = subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error extracting audio: {e}")
        return False
    except FileNotFoundError:
        # Try alternative ffmpeg command
        try:
            alt_cmd = 'ffmpeg' if platform.system() == 'Windows' else 'ffmpeg'
            cmd = [alt_cmd, '-i', video_path, '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', '-y', output_audio_path]
            if platform.system() == 'Windows':
                process = subprocess.run(cmd, check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                process = subprocess.run(cmd, check=True, capture_output=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("ffmpeg not found. Please install ffmpeg to process video files.")
            return False
    finally:
        # Clean up process handles if needed
        if process and hasattr(process, 'stdout') and process.stdout:
            try:
                process.stdout.close()
            except:
                pass

def get_models_path():
    """Get the models directory path for both script and exe modes"""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'models')
    else:
        return os.path.join(os.path.dirname(__file__), 'models')

def transcribe_audio_to_srt(audio_path, model_size="medium"):
    """Transcribe audio using Purfview Whisper"""
    load_whisper_backends()
    
    # Fix for PyInstaller - check _internal first, then exe directory
    if getattr(sys, 'frozen', False):
        # Try _internal first (where COLLECT puts bundled data)
        alt_paths = [
            os.path.join(sys._MEIPASS, "Purfview-Whisper-Faster"),
            os.path.join(os.path.dirname(sys.executable), "Purfview-Whisper-Faster"),
        ]
    else:
        # Running as script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        alt_paths = [os.path.join(current_dir, "Purfview-Whisper-Faster")]
    
    purfview_whisper_dir = None
    for path in alt_paths:
        logger.info(f"[DEBUG] Checking: {path}")
        if os.path.exists(path):
            purfview_whisper_dir = path
            logger.info(f"[DEBUG] Found Purfview at: {path}")
            break
    
    if not purfview_whisper_dir:
        logger.error(f"[ERROR] Purfview not found in any location")
        return None
    
    try:
        update_progress("Loading Purfview Whisper", 15)
        whisper_exe = os.path.join(purfview_whisper_dir, "faster-whisper-xxl.exe")
        if not os.path.exists(whisper_exe):
            print(f"[ERROR] Whisper executable not found: {whisper_exe}")
            return None
        
        cmd = [whisper_exe, audio_path, "--model", model_size, "--output_format", "srt", "--print_progress"]
        print(f"Running Purfview Whisper: {' '.join(cmd)}")
        
        import threading
        
        def read_output(process):
            for line in iter(process.stdout.readline, ''):
                if line:
                    logger.info(line.strip())
                    if '%' in line and any(char.isdigit() for char in line):
                        try:
                            match = re.search(r'(\d+)%', line)
                            if match:
                                whisper_progress = int(match.group(1))
                                # Map Purfview's 0-100% to our 15-50% range
                                mapped_progress = 15 + int((whisper_progress / 100) * 35)
                                update_progress(f"Transcribing audio: {whisper_progress}%", mapped_progress)
                        except:
                            pass
        
        creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' and not DEBUG else 0
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                 text=True, cwd=purfview_whisper_dir, 
                                 creationflags=creationflags, bufsize=1, universal_newlines=True)
        
        output_thread = threading.Thread(target=read_output, args=(process,))
        output_thread.daemon = True
        output_thread.start()
        
        returncode = process.wait()
        output_thread.join(timeout=1)
        
        try:
            process.stdout.close()
            process.terminate()
        except:
            pass
        
        if returncode == 0:
            base_name = os.path.splitext(os.path.basename(audio_path))[0]
            output_file = os.path.join(purfview_whisper_dir, base_name + ".srt")
            if os.path.exists(output_file):
                with open(output_file, 'r', encoding='utf-8') as f:
                    srt_content = f.read()
                os.unlink(output_file)
                update_progress("Transcription complete", 50)
                print("Successfully transcribed with Purfview Whisper")
                return srt_content
        else:
            print(f"Purfview Whisper failed with return code {returncode}")
    except Exception as e:
        print(f"Purfview Whisper failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("[ERROR] Transcription failed")
    return None

def process_media_file(file_path):
    """Process audio or video file and return SRT content"""
    file_ext = os.path.splitext(file_path)[1].lower()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            if file_ext in SUPPORTED_AUDIO_FORMATS:
                # Direct audio transcription
                update_progress("Transcribing audio", 10)
                result = transcribe_audio_to_srt(file_path, WHISPER_MODEL_SIZE)
                return result
            elif file_ext in SUPPORTED_VIDEO_FORMATS:
                # Extract audio from video first
                update_progress("Extracting audio from video", 5)
                temp_audio_path = os.path.join(temp_dir, "extracted_audio.wav")
                if extract_audio_from_video(file_path, temp_audio_path):
                    update_progress("Transcribing extracted audio", 10)
                    result = transcribe_audio_to_srt(temp_audio_path, WHISPER_MODEL_SIZE)
                    # Clean up temp audio file immediately
                    try:
                        os.unlink(temp_audio_path)
                    except:
                        pass
                    return result
                else:
                    return None
            else:
                return None
        except Exception as e:
            print(f"Error in process_media_file: {e}")
            return None
        finally:
            # Aggressive garbage collection after processing
            import gc
            gc.collect()
            # Force MLX memory cleanup if available
            try:
                import mlx.core as mx
                mx.metal.clear_cache()
            except:
                pass

def get_ollama_models(base_url):
    try:
        # Check if this is an Osaurus server first
        try:
            test_response = requests.get(f"{base_url.rstrip('/')}/", timeout=5)
            if "Osaurus Server" in test_response.text:
                # Use Osaurus API endpoint
                url = f"{base_url.rstrip('/')}/api/tags"
            else:
                # Use standard Ollama API endpoint
                url = f"{base_url.rstrip('/')}/api/tags"
        except:
            # Fallback to standard Ollama endpoint
            url = f"{base_url.rstrip('/')}/api/tags"
            
        session = requests.Session()
        session.trust_env = False  # Disable proxy
        if platform.system() != "Windows":
            session.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = session.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        all_models = [model['name'] for model in data.get('models', [])]
        text_models = [m for m in all_models if 'whisper' not in m.lower() and 'vision' not in m.lower()]
        return sorted(text_models)
    except requests.exceptions.RequestException as e: 
        print(f"Error fetching models from {base_url}: {e}")
        if "192.168" in base_url or "localhost" not in base_url:
            print("Tip: Make sure the remote server is accessible, or try using localhost:11434 with Ollama running locally")
        return []

def get_title_for_chunk(transcript_chunk, timestamp, ollama_session, custom_prompt=None):
    if custom_prompt:
        prompt = f"{custom_prompt}\n\nTranscript: {transcript_chunk}\n\nTimestamp: {timestamp}"
    else:
        prompt = (
            "You are an expert in summarizing video content with a devout, manly Catholic perspective. "
            "Generate a concise, single-line chapter title (maximum 50 characters) for the following transcript chunk. "
            "Do not include any introductory phrases like 'Title:'. Respond ONLY with the title itself.\n\n"
            f"Transcript: {transcript_chunk}\n\nTimestamp: {timestamp}"
        )
    try:
        title = ollama_session.ask(prompt).strip()
        
        # Check if response is an error message
        if title.startswith('[Error') or 'Error' in title[:20]:
            print(f"Ollama API error: {title}")
            return "[Connection Error]"
        
        # Remove thinking tags and common prefixes
        title = re.sub(r'<think>.*?</think>', '', title, flags=re.DOTALL | re.IGNORECASE)
        title = re.sub(r'^(Title:|Here is a title:|Chapter Title:)\s*', '', title, flags=re.IGNORECASE).strip('"\'')
        title = title.strip()
        # If title is still empty or just thinking remnants, use fallback
        if not title or title.startswith('Okay,') or len(title) < 3:
            title = "Chapter"
        if len(title) > 50:
            shorten_prompt = (
                f"Shorten this title to 50 characters or less. Maintain the original tone. "
                f"Respond ONLY with the shortened title.\n\nOriginal Title: {title}"
            )
            title = ollama_session.ask(shorten_prompt).strip().strip('"\'')
        if len(title) > 50: title = title[:50].rsplit(' ', 1)[0]
        return title.strip().rstrip('.,:;-—') or "[Title Generation Failed]"
    except Exception as e:
        print(f"Error during title generation: {e}")
        return "[Error generating title]"

# Simple debug file writing for PyInstaller
def write_debug(message):
    """Write debug message to log file"""
    logger.info(message)

# Test debug writing immediately
try:
    write_debug("=== APPLICATION STARTED ===")
    write_debug(f"Python version: {sys.version}")
    write_debug(f"Executable: {sys.executable}")
    write_debug(f"Current directory: {os.getcwd()}")
except Exception as e:
    logger.error(f"Failed to write initial debug info: {e}")

# Global progress tracking
progress_data = {"step": "", "progress": 0}

def update_progress(step, progress):
    global progress_data
    progress_data = {"step": step, "progress": progress}
    logger.info(f"Progress: {step} - {progress}%")
    sys.stdout.flush()

def cleanup_old_files(directory, keep_count=5):
    """Remove old uploaded and transcribed files, keeping only the most recent ones"""
    try:
        import glob
        from datetime import datetime
        
        # Find all uploaded media files and SRT files
        patterns = ['*.mp3', '*.mp4', '*.wav', '*.m4a', '*.avi', '*.mov', '*.mkv', '*_transcribed*.srt']
        files_to_check = []
        
        for pattern in patterns:
            files_to_check.extend(glob.glob(os.path.join(directory, pattern)))
        
        if len(files_to_check) <= keep_count:
            return  # Nothing to clean
        
        # Sort by modification time (oldest first)
        files_with_time = [(f, os.path.getmtime(f)) for f in files_to_check]
        files_with_time.sort(key=lambda x: x[1])
        
        # Remove oldest files, keeping only keep_count most recent
        files_to_remove = files_with_time[:-keep_count]
        
        for file_path, _ in files_to_remove:
            try:
                os.unlink(file_path)
                write_debug(f"Cleaned up old file: {os.path.basename(file_path)}")
            except Exception as e:
                write_debug(f"Failed to remove {file_path}: {e}")
    except Exception as e:
        write_debug(f"Cleanup error: {e}")

def get_fallback_chapters_from_srt(file_path, num_chapters):
    """Generate chapters using mathematical division without LLM"""
    print(f"\n=== FALLBACK CHAPTER GENERATION ===")
    print(f"Using mathematical division (no LLM)")
    print(f"Input file: {file_path}")
    print(f"Requested chapters: {num_chapters}")
    print(f"File exists: {os.path.exists(file_path)}")
    
    if os.path.exists(file_path):
        print(f"File size: {os.path.getsize(file_path)} bytes")
    
    transcript_blocks = []
    
    # Try pysrt first
    try:
        print("[DEBUG] Trying pysrt parsing...")
        import pysrt
        subs = pysrt.open(file_path, encoding='utf-8')
        print(f"[DEBUG] pysrt loaded {len(subs)} subtitles")
        
        for i, sub in enumerate(subs):
            timestamp = f"{sub.start.hours:02d}:{sub.start.minutes:02d}:{sub.start.seconds:02d},{sub.start.milliseconds:03d}"
            text = re.sub(r'<[^>]+>', '', sub.text)
            text = re.sub(r'\s+', ' ', text).strip()
            transcript_blocks.append({"timestamp": timestamp, "text": text})
            
            if i < 3:  # Debug first few entries
                print(f"[DEBUG] pysrt {i+1}: {timestamp} - {text[:50]}...")
                
    except Exception as e:
        print(f"[DEBUG] pysrt failed: {e}")
        print("[DEBUG] Trying regex fallback...")
        
        # Fallback to regex parsing
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            pattern = re.compile(r'\d+\n(\d{2}:\d{2}:\d{2},\d{3}) --> \d{2}:\d{2}:\d{2},\d{3}\n(.*?)(?=\n\n|\n\d|\Z)', re.DOTALL)
            matches = pattern.findall(content)
            print(f"[DEBUG] regex found {len(matches)} matches")
            
            for i, match in enumerate(matches):
                timestamp = match[0]
                text = match[1].replace('\n', ' ')
                text = re.sub(r'\s+', ' ', text).strip()
                transcript_blocks.append({"timestamp": timestamp, "text": text})
                
                if i < 3:  # Debug first few entries
                    print(f"[DEBUG] regex {i+1}: {timestamp} - {text[:50]}...")
                    
        except Exception as e2:
            print(f"[DEBUG] regex also failed: {e2}")
            return []
    
    print(f"[DEBUG] Total transcript blocks created: {len(transcript_blocks)}")
    
    if not transcript_blocks:
        print("[ERROR] No transcript blocks found in fallback!")
        return []
    
    # Use mathematical division to create chapters
    total_blocks = len(transcript_blocks)
    blocks_per_chapter = max(1, total_blocks // num_chapters)
    print(f"[DEBUG] Total blocks: {total_blocks}, blocks per chapter: {blocks_per_chapter}")
    
    chapters = []
    for i in range(num_chapters):
        start_idx = i * blocks_per_chapter
        if start_idx >= total_blocks:
            break
            
        end_idx = min((i + 1) * blocks_per_chapter, total_blocks)
        
        # Get content for this chapter
        chapter_blocks = transcript_blocks[start_idx:end_idx]
        if not chapter_blocks:
            continue
            
        # Create title from first few words
        first_text = chapter_blocks[0]["text"][:50]
        title = first_text if len(first_text) < 50 else first_text + "..."
        
        # Format timestamp
        timestamp_str = chapter_blocks[0]["timestamp"]
        hms = timestamp_str.split(',')[0]
        parts = hms.split(':')
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            total_minutes = (h * 60) + m
            formatted_timestamp = f"{total_minutes}:{s:02d}"
        else:
            formatted_timestamp = "0:00"
        
        chapters.append((formatted_timestamp, title))
        print(f"[DEBUG] Chapter {i+1}: {formatted_timestamp} - {title}")
    
    # Don't set progress to 100 here - let the route handler do it
    print(f"[DEBUG] Generated {len(chapters)} chapters using fallback method")
    return chapters

def process_srt(file_path, num_chapters, model, ollama_endpoint, custom_prompt=None):
    write_debug(f"\n=== SRT PROCESSING START ===")
    write_debug(f"File: {file_path}")
    write_debug(f"Chapters requested: {num_chapters}")
    write_debug(f"Model: {model}")
    write_debug(f"Endpoint: {ollama_endpoint}")
    
    print(f"\n=== SRT PROCESSING START ===")
    print(f"File: {file_path}")
    print(f"Chapters requested: {num_chapters}")
    print(f"Model: {model}")
    print(f"Endpoint: {ollama_endpoint}")
    
    update_progress("Initializing chapter generation", 60)
    
    # Test Ollama connection first with timeout
    try:
        print("[DEBUG] Testing Ollama connection...")
        ollama_session = OllamaSession(model=model, base_url=ollama_endpoint)
        
        # Quick test with timeout using threading
        import threading
        import time
        
        test_result = {"success": False, "error": None}
        
        def test_connection():
            try:
                print("[DEBUG] Sending test request to Ollama...")
                write_debug("[DEBUG] Sending test request to Ollama...")
                test_response = ollama_session.ask("test")
                print(f"[DEBUG] Ollama test response: {test_response[:100]}")
                write_debug(f"[DEBUG] Ollama test response: {test_response[:100]}")
                # Check if response contains error
                if test_response and not test_response.startswith('[Error'):
                    test_result["success"] = True
                else:
                    test_result["error"] = test_response
            except Exception as e:
                print(f"[DEBUG] Ollama test exception: {e}")
                write_debug(f"[DEBUG] Ollama test exception: {e}")
                test_result["error"] = str(e)
        
        # Start connection test in thread
        thread = threading.Thread(target=test_connection)
        thread.daemon = True
        thread.start()
        
        # Wait for up to 30 seconds (Ollama can be slow on first request)
        thread.join(timeout=30)
        
        if thread.is_alive():
            print("[ERROR] Ollama connection timeout (30s)")
            write_debug("[ERROR] Ollama connection timeout (30s)")
            print("[INFO] Falling back to mathematical chapter division")
            return get_fallback_chapters_from_srt(file_path, num_chapters)
        
        if test_result["success"]:
            print("[DEBUG] Ollama connection successful")
            write_debug("[DEBUG] Ollama connection successful")
        else:
            error_msg = test_result.get('error', 'Unknown error')
            print(f"[ERROR] Ollama connection failed: {error_msg}")
            write_debug(f"[ERROR] Ollama connection failed: {error_msg}")
            print("[INFO] Falling back to mathematical chapter division")
            return get_fallback_chapters_from_srt(file_path, num_chapters)
            
    except Exception as e:
        print(f"[ERROR] Failed to initialize Ollama: {e}")
        print("[INFO] Falling back to mathematical chapter division")
        return get_fallback_chapters_from_srt(file_path, num_chapters)
    
    # Add try-catch around the entire SRT processing
    try:
        print(f"[DEBUG] About to process SRT file: {file_path}")
        print(f"[DEBUG] File exists: {os.path.exists(file_path)}")
        if os.path.exists(file_path):
            print(f"[DEBUG] File size: {os.path.getsize(file_path)} bytes")
        
        try:
            import pysrt
            print("Loading SRT with pysrt...")
            # Load SRT file using pysrt library
            subs = pysrt.open(file_path, encoding='utf-8')
            print(f"Loaded {len(subs)} subtitle blocks")
            
            # Convert to transcript blocks format
            transcript_blocks = []
            for sub in subs:
                # Convert time to HH:MM:SS,mmm format
                timestamp = f"{sub.start.hours:02d}:{sub.start.minutes:02d}:{sub.start.seconds:02d},{sub.start.milliseconds:03d}"
                # Clean text (remove HTML tags, extra whitespace)
                text = re.sub(r'<[^>]+>', '', sub.text)  # Remove HTML tags
                text = re.sub(r'\s+', ' ', text).strip()  # Normalize whitespace
                transcript_blocks.append({"timestamp": timestamp, "text": text})
                
        except Exception as e:
            print(f"[ERROR] Failed to parse SRT with pysrt: {e}")
            print("Falling back to regex parsing...")
            # Fallback to regex parsing
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            pattern = re.compile(r'\d+\n(\d{2}:\d{2}:\d{2},\d{3}) --> \d{2}:\d{2}:\d{2},\d{3}\n(.*?)(?=\n\n|\n\d|\Z)', re.DOTALL)
            matches = pattern.findall(content)
            print(f"Regex parsing found {len(matches)} matches")
            transcript_blocks = [{"timestamp": match[0], "text": match[1].replace('\n', ' ')} for match in matches]
        
        if not transcript_blocks: 
            print("[ERROR] No transcript blocks found!")
            return []
        
        print(f"Total transcript blocks created: {len(transcript_blocks)}")
        print("Sample blocks:")
        for i, block in enumerate(transcript_blocks[:3]):
            print(f"  {i+1}: {block['timestamp']} - {block['text'][:50]}...")
        
        total_blocks = len(transcript_blocks)
        if num_chapters <= 0: 
            raise ValueError("Number of chapters must be > 0.")
        
        # Intelligent chapter generation with LLM-driven transitions
        chapters = []
        
        if num_chapters == 1:
            print("Single chapter mode - using all content")
            # Single chapter - use all content
            combined_text = " ".join([block["text"] for block in transcript_blocks])
            timestamp_str = transcript_blocks[0]["timestamp"]
            title = get_title_for_chunk(combined_text, timestamp_str, ollama_session, custom_prompt)
            hms = timestamp_str.split(',')[0]
            parts = hms.split(':')
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            total_minutes = (h * 60) + m
            formatted_timestamp = f"{total_minutes}:{s:02d}"
            chapters.append((formatted_timestamp, title))
        else:
            print("Multi-chapter mode - using LLM-driven analysis")
            # LLM-driven chapter generation with intelligent transitions
            chapters = generate_llm_driven_chapters(transcript_blocks, num_chapters, ollama_session, custom_prompt)
        
        # Don't set progress to 100 here - let the route handler do it
        print(f"\n=== SRT PROCESSING COMPLETE ===")
        print(f"Final chapters to return: {len(chapters)}")
        for i, (timestamp, title) in enumerate(chapters):
            print(f"  Final Chapter {i+1}: {timestamp} - {title}")
        print("="*40 + "\n")
        
        ollama_session.close()
        return chapters
        
    except Exception as e:
        print(f"[CRITICAL ERROR] SRT processing failed: {e}")
        import traceback
        traceback.print_exc()
        return []

def generate_llm_driven_chapters(transcript_blocks, num_chapters, ollama_session, custom_prompt):
    """Generate chapters where LLM decides transition points using chunk analysis"""
    total_blocks = len(transcript_blocks)
    chapters = []
    
    print(f"\n=== CHAPTER GENERATION START ===")
    print(f"Total transcript blocks: {total_blocks}")
    print(f"Requested chapters: {num_chapters}")
    
    # Step 1: Create initial mathematical chunks as baseline
    update_progress("Creating initial content chunks", 65)
    base_chunks = create_base_chunks(transcript_blocks, num_chapters)
    print(f"Created {len(base_chunks)} base chunks")
    
    # Step 2: Generate titles for each chunk
    chunk_titles = []
    for i, chunk in enumerate(base_chunks):
        progress = 70 + int((i / len(base_chunks)) * 20)
        update_progress(f"Analyzing chunk {i + 1} of {len(base_chunks)}", progress)
        
        combined_text = " ".join([block["text"] for block in chunk])
        timestamp_str = chunk[0]["timestamp"]
        print(f"\n--- Chunk {i+1} ---")
        print(f"Blocks in chunk: {len(chunk)}")
        print(f"Timestamp: {timestamp_str}")
        print(f"Text preview: {combined_text[:100]}...")
        
        title = get_title_for_chunk(combined_text, timestamp_str, ollama_session, custom_prompt)
        print(f"Generated title: '{title}'")
        chunk_titles.append((timestamp_str, title, chunk))
    
    # Step 3: LLM identifies optimal transition points between chunks
    update_progress("Identifying optimal transition points", 90)
    print(f"\n=== TRANSITION ANALYSIS ===")
    transition_points = get_llm_transition_analysis(chunk_titles, ollama_session, custom_prompt)
    print(f"Transition points (block indices): {transition_points}")
    
    # Step 4: Refine chapters based on LLM transition analysis
    print(f"\n=== REFINING CHAPTERS ===")
    chapters = refine_chapters_with_transitions(transcript_blocks, transition_points, ollama_session, custom_prompt)
    print(f"Final chapters count: {len(chapters)}")
    
    for i, (timestamp, title) in enumerate(chapters):
        print(f"Chapter {i+1}: {timestamp} - {title}")
    
    print(f"=== CHAPTER GENERATION COMPLETE ===\n")
    return chapters

def create_base_chunks(transcript_blocks, num_chapters):
    """Create initial chunks as baseline for LLM analysis"""
    total_blocks = len(transcript_blocks)
    base_chunk_size = total_blocks // num_chapters
    remainder = total_blocks % num_chapters
    
    chunks = []
    current_idx = 0
    
    for i in range(num_chapters):
        chunk_size = base_chunk_size + (1 if i < remainder else 0)
        chunk_end = current_idx + chunk_size
        
        # Add some overlap for context (20% from previous chunk if not first)
        if i > 0:
            overlap_size = max(1, chunk_size // 5)
            overlap_start = max(0, current_idx - overlap_size)
            chunk = transcript_blocks[overlap_start:chunk_end]
        else:
            chunk = transcript_blocks[current_idx:chunk_end]
        
        chunks.append(chunk)
        current_idx = chunk_end
    
    return chunks

def compute_semantic_similarity(transcript_blocks, center_idx, window_size):
    """Compute TF-IDF cosine similarity to find semantic dips around boundary"""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
    except ImportError:
        # Fallback to simple text similarity if sklearn not available
        return simple_text_similarity(transcript_blocks, center_idx, window_size)
    
    # Extract text in window around center_idx
    start_idx = max(0, center_idx - window_size // 2)
    end_idx = min(len(transcript_blocks), center_idx + window_size // 2 + 1)
    
    if end_idx - start_idx < 3:
        return 0.5  # Default similarity for very small windows
    
    texts = [block["text"] for block in transcript_blocks[start_idx:end_idx]]
    
    # Compute TF-IDF vectors
    vectorizer = TfidfVectorizer(stop_words='english', max_features=100)
    try:
        tfidf_matrix = vectorizer.fit_transform(texts)
        similarities = cosine_similarity(tfidf_matrix)
        
        # Find similarity dip around center
        center_local = center_idx - start_idx
        if center_local <= 0 or center_local >= len(similarities) - 1:
            return 0.5
        
        # Average similarity across the boundary
        left_sim = similarities[center_local-1, center_local]
        right_sim = similarities[center_local, center_local+1] if center_local + 1 < len(similarities) else left_sim
        
        return (left_sim + right_sim) / 2
    except:
        return 0.5  # Fallback on any error

def simple_text_similarity(transcript_blocks, center_idx, window_size):
    """Simple fallback similarity using word overlap"""
    start_idx = max(0, center_idx - window_size // 2)
    end_idx = min(len(transcript_blocks), center_idx + window_size // 2 + 1)
    
    if end_idx - start_idx < 3:
        return 0.5
    
    # Get texts before and after boundary
    center_local = center_idx - start_idx
    if center_local <= 0 or center_local >= end_idx - start_idx - 1:
        return 0.5
    
    left_text = transcript_blocks[start_idx + center_local - 1]["text"].lower()
    right_text = transcript_blocks[start_idx + center_local]["text"].lower()
    
    # Simple word overlap similarity
    left_words = set(left_text.split())
    right_words = set(right_text.split())
    
    if not left_words or not right_words:
        return 0.5
    
    intersection = left_words.intersection(right_words)
    union = left_words.union(right_words)
    
    return len(intersection) / len(union) if union else 0.5

def get_llm_transition_analysis(chunk_titles, ollama_session, custom_prompt):
    """Intermediate-window boundary refinement using small LLM prompts"""
    import re
    
    # Test if LLM is available by making a simple request with timeout
    try:
        import threading
        test_result = {"success": False}
        
        def test_llm():
            try:
                response = ollama_session.ask("Respond with only the number: 1").strip()
                if "1" in response:
                    test_result["success"] = True
            except:
                pass
        
        thread = threading.Thread(target=test_llm)
        thread.daemon = True
        thread.start()
        thread.join(timeout=10)
        
        if not test_result["success"]:
            print("[INFO] LLM timeout or unavailable, using fallback")
            return get_fallback_transition_indices(chunk_titles)
    except Exception:
        return get_fallback_transition_indices(chunk_titles)
    
    # Flatten transcript blocks from all chunks for global indexing
    all_blocks = []
    chunk_boundaries = [0]  # Starting index of each chunk in global blocks
    
    for i, (timestamp, title, chunk) in enumerate(chunk_titles):
        all_blocks.extend(chunk)
        chunk_boundaries.append(len(all_blocks))
    
    transition_indices = [0]  # First chapter always starts at block 0
    
    # Process each boundary (except the last one)
    for i in range(len(chunk_titles) - 1):
        update_progress(f"Analyzing transition {i+1} of {len(chunk_titles)-1}", 90 + int((i / (len(chunk_titles)-1)) * 8))
        
        former_chunk_end = chunk_boundaries[i + 1]  # End of former chunk
        latter_chunk_start = chunk_boundaries[i + 1]  # Start of latter chunk
        
        # Find optimal window center using semantic similarity
        window_center = find_optimal_boundary_center(
            all_blocks, former_chunk_end, latter_chunk_start
        )
        
        # Determine window size based on semantic contrast
        similarity = compute_semantic_similarity(
            all_blocks, window_center, DEFAULT_WINDOW_SIZE
        )
        
        window_size = DEFAULT_WINDOW_SIZE
        if similarity < SIMILARITY_THRESHOLD:
            # Expand window for better contrast when similarity is low
            window_size = min(
                int(DEFAULT_WINDOW_SIZE * CONTRAST_EXPANSION_FACTOR),
                MAX_WINDOW_SIZE
            )
        
        # Build intermediate window around the boundary
        window_start = max(0, window_center - window_size // 2)
        window_end = min(len(all_blocks), window_center + window_size // 2 + 1)
        
        # Get window text with chapter labels
        window_blocks = all_blocks[window_start:window_end]
        boundary_in_window = window_center - window_start
        
        # Create tiny prompt for LLM
        prompt = f"""Find the exact topic transition point in this text.

Former chapter topic: {chunk_titles[i][1]}
Latter chapter topic: {chunk_titles[i + 1][1]}

Text (blocks numbered 0-{len(window_blocks)-1}):
{format_window_text_with_indices(window_blocks)}

Where does the topic change from the former to the latter?
Return EXACTLY ONE INTEGER: the block index where the transition occurs.
The transition should be between blocks {boundary_in_window-2} and {boundary_in_window+2}.

Respond with ONLY the integer (0-{len(window_blocks)-1}):"""

        try:
            response = ollama_session.ask(prompt).strip()
            
            # Strict validation: extract integer only
            transition_idx = extract_integer_response(response, 0, len(window_blocks) - 1)
            
            # Convert local window index to global block index
            global_transition_idx = window_start + transition_idx
            
            # Ensure monotonic progression
            if global_transition_idx > transition_indices[-1]:
                transition_indices.append(global_transition_idx)
            else:
                # Fallback: use next block after last transition
                transition_indices.append(transition_indices[-1] + 1)
                
        except Exception:
            # Fallback: use semantic similarity minimum
            fallback_idx = find_semantic_minimum(all_blocks, window_center, window_size)
            transition_indices.append(max(fallback_idx, transition_indices[-1] + 1))
    
    return transition_indices

def get_fallback_transition_indices(chunk_titles):
    """Fallback to mathematical division when LLM is unavailable"""
    
    # Count total blocks across all chunks
    total_blocks = sum(len(chunk) for _, _, chunk in chunk_titles)
    requested_chapters = len(chunk_titles)
    
    if requested_chapters <= 0:
        return [0]
    
    # Mathematical division to ensure exactly requested number of chapters
    base_chunk_size = total_blocks // requested_chapters
    remainder = total_blocks % requested_chapters
    
    transition_indices = []
    current_idx = 0
    
    for i in range(requested_chapters):
        transition_indices.append(current_idx)
        chunk_size = base_chunk_size + (1 if i < remainder else 0)
        current_idx += chunk_size
    
    # Ensure we get exactly the requested number of chapters
    while len(transition_indices) > requested_chapters:
        transition_indices.pop()
    
    return transition_indices[:requested_chapters]

def find_optimal_boundary_center(all_blocks, former_end, latter_start):
    """Find the optimal center point for the window around the boundary"""
    # Search in a small range around the initial boundary
    search_range = 4
    start_search = max(former_end - search_range, 0)
    end_search = min(latter_start + search_range, len(all_blocks))
    
    best_center = latter_start
    min_similarity = float('inf')
    
    for candidate in range(start_search, end_search):
        similarity = compute_semantic_similarity(all_blocks, candidate, 6)
        if similarity < min_similarity:
            min_similarity = similarity
            best_center = candidate
    
    return best_center

def find_semantic_minimum(all_blocks, center, window_size):
    """Find the point of minimum semantic similarity in a window"""
    start_idx = max(0, center - window_size // 2)
    end_idx = min(len(all_blocks), center + window_size // 2 + 1)
    
    min_sim = float('inf')
    min_idx = center
    
    for i in range(start_idx + 1, end_idx - 1):
        sim = compute_semantic_similarity(all_blocks, i, 4)
        if sim < min_sim:
            min_sim = sim
            min_idx = i
    
    return min_idx

def format_window_text_with_indices(window_blocks):
    """Format window text with block indices for LLM analysis"""
    formatted_lines = []
    for i, block in enumerate(window_blocks):
        # Truncate very long blocks to keep prompt small
        text = block["text"][:100] + ("..." if len(block["text"]) > 100 else "")
        formatted_lines.append(f"[{i}] {text}")
    return "\n".join(formatted_lines)

def extract_integer_response(response, min_val, max_val):
    """Strictly validate and extract integer from LLM response"""
    import re
    
    # Remove all non-digit characters except minus sign
    cleaned = re.sub(r'[^\d-]', '', response)
    
    try:
        if cleaned:
            num = int(cleaned)
            # Clamp to valid range
            return max(min_val, min(max_val, num))
    except ValueError:
        pass
    
    # Fallback: try to find any number in the response
    numbers = re.findall(r'-?\d+', response)
    if numbers:
        try:
            num = int(numbers[0])
            return max(min_val, min(max_val, num))
        except ValueError:
            pass
    
    # Ultimate fallback: return middle of range
    return (min_val + max_val) // 2

def refine_chapters_with_transitions(transcript_blocks, transition_indices, ollama_session, custom_prompt):
    """Create final chapters based on LLM-identified transition indices"""
    chapters = []
    
    # Ensure first chapter starts at 0:00 (YouTube rule)
    if transition_indices and transition_indices[0] != 0:
        transition_indices[0] = 0
    
    # Ensure monotonic boundaries and avoid overlaps
    transition_indices = ensure_monotonic_boundaries(transition_indices, len(transcript_blocks))
    
    for i, start_idx in enumerate(transition_indices):
        # Determine end point (next transition or end of content)
        if i + 1 < len(transition_indices):
            end_idx = transition_indices[i + 1]
        else:
            end_idx = len(transcript_blocks)
        
        # Ensure we have content for this chapter
        if start_idx >= end_idx:
            continue
        
        # Create chapter from blocks
        chapter_blocks = transcript_blocks[start_idx:end_idx]
        if not chapter_blocks:
            continue
        
        combined_text = " ".join([block["text"] for block in chapter_blocks])
        timestamp_str = chapter_blocks[0]["timestamp"]
        
        # Generate title for this chapter
        title = get_title_for_chunk(combined_text, timestamp_str, ollama_session, custom_prompt)
        
        # Format timestamp as MM:SS (YouTube format)
        hms = timestamp_str.split(',')[0]  # Remove milliseconds
        parts = hms.split(':')
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            total_minutes = (h * 60) + m
            formatted_timestamp = f"{total_minutes}:{s:02d}"
        else:
            # Fallback formatting
            formatted_timestamp = "0:00"
        
        chapters.append((formatted_timestamp, title))
    
    return chapters

def ensure_monotonic_boundaries(transition_indices, total_blocks):
    """Ensure monotonic progression and avoid empty/overlapping chapters"""
    if not transition_indices:
        return [0]
    
    # Start with first boundary
    cleaned = [transition_indices[0]]
    
    for i in range(1, len(transition_indices)):
        current = transition_indices[i]
        previous = cleaned[-1]
        
        # Ensure current is after previous
        if current <= previous:
            # Force minimum gap of 1 block to avoid empty chapters
            current = previous + 1
        
        # Ensure we don't exceed total blocks
        if current >= total_blocks:
            break
        
        cleaned.append(current)
    
    # Ensure we have at least one transition point
    if not cleaned:
        cleaned = [0]
    
    return cleaned

def get_fallback_transition_points(transcript_blocks, num_chapters):
    """Fallback mathematical division if LLM fails"""
    total_blocks = len(transcript_blocks)
    base_chunk_size = total_blocks // num_chapters
    remainder = total_blocks % num_chapters
    
    transition_points = []
    current_idx = 0
    
    for i in range(num_chapters):
        transition_points.append(current_idx)
        chunk_size = base_chunk_size + (1 if i < remainder else 0)
        current_idx += chunk_size
    
    return transition_points[:num_chapters]

def generate_intelligent_chapters(transcript_blocks, num_chapters, ollama_session, custom_prompt):
    """Generate chapters with intelligent transitions between topics"""
    total_blocks = len(transcript_blocks)
    chapters = []
    
    # Calculate base chunk size and transition points
    base_chunk_size = total_blocks // num_chapters
    remainder = total_blocks % num_chapters
    
    current_idx = 0
    
    for chapter_idx in range(num_chapters):
        # Calculate chunk boundaries
        chunk_start = current_idx
        
        # Distribute remainder blocks across early chapters
        chunk_size = base_chunk_size + (1 if chapter_idx < remainder else 0)
        chunk_end = current_idx + chunk_size
        
        # If not the first chapter, start with transition blocks
        if chapter_idx > 0:
            # Get transition blocks from previous chapter end
            transition_blocks = max(1, chunk_size // 4)  # 25% for transition
            transition_start = current_idx - transition_blocks
            transition_end = current_idx + (chunk_size - transition_blocks)
            
            # Chapter includes transition + new content
            chapter_chunk = transcript_blocks[transition_start:transition_end]
            timestamp_str = transcript_blocks[transition_start]["timestamp"]  # Use transition start time
        else:
            # First chapter - no transition needed
            chapter_chunk = transcript_blocks[chunk_start:chunk_end]
            timestamp_str = chapter_chunk[0]["timestamp"]
        
        if chapter_chunk:
            combined_text = " ".join([block["text"] for block in chapter_chunk])
            
            progress = 60 + int((chapter_idx / num_chapters) * 40)
            update_progress(f"Generating chapter {chapter_idx + 1} of {num_chapters}", progress)
            
            title = get_title_for_chunk(combined_text, timestamp_str, ollama_session, custom_prompt)
            hms = timestamp_str.split(',')[0]
            parts = hms.split(':')
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            total_minutes = (h * 60) + m
            formatted_timestamp = f"{total_minutes}:{s:02d}"
            chapters.append((formatted_timestamp, title))
        
        # Update current_idx for next chapter
        if chapter_idx < num_chapters - 1:
            # Leave transition blocks for next chapter
            transition_blocks = max(1, chunk_size // 4)
            current_idx = chunk_end - transition_blocks
        else:
            current_idx = chunk_end
    
    return chapters

# Initialize Flask app with lazy imports
try:
    lazy_import_web()
    app = Flask(__name__)
    
    @app.route('/')
    def index(): 
        html = load_html_template()
        # Inject default endpoint into HTML
        html = html.replace('{{ ENDPOINT }}', DEFAULT_OLLAMA_BASE_URL)
        return html
    
    @app.route('/progress')
    def get_progress(): return jsonify(progress_data)
    
    @app.route('/check_updates', methods=['GET'])
    def check_updates_route():
        from updater import check_for_updates
        update_info = check_for_updates(APP_VERSION)
        return jsonify(update_info)
    
    @app.route('/download_update', methods=['POST'])
    def download_update_route():
        from updater import download_and_run_installer
        import time
        data = request.get_json()
        download_url = data.get('download_url')
        if not download_url:
            return jsonify({"success": False, "error": "Download URL not provided."}), 400
        
        result = download_and_run_installer(download_url)
        
        if result.get("success"):
            def shutdown_app():
                time.sleep(1)
                os._exit(0)
            threading.Thread(target=shutdown_app).start()
        
        return jsonify(result)
    
    @app.route('/api/models', methods=['GET'])
    def api_get_models(): 
        endpoint = request.args.get('endpoint', DEFAULT_OLLAMA_BASE_URL)
        if not endpoint:
            endpoint = DEFAULT_OLLAMA_BASE_URL
        print(f"Fetching models from: {endpoint}")
        models = get_ollama_models(endpoint)
        print(f"Found models: {models}")
        return jsonify(models)
    
    @app.route('/save_srt_local/<filename>')
    def save_srt_local(filename):
        """Save SRT file directly to application directory"""
        try:
            import datetime
            
            # Get the current directory (works in both script and exe mode)
            if getattr(sys, 'frozen', False):
                # Running in PyInstaller bundle
                search_dir = os.path.dirname(sys.executable)
            else:
                # Running in normal Python
                search_dir = os.path.dirname(__file__)
            
            # Look for the exact transcribed SRT file
            expected_filename = f"{filename}_transcribed.srt"
            srt_path = os.path.join(search_dir, expected_filename)
            
            write_debug(f"Looking for SRT file to save locally: {srt_path}")
            
            if os.path.exists(srt_path):
                # Create a timestamped copy in application directory
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                local_filename = f"{filename}_transcribed_{timestamp}.srt"
                local_path = os.path.join(search_dir, local_filename)
                
                # Copy file
                import shutil
                shutil.copy2(srt_path, local_path)
                
                write_debug(f"SRT file saved locally: {local_path}")
                
                return jsonify({
                    "success": True,
                    "message": f"SRT file saved locally as: {local_filename}",
                    "local_path": local_path
                })
            else:
                # Fallback to glob search
                srt_pattern = os.path.join(search_dir, f'*{filename}*.srt')
                srt_files = glob.glob(srt_pattern)
                write_debug(f"Fallback search pattern: {srt_pattern}")
                
                if srt_files:
                    srt_path = srt_files[0]
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    local_filename = f"{filename}_transcribed_{timestamp}.srt"
                    local_path = os.path.join(search_dir, local_filename)
                    
                    import shutil
                    shutil.copy2(srt_path, local_path)
                    
                    write_debug(f"SRT file saved locally: {local_path}")
                    
                    return jsonify({
                        "success": True,
                        "message": f"SRT file saved locally as: {local_filename}",
                        "local_path": local_path
                    })
                else:
                    write_debug(f"SRT file not found for: {filename}")
                    return jsonify({"error": "SRT file not found"}), 404
                    
        except Exception as e:
            write_debug(f"Error saving SRT locally: {e}")
            return jsonify({"error": "Failed to save SRT file locally"}), 500
    
    @app.route('/download_srt/<filename>')
    def download_srt(filename):
        try:
            # Look for SRT file in current directory first
            if getattr(sys, 'frozen', False):
                # Running in PyInstaller bundle
                search_dir = os.path.dirname(sys.executable)
            else:
                # Running in normal Python
                search_dir = os.path.dirname(__file__)
            
            # Look for the exact transcribed SRT file
            expected_filename = f"{filename}_transcribed.srt"
            srt_path = os.path.join(search_dir, expected_filename)
            
            write_debug(f"Looking for SRT file: {srt_path}")
            
            if os.path.exists(srt_path):
                write_debug(f"Found SRT file: {srt_path}")
                return send_file(srt_path, as_attachment=True, download_name=expected_filename)
            else:
                # Fallback to glob search
                srt_pattern = os.path.join(search_dir, f'*{filename}*.srt')
                srt_files = glob.glob(srt_pattern)
                write_debug(f"Fallback search pattern: {srt_pattern}")
                write_debug(f"Found SRT files: {srt_files}")
                
                if srt_files:
                    srt_path = srt_files[0]
                    write_debug(f"Downloading SRT: {srt_path}")
                    return send_file(srt_path, as_attachment=True, download_name=os.path.basename(srt_path))
                else:
                    write_debug(f"SRT file not found for: {filename}")
                    return jsonify({"error": "SRT file not found"}), 404
        except Exception as e:
            write_debug(f"Error downloading SRT: {e}")
            return jsonify({"error": "Failed to download SRT file"}), 500

except Exception as e:
    # Critical Flask startup error
    try:
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
        error_file = os.path.join(desktop, 'flask_startup_error.txt')
        with open(error_file, 'w', encoding='utf-8') as f:
            f.write(f"FLASK STARTUP ERROR: {e}\n")
            f.write(f"Python version: {sys.version}\n")
            f.write(f"Executable: {sys.executable}\n")
    except:
        pass
    sys.exit(1)

@app.route('/retry_chapters', methods=['POST'])
def retry_chapters_route():
    """Regenerate chapters from existing SRT without re-transcribing"""
    try:
        srt_path_base = request.form.get('srt_path')
        num_chapters = int(request.form.get('num_chapters', 10))
        model = request.form.get('model')
        endpoint = request.form.get('ollama_endpoint', DEFAULT_OLLAMA_BASE_URL)
        custom_prompt = request.form.get('custom_prompt')
        
        if not srt_path_base or not model:
            return jsonify({"error": "Missing required parameters"}), 400
        
        # Find the SRT file
        if getattr(sys, 'frozen', False):
            search_dir = os.path.dirname(sys.executable)
        else:
            search_dir = os.path.dirname(__file__)
        
        srt_filename = f"{srt_path_base}_transcribed.srt"
        srt_path = os.path.join(search_dir, srt_filename)
        
        if not os.path.exists(srt_path):
            return jsonify({"error": "SRT file not found. Please re-transcribe the media file."}), 404
        
        update_progress("Processing SRT file", 50)
        results = process_srt(srt_path, num_chapters, model, endpoint, custom_prompt)
        
        if not results:
            return jsonify({"error": "Failed to generate chapters"}), 500
        
        output = [f"{timestamp} {title}" for timestamp, title in results]
        return jsonify({"chapters": output})
        
    except Exception as e:
        print(f"[FLASK] Retry chapters error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/process', methods=['POST'])
def process_file_route():
    write_debug("=== FLASK PROCESS ROUTE START ===")
    try:
        if 'file' not in request.files: 
            write_debug("ERROR: No file part in request")
            return jsonify({"error": "No file part"}), 400
        file = request.files['file']
        if file.filename == '': 
            write_debug("ERROR: No selected file")
            return jsonify({"error": "No selected file"}), 400
        num_chapters = int(request.form.get('num_chapters', 10))
        model = request.form.get('model')
        endpoint = request.form.get('ollama_endpoint', DEFAULT_OLLAMA_BASE_URL)
        custom_prompt = request.form.get('custom_prompt')
        if not model: 
            write_debug("ERROR: No model selected")
            return jsonify({"error": "No model selected"}), 400
        
        write_debug(f"Processing file: {file.filename}")
        write_debug(f"Chapters: {num_chapters}, Model: {model}, Endpoint: {endpoint}")
        
        # Save to exe directory instead of temp
        if getattr(sys, 'frozen', False):
            upload_dir = os.path.dirname(sys.executable)
        else:
            upload_dir = os.path.dirname(__file__)
        
        # Clean old files (keep only last 5 processed files)
        cleanup_old_files(upload_dir)
        
        upload_path = os.path.join(upload_dir, file.filename)
        file.save(upload_path)
        write_debug(f"File saved to: {upload_path}")
        
        try:
            # Check if SRT-only processing requested
            srt_only = request.form.get('srt_only') == 'true'
            write_debug(f"SRT-only mode: {srt_only}")
            
            # Check file type and process accordingly
            file_ext = os.path.splitext(file.filename)[1].lower()
            write_debug(f"File extension: {file_ext}")
            
            update_progress("Starting processing", 0)
            
            if srt_only and (file_ext in SUPPORTED_AUDIO_FORMATS or file_ext in SUPPORTED_VIDEO_FORMATS):
                # SRT-only transcription for video/audio files
                update_progress("Extracting audio from video", 5)
                srt_content = process_media_file(upload_path)
                if srt_content is None:
                    return jsonify({"error": "Failed to transcribe media file. All whisper backends failed. Please check your network connection and try again."}), 500
                
                update_progress("Transcription complete", 100)
                
                # Save transcribed SRT to permanent file for download
                base_filename = os.path.splitext(os.path.basename(file.filename))[0]
                srt_filename = f"{base_filename}_transcribed.srt"
                
                # Save to exe directory
                if getattr(sys, 'frozen', False):
                    srt_path = os.path.join(os.path.dirname(sys.executable), srt_filename)
                else:
                    srt_path = os.path.join(os.path.dirname(__file__), srt_filename)
                
                with open(srt_path, 'w', encoding='utf-8') as f:
                    f.write(srt_content)
                
                print(f"[FLASK] SRT-only transcription completed: {srt_filename}")
                response = jsonify({
                    "srt_download_url": f"/download_srt/{base_filename}",
                    "srt_filename": srt_filename
                })
                print(f"[FLASK] SRT-only response created: {response}")
                return response
            
            if (file_ext == '.srt'):
                # Process SRT file directly
                update_progress("Processing SRT file", 50)
                results = process_srt(upload_path, num_chapters, model, endpoint, custom_prompt)
                print(f"[FLASK] process_srt returned {len(results)} results")
                
                if not results:
                    return jsonify({"error": "Failed to generate chapters"}), 500
                
                # Create output BEFORE setting progress to 100%
                output = [f"{timestamp} {title}" for timestamp, title in results]
                print(f"[FLASK] Returning {len(output)} chapters for SRT file")
                
                # Set progress to 100 AFTER creating output
                update_progress("Processing complete", 100)
                
                return jsonify({"chapters": output})
            elif file_ext in SUPPORTED_AUDIO_FORMATS or file_ext in SUPPORTED_VIDEO_FORMATS:
                # SIMPLIFIED: Use existing SRT-only pipeline first, then SRT-to-chapters pipeline
                try:
                    write_debug(f"Step 1: Transcribing {file.filename} to SRT")
                    print(f"[FLASK] Step 1: Transcribing {file.filename} to SRT")
                    
                    # Step 1: Use existing SRT-only transcription pipeline
                    update_progress("Extracting audio from video", 5)
                    srt_content = process_media_file(upload_path)
                    if srt_content is None:
                        write_debug("ERROR: Transcription failed")
                        return jsonify({"error": "Failed to transcribe media file. All whisper backends failed. Please upload an SRT file instead, or check your network connection and try again."}), 500
                    
                    update_progress("Transcription complete", 50)
                    write_debug(f"Step 1 complete: SRT content length: {len(srt_content)}")
                    
                    # Step 2: Save SRT file (reuse SRT-only logic)
                    base_filename = os.path.splitext(os.path.basename(file.filename))[0]
                    srt_filename = f"{base_filename}_transcribed.srt"
                    
                    # Save to current directory
                    if getattr(sys, 'frozen', False):
                        srt_path = os.path.join(os.path.dirname(sys.executable), srt_filename)
                    else:
                        srt_path = os.path.join(os.path.dirname(__file__), srt_filename)
                    
                    write_debug(f"Step 2: Saving SRT to: {srt_path}")
                    with open(srt_path, 'w', encoding='utf-8') as f:
                        f.write(srt_content)
                    
                    write_debug(f"Step 2 complete: SRT saved, size: {os.path.getsize(srt_path)} bytes")
                    
                    # Step 3: Use existing SRT-to-chapters pipeline
                    write_debug(f"Step 3: Converting SRT to chapters")
                    print(f"[FLASK] Step 3: Converting SRT to chapters")
                    update_progress("Generating chapters from SRT", 75)
                    
                    results = process_srt(srt_path, num_chapters, model, endpoint, custom_prompt)
                    write_debug(f"Step 3 complete: process_srt returned {len(results)} results")
                    print(f"[FLASK] Step 3 complete: {len(results)} chapters generated")
                    
                    if not results:
                        write_debug("ERROR: No chapters generated from SRT")
                        return jsonify({"error": "Failed to generate chapters from transcribed content"}), 500
                    
                    # Step 4: Return combined response
                    output = [f"{timestamp} {title}" for timestamp, title in results]
                    
                    write_debug(f"Step 4 complete: Returning {len(output)} chapters + SRT download")
                    print(f"[FLASK] SUCCESS: {len(output)} chapters generated")
                    print(f"[FLASK] About to return response with chapters={len(output)}, srt_download_url={f'/download_srt/{base_filename}'}")
                    
                    # CRITICAL: Set progress to 100 AFTER creating output
                    update_progress("Processing complete", 100)
                    
                    # Return immediately - don't wait for finally block
                    response_data = {
                        "chapters": output,
                        "srt_download_url": f"/download_srt/{base_filename}",
                        "srt_filename": srt_filename
                    }
                    write_debug(f"Returning response: chapters count={len(output)}, has srt_download_url={bool(response_data.get('srt_download_url'))}")
                    print(f"[FLASK] Response data keys: {list(response_data.keys())}")
                    return jsonify(response_data)
                    
                except Exception as media_error:
                    write_debug(f"ERROR in media processing: {media_error}")
                    print(f"[FLASK] ERROR in media processing: {media_error}")
                    import traceback
                    traceback.print_exc()
                    return jsonify({"error": f"Failed to process media file: {str(media_error)}"}), 500
            else:
                return jsonify({"error": "Unsupported file format"}), 400
        finally:
            # Clean up uploaded file
            try:
                os.unlink(upload_path)
            except:
                pass
    except Exception as e:
        print(f"[FLASK] Exception caught in /process: {e}", file=sys.stderr)
        print(f"[FLASK] Exception type: {type(e)}", file=sys.stderr)
        import traceback
        print(f"[FLASK] Traceback: {traceback.format_exc()}", file=sys.stderr)
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500

class API:
    def __init__(self, window):
        self._window = window
    def closeWindow(self):
        if self._window: self._window.destroy()
        os._exit(0)
    def minimizeWindow(self):
        if self._window: self._window.minimize()
    def set_window_position(self, x, y):
        if self._window: self._window.move(x, y)
    def get_window_position(self):
        if self._window: return {'x': self._window.x, 'y': self._window.y}
        return {'x': 0, 'y': 0}
    
    def resize_window(self, height):
        if self._window:
            current_width = self._window.width
            # Add a small buffer to the height to prevent scrollbars from flashing.
            self._window.resize(current_width, int(height) + 5)

if __name__ == "__main__":
    import threading
    
    logger.info("Starting Chapter Generator...")
    
    # Check if we're running as an executable
    try:
        import sys
        if getattr(sys, 'frozen', False):
            # Running as executable - use pywebview for standalone window
            logger.info("Running as executable - starting GUI mode")
            
            # Start Flask server in background thread
            import threading
            import time
            
            def run_server():
                app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
            
            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()
            
            # Wait for server to start
            time.sleep(2)
            
            # Create pywebview window
            api = API(None)
            window = webview.create_window(
                'SRT Chapter Generator', 
                'http://localhost:5000',
                frameless=True,
                easy_drag=False,
                width=586,
                height=900,
                min_size=(500, 600),
                js_api=api,
                resizable=True
            )
            webview.start()
        else:
            # Running as Python script - use GUI
            logger.info("Starting GUI mode...")
            api = API(None)
            window = webview.create_window(
                'SRT Chapter Generator', 
                app,
                frameless=True,
                easy_drag=False,
                width=586,
                height=900,
                min_size=(500, 600),
                js_api=api,
                resizable=True
            )
            api._window = window
            webview.start(http_server=True, debug=DEBUG, gui='edge')
    except Exception as e:
        logger.error(f"Startup error: {e}")
        logger.info("Starting in server mode...")
        logger.info(f"Server running at: http://localhost:5000")
        app.run(host='127.0.0.1', port=5000, debug=DEBUG)
