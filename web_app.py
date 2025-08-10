# web_app.py
import os
import re
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, make_response
from core.orchestrator import Orchestrator, CONVERSATIONS_DIR, StatusEnum

app = Flask(__name__)
orchestrator_instances = {}

@app.after_request
def add_no_cache_headers(response):
    """Disabilita la cache per tutti i file statici durante lo sviluppo."""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

def get_orchestrator(session_id, lang='en', architect_llm='gemini'):
    """Ora accetta anche la selezione dell'architetto."""
    if session_id not in orchestrator_instances:
        orchestrator_instances[session_id] = Orchestrator(
            session_id=session_id if session_id != "new" else None, 
            lang=lang,
            architect_llm=architect_llm
        )
    else:
        # FIX: Aggiorna architetto anche se orchestrator esiste già
        orchestrator = orchestrator_instances[session_id]
        
        # IMPORTANTE: Aggiorna l'architetto PRIMA di qualsiasi operazione che possa ricaricare lo stato
        orchestrator.architect_llm = architect_llm
        
        # Se l'architetto è cambiato, potrebbe essere necessario riconfigurare il modello
        if architect_llm != getattr(orchestrator, '_last_configured_architect', None):
            orchestrator._last_configured_architect = architect_llm
            # Forza la riconfigurazione del modello se necessario
            orchestrator._setup_initial_chat_session()
        
        # FIX: Assicura attributi di stato per recovery
        if not hasattr(orchestrator, 'status'):
            orchestrator.status = StatusEnum.IDLE
        if not hasattr(orchestrator, 'status_updated_at'):
            orchestrator.status_updated_at = datetime.now()
            
    return orchestrator_instances[session_id]

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/set_directory", methods=["POST"])
def set_directory():
    """NUOVO ENDPOINT: Imposta la directory di lavoro per una sessione."""
    data = request.json
    session_id = data.get("session_id")
    path = data.get("path")
    lang = data.get("lang", 'en')

    if not session_id or not path:
        return jsonify({"success": False, "error": "Dati mancanti"}), 400

    orchestrator = get_orchestrator(session_id, lang)
    response_message = orchestrator.set_working_directory(path)
    
    if "ERRORE" in response_message:
        return jsonify({"success": False, "message": response_message})
    else:
        orchestrator.save_state() # Salva lo stato dopo aver impostato la directory
        return jsonify({"success": True, "message": response_message, "session_id": orchestrator.session_id})

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Punto di ingresso principale. Riceve l'input dell'utente, lo passa all'Orchestratore,
    e poi streamma la risposta dalla coda di output dell'Orchestratore.
    """
    data = request.json
    user_input = data.get("message")
    session_id = data.get("session_id")
    lang = data.get("lang", 'en')
    architect_llm = data.get("architect", 'gemini')
    
    if not user_input or not session_id:
        return jsonify({"error": "Input o session_id mancante"}), 400
    
    orchestrator = get_orchestrator(session_id, lang, architect_llm)
    
    # Questa chiamata è ora non-bloccante. Elabora l'input e potrebbe
    # avviare il thread di sviluppo in background.
    orchestrator.process_user_input(user_input)
    
    def stream_from_queue():
        """
        Questo generatore si mette in ascolto sulla coda dell'orchestratore
        e invia i dati al frontend non appena diventano disponibili.
        """
        print(f"[TEMP DEBUG] stream_from_queue avviato per sessione {session_id}")
        chunk_count = 0
        while True:
            # .get() è bloccante: aspetta finché non c'è un elemento nella coda
            chunk = orchestrator.output_queue.get()
            chunk_count += 1
            print(f"[TEMP DEBUG] Chunk {chunk_count} ricevuto: {chunk[:200] if chunk else 'None'}...")
            if chunk is None: # 'None' è il nostro segnale per terminare lo stream
                print(f"[TEMP DEBUG] Stream terminato dopo {chunk_count} chunks")
                break
            yield chunk
        print(f"[TEMP DEBUG] Generatore completato")
            
    return Response(stream_from_queue(), mimetype='text/plain')

@app.route("/api/conversations", methods=["GET"])
def get_conversations():
    """Restituisce la lista di tutte le conversazioni salvate."""
    if not os.path.exists(CONVERSATIONS_DIR):
        return jsonify([])
    
    sessions = sorted([f.replace('.json', '') for f in os.listdir(CONVERSATIONS_DIR) if f.endswith('.json')], reverse=True)
    return jsonify(sessions)

@app.route("/api/history/<session_id>", methods=["GET"])
def get_history(session_id):
    """Restituisce la cronologia di una specifica conversazione senza inizializzare l'Orchestrator."""
    import json
    import os
    from core.orchestrator import CONVERSATIONS_DIR
    
    filepath = os.path.join(CONVERSATIONS_DIR, f"{session_id}.json")
    
    if not os.path.exists(filepath):
        return jsonify({"error": "Sessione non trovata"}), 404
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            state = json.load(f)
        
        return jsonify({
            "history": state.get("display_history", []), 
            "session_id": state.get("session_id", session_id),
            "architect_llm": state.get("architect_llm", "gemini")  # Include info architetto
        })
    except Exception as e:
        return jsonify({"error": f"Errore nel caricamento: {str(e)}"}), 500

@app.route("/api/conversation_info/<session_id>", methods=["GET"]) 
def get_conversation_info(session_id):
    """Restituisce informazioni sulla conversazione senza inizializzare l'Orchestrator."""
    import json
    import os
    from core.orchestrator import CONVERSATIONS_DIR
    
    filepath = os.path.join(CONVERSATIONS_DIR, f"{session_id}.json")
    
    if not os.path.exists(filepath):
        return jsonify({"error": "Sessione non trovata"}), 404
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            state = json.load(f)
        
        return jsonify({
            "session_id": state.get("session_id", session_id),
            "architect_llm": state.get("architect_llm", "gemini"),
            "mode": state.get("mode", "BRAINSTORMING"),
            "status": state.get("status", StatusEnum.IDLE),
            "lang": state.get("lang", "en"),
            "has_project_plan": bool(state.get("project_plan")),
            "has_working_directory": bool(state.get("working_directory")),
            # Informazioni fallback provider
            "original_architect": state.get("original_architect", state.get("architect_llm", "gemini")),
            "current_architect": state.get("current_architect", state.get("architect_llm", "gemini")),
            "fallback_active": state.get("fallback_active", False),
            "fallback_reason": state.get("fallback_reason", None)
        })
    except Exception as e:
        return jsonify({"error": f"Errore nel caricamento: {str(e)}"}), 500

@app.route("/api/rename", methods=["POST"])
def rename_conversation():
    """Permette di rinominare una conversazione."""
    data = request.json
    old_id = data.get("old_id")
    new_name = data.get("new_name")

    if not old_id or not new_name:
        return jsonify({"error": "Dati mancanti"}), 400

    new_id = re.sub(r'[^a-zA-Z0-9_-]', '_', new_name).lower()
    
    old_path = os.path.join(CONVERSATIONS_DIR, f"{old_id}.json")
    new_path = os.path.join(CONVERSATIONS_DIR, f"{new_id}.json")

    if not os.path.exists(old_path):
        return jsonify({"error": "Sessione originale non trovata"}), 404
    if os.path.exists(new_path):
        return jsonify({"error": "Un file con questo nome esiste già"}), 409

    try:
        os.rename(old_path, new_path)
        if old_id in orchestrator_instances:
            instance = orchestrator_instances.pop(old_id)
            instance.session_id = new_id
            instance.save_state()
            orchestrator_instances[new_id] = instance
        
        return jsonify({"success": True, "new_id": new_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/delete", methods=["POST"])
def delete_conversation():
    """Permette di eliminare una conversazione."""
    data = request.json
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"error": "Session ID mancante"}), 400

    filepath = os.path.join(CONVERSATIONS_DIR, f"{session_id}.json")

    if not os.path.exists(filepath):
        return jsonify({"error": "Conversazione non trovata"}), 404

    try:
        os.remove(filepath)
        # Rimuovi anche dall'cache se esiste
        if session_id in orchestrator_instances:
            del orchestrator_instances[session_id]
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Avviamo il server in modalità "threaded" per gestire correttamente
    # le richieste multiple e il lavoro in background.
    # host='0.0.0.0' permette connessioni da qualsiasi indirizzo
    app.run(debug=True, host='0.0.0.0', port=5050, threaded=True)