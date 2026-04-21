import os
import uuid
import tempfile
import threading
import re
from flask import Flask, render_template, request, jsonify, send_file
import pypdf
from pydub import AudioSegment
import torch
from TTS.api import TTS
import nltk
from nltk.tokenize import sent_tokenize
import traceback

# Force Coqui TOS Agreement
os.environ["COQUI_TOS_AGREED"] = "1"
# Avoid some transformers import issues
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"

# --- Set Local Paths for everything ---
# Store AI models inside the project instead of System AppData
os.environ["TTS_HOME"] = os.path.abspath("models")
os.environ["XDG_DATA_HOME"] = os.path.abspath("models")

# Download NLTK data for sentence tokenization
nltk.download('punkt')

app = Flask(__name__)

# Local folders for uploads and models
LOCAL_TEMP_DIR = os.path.abspath("temp_files")
MODELS_DIR = os.path.abspath("models")
OUTPUTS_DIR = os.path.abspath("outputs")

for folder in [LOCAL_TEMP_DIR, MODELS_DIR, OUTPUTS_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

app.config['UPLOAD_FOLDER'] = LOCAL_TEMP_DIR
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB max upload

# Configure pydub to use the local ffmpeg
ffmpeg_path = os.path.abspath("ffmpeg.exe")
ffprobe_path = os.path.abspath("ffprobe.exe")

if os.path.exists(ffmpeg_path):
    AudioSegment.converter = ffmpeg_path
    print(f"Using local ffmpeg: {ffmpeg_path}")

if os.path.exists(ffprobe_path):
    AudioSegment.ffprobe = ffprobe_path
    print(f"Using local ffprobe: {ffprobe_path}")

# --- Auto-Cleanup Logic ---
def cleanup_old_files():
    """Delete files in outputs folder older than 24 hours."""
    now = time.time()
    if os.path.exists(OUTPUTS_DIR):
        for f in os.listdir(OUTPUTS_DIR):
            f_path = os.path.join(OUTPUTS_DIR, f)
            if os.stat(f_path).st_mtime < now - 24 * 3600:
                if os.path.isfile(f_path):
                    try:
                        os.remove(f_path)
                    except: pass

import time
# Run cleanup once on start
cleanup_old_files()

progress_store = {}

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")

VOICES_DIR = os.path.join('static', 'voices')

def get_available_voices():
    voices = []
    if os.path.exists(VOICES_DIR):
        for file in os.listdir(VOICES_DIR):
            if file.endswith(('.wav', '.mp3')):
                name = os.path.splitext(file)[0].replace('_', ' ').capitalize()
                voices.append({'id': file, 'name': name})
    return voices
# Load TTS Model
try:
    print("--- Starting to load TTS Model (XTTS-v2) ---")
    print("This might take a few minutes on the first run as it downloads ~2GB of models.")
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    print("--- TTS Model loaded successfully! ---")
except Exception as e:
    tts = None
    with open("error_log.txt", "w", encoding="utf-8") as f:
        f.write(f"Error Type: {type(e).__name__}\n")
        f.write(f"Error Message: {str(e)}\n")
        f.write(traceback.format_exc())
    print("!!! FAILED TO LOAD TTS MODEL - Error logged to error_log.txt !!!")
    traceback.print_exc()

def clean_arabic_text(text):
    # Remove excessive newlines and spaces
    text = re.sub(r'[\r\n]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def chunk_text(text, max_words=30):
    # Smart chunking using NLTK
    sentences = sent_tokenize(text)
    chunks = []
    current_chunk = []
    current_length = 0
    
    for sentence in sentences:
        words = sentence.split()
        if current_length + len(words) <= max_words:
            current_chunk.append(sentence)
            current_length += len(words)
        else:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
            
            if len(words) > max_words:
                for i in range(0, len(words), max_words):
                    chunks.append(" ".join(words[i:i+max_words]))
                current_chunk = []
                current_length = 0
            else:
                current_chunk = [sentence]
                current_length = len(words)
                
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        
    return chunks

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extract_text', methods=['POST'])
def extract_text():
    if 'pdf' not in request.files:
        return jsonify({'error': 'لم يتم العثور على ملف PDF'}), 400
        
    pdf_file = request.files['pdf']
    if pdf_file.filename == '':
        return jsonify({'error': 'اسم الملف فارغ'}), 400
        
    if not pdf_file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'يرجى رفع ملف بصيغة PDF فقط'}), 400

    try:
        temp_pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}.pdf")
        pdf_file.save(temp_pdf_path)
        
        reader = pypdf.PdfReader(temp_pdf_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + " "
        
        os.remove(temp_pdf_path)
        
        cleaned_text = clean_arabic_text(text)
        return jsonify({'text': cleaned_text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_voices', methods=['GET'])
def get_voices():
    return jsonify(get_available_voices())

@app.route('/generate_audio', methods=['POST'])
def generate_audio():
    if tts is None:
        return jsonify({'error': 'نموذج الصوت غير محمل.'}), 500
        
    text = request.form.get('text', '')
    is_preview = request.form.get('preview', 'false') == 'true'
    speed = float(request.form.get('speed', 1.0))

    if not text:
        return jsonify({'error': 'النص فارغ'}), 400
        
    voice_key = request.form.get('voice_key', '')
    ref_path = ""

    if voice_key and voice_key != 'custom':
        ref_path = os.path.abspath(os.path.join(VOICES_DIR, voice_key))
        if not os.path.exists(ref_path):
             return jsonify({'error': 'صوت المكتبة غير موجود.'}), 400
    else:
        if 'reference_audio' not in request.files:
            return jsonify({'error': 'يرجى اختيار صوت أو رفع ملف صوتي مرجعي.'}), 400
            
        ref_file = request.files['reference_audio']
        ref_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}_ref.wav")
        ref_file.save(ref_path)
    
    task_id = str(uuid.uuid4())
    progress_store[task_id] = {'status': 'processing', 'progress': 0, 'file': None, 'error': None, 'message': 'بدأ التحضير...'}
    
    is_temp_ref = (voice_key == 'custom' or not voice_key)
    thread = threading.Thread(target=process_audio_task, args=(task_id, text, ref_path, is_temp_ref, is_preview, speed))
    thread.start()
    
    return jsonify({'task_id': task_id})

def process_audio_task(task_id, text, ref_path, is_temp_ref, is_preview, speed):
    try:
        chunks = chunk_text(text, max_words=30)
        
        # If preview, only take first 3 chunks
        if is_preview:
            chunks = chunks[:2]
            progress_store[task_id]['message'] = 'توليد معاينة سريعة...'

        if not chunks:
            progress_store[task_id]['status'] = 'failed'
            progress_store[task_id]['error'] = 'لا يوجد نص صالح للتحويل.'
            return
            
        temp_dir = tempfile.mkdtemp()
        audio_paths = []
        
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
                
            progress = int(((i) / total_chunks) * 90)
            progress_store[task_id]['progress'] = progress
            progress_store[task_id]['message'] = f'توليد المقطع {i+1} من {total_chunks}...'
            
            chunk_audio_path = os.path.join(temp_dir, f"chunk_{i}.wav")
            
            tts.tts_to_file(
                text=chunk,
                speaker_wav=ref_path,
                language="ar",
                file_path=chunk_audio_path,
                speed=speed
            )
            
            audio_paths.append(chunk_audio_path)
            
        progress_store[task_id]['progress'] = 95
        progress_store[task_id]['message'] = 'جاري دمج المقاطع الصوتية...'
        
        combined_audio = AudioSegment.empty()
        for path in audio_paths:
            combined_audio += AudioSegment.from_wav(path)
            
        filename = f"preview_{task_id}.mp3" if is_preview else f"audiobook_{task_id}.mp3"
        final_output_path = os.path.join(OUTPUTS_DIR, filename)
        
        combined_audio.export(final_output_path, format="mp3", bitrate="128k")
        
        # Cleanup temp
        for path in audio_paths:
            if os.path.exists(path): os.remove(path)
        os.rmdir(temp_dir)
        if is_temp_ref and os.path.exists(ref_path): os.remove(ref_path)
            
        progress_store[task_id]['status'] = 'completed'
        progress_store[task_id]['progress'] = 100
        progress_store[task_id]['message'] = 'اكتملت المعاينة!' if is_preview else 'اكتمل التحويل بنجاح!'
        progress_store[task_id]['file'] = final_output_path
        
    except Exception as e:
        progress_store[task_id]['status'] = 'failed'
        error_detail = traceback.format_exc()
        progress_store[task_id]['error'] = f"حدث خطأ: {str(e)}"
        print(f"Error in task {task_id}:")
        print(error_detail)
        with open("task_errors.log", "a", encoding="utf-8") as f:
            f.write(f"Task ID: {task_id}\n{error_detail}\n{'-'*50}\n")

@app.route('/progress/<task_id>', methods=['GET'])
def get_progress(task_id):
    task = progress_store.get(task_id, None)
    if not task:
        return jsonify({'status': 'not_found'}), 404
    return jsonify(task)

@app.route('/download/<task_id>', methods=['GET'])
def download(task_id):
    task = progress_store.get(task_id)
    if task and task['status'] == 'completed':
        return send_file(task['file'], as_attachment=True, download_name='audiobook.mp3')
    return "Not ready or not found", 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)
