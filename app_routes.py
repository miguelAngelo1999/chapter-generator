"""
app_routes.py - Flask routes for Chapter Generator.
This file is loaded dynamically at runtime so patches can update
backend logic without requiring a full exe rebuild.
"""
import os
import sys
import glob


def register_routes(app, state):
    """Register all Flask routes. Called after app is created."""

    request = state['request']
    jsonify = state['jsonify']
    send_file = state['send_file']
    progress_data = state['progress_data']
    process_srt = state['process_srt']
    process_media_file = state['process_media_file']
    get_ollama_models = state['get_ollama_models']
    cleanup_old_files = state['cleanup_old_files']
    update_progress = state['update_progress']
    write_debug = state['write_debug']
    APP_VERSION = state['APP_VERSION']
    DEFAULT_OLLAMA_BASE_URL = state['DEFAULT_OLLAMA_BASE_URL']
    SUPPORTED_AUDIO_FORMATS = state['SUPPORTED_AUDIO_FORMATS']
    SUPPORTED_VIDEO_FORMATS = state['SUPPORTED_VIDEO_FORMATS']

    @app.route('/')
    def index():
        from chapter_generator import load_html_template
        html = load_html_template()
        html = html.replace('{{ ENDPOINT }}', DEFAULT_OLLAMA_BASE_URL)
        return html

    @app.route('/progress')
    def get_progress():
        return jsonify(state['progress_data'])

    @app.route('/check_updates', methods=['GET'])
    def check_updates_route():
        from updater import check_for_updates
        return jsonify(check_for_updates(state['APP_VERSION']))

    @app.route('/download_update', methods=['POST'])
    def download_update_route():
        data = request.get_json()
        download_url = data.get('download_url')
        new_version = data.get('new_version', '')
        if not download_url:
            return jsonify({"success": False, "error": "Download URL not provided."}), 400
        from updater import download_and_apply_update
        result = download_and_apply_update(download_url, new_version)
        return jsonify(result)

    @app.route('/api/version')
    def api_version():
        return jsonify({'version': state['APP_VERSION']})

    @app.route('/api/models', methods=['GET'])
    def api_get_models():
        endpoint = request.args.get('endpoint', DEFAULT_OLLAMA_BASE_URL)
        models = get_ollama_models(endpoint or DEFAULT_OLLAMA_BASE_URL)
        return jsonify(models)

    @app.route('/download_srt/<filename>')
    def download_srt(filename):
        try:
            search_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
            srt_path = os.path.join(search_dir, f"{filename}_transcribed.srt")
            if os.path.exists(srt_path):
                return send_file(srt_path, as_attachment=True, download_name=f"{filename}_transcribed.srt")
            matches = glob.glob(os.path.join(search_dir, f'*{filename}*.srt'))
            if matches:
                return send_file(matches[0], as_attachment=True, download_name=os.path.basename(matches[0]))
            return jsonify({"error": "SRT file not found"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/retry_chapters', methods=['POST'])
    def retry_chapters_route():
        try:
            srt_path_base = request.form.get('srt_path')
            num_chapters = int(request.form.get('num_chapters', 10))
            model = request.form.get('model')
            endpoint = request.form.get('ollama_endpoint', DEFAULT_OLLAMA_BASE_URL)
            custom_prompt = request.form.get('custom_prompt')
            if not srt_path_base or not model:
                return jsonify({"error": "Missing required parameters"}), 400
            search_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
            srt_path = os.path.join(search_dir, f"{srt_path_base}_transcribed.srt")
            if not os.path.exists(srt_path):
                return jsonify({"error": "SRT file not found."}), 404
            update_progress("Processing SRT file", 50)
            results = process_srt(srt_path, num_chapters, model, endpoint, custom_prompt)
            if not results:
                return jsonify({"error": "Failed to generate chapters"}), 500
            return jsonify({"chapters": [f"{ts} {title}" for ts, title in results]})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/process', methods=['POST'])
    def process_file_route():
        write_debug("=== FLASK PROCESS ROUTE START ===")
        try:
            if 'file' not in request.files:
                return jsonify({"error": "No file part"}), 400
            file = request.files['file']
            if file.filename == '':
                return jsonify({"error": "No selected file"}), 400
            num_chapters = int(request.form.get('num_chapters', 10))
            model = request.form.get('model')
            endpoint = request.form.get('ollama_endpoint', DEFAULT_OLLAMA_BASE_URL)
            custom_prompt = request.form.get('custom_prompt')
            srt_only = request.form.get('srt_only') == 'true'
            if not model and not srt_only:
                return jsonify({"error": "No model selected"}), 400

            upload_dir = os.path.join('C:\\', 'ProgramData', 'ChapterGenerator') if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
            os.makedirs(upload_dir, exist_ok=True)
            cleanup_old_files(upload_dir)
            upload_path = os.path.join(upload_dir, file.filename)
            file.save(upload_path)
            write_debug(f"File saved to: {upload_path}")

            try:
                file_ext = os.path.splitext(file.filename)[1].lower()
                update_progress("Starting processing", 0)

                if file_ext == '.srt':
                    update_progress("Processing SRT file", 50)
                    results = process_srt(upload_path, num_chapters, model, endpoint, custom_prompt)
                    if not results:
                        return jsonify({"error": "Failed to generate chapters"}), 500
                    output = [f"{ts} {title}" for ts, title in results]
                    update_progress("Processing complete", 100)
                    return jsonify({"chapters": output})

                elif file_ext in SUPPORTED_AUDIO_FORMATS or file_ext in SUPPORTED_VIDEO_FORMATS:
                    update_progress("Extracting audio from video", 5)
                    srt_content = process_media_file(upload_path)
                    if srt_content is None:
                        return jsonify({"error": "Failed to transcribe media file."}), 500

                    update_progress("Transcription complete", 50)
                    base_filename = os.path.splitext(os.path.basename(file.filename))[0]
                    srt_filename = f"{base_filename}_transcribed.srt"
                    srt_dir = os.path.join('C:\\', 'ProgramData', 'ChapterGenerator') if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
                    os.makedirs(srt_dir, exist_ok=True)
                    srt_path = os.path.join(srt_dir, srt_filename)
                    with open(srt_path, 'w', encoding='utf-8') as f:
                        f.write(srt_content)

                    if srt_only:
                        update_progress("Transcription complete", 100)
                        return jsonify({"srt_download_url": f"/download_srt/{base_filename}", "srt_filename": srt_filename})

                    update_progress("Generating chapters from SRT", 75)
                    results = process_srt(srt_path, num_chapters, model, endpoint, custom_prompt)
                    if not results:
                        return jsonify({"error": "Failed to generate chapters"}), 500
                    output = [f"{ts} {title}" for ts, title in results]
                    update_progress("Processing complete", 100)
                    return jsonify({"chapters": output, "srt_download_url": f"/download_srt/{base_filename}", "srt_filename": srt_filename})
                else:
                    return jsonify({"error": "Unsupported file format"}), 400
            finally:
                try:
                    os.unlink(upload_path)
                except Exception:
                    pass
        except Exception as e:
            write_debug(f"Error in /process: {e}")
            return jsonify({"error": str(e)}), 500
