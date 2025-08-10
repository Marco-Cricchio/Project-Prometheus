# core/orchestrator.py

import os
import subprocess
from dotenv import load_dotenv
import json
from datetime import datetime
import select
import threading
import queue
import time
import tempfile

# Gestione import Gemini con lazy loading
class _GeminiImports:
    def __init__(self):
        self.available = None  # None = non testato, True = disponibile, False = non disponibile
        self.genai = None
        self.GenerationConfig = None
    
    def is_available(self):
        if self.available is None:
            self._try_import()
        return self.available
    
    def _try_import(self):
        try:
            import google.generativeai as genai
            from google.generativeai.types import GenerationConfig
            self.genai = genai
            self.GenerationConfig = GenerationConfig
            self.available = True
        except ImportError:
            self.available = False
        except Exception:
            self.available = False

_gemini = _GeminiImports()

def _lazy_import_gemini():
    """Compatibilità con il codice esistente."""
    return _gemini.is_available()


# Sistema di gestione errori centralizzato per i provider AI
class ProviderErrorHandler:
    """Gestisce errori e fallback automatico tra provider AI."""
    
    # Tipi di errore riconosciuti
    ERROR_TYPES = {
        'RATE_LIMIT': 'rate_limit',
        'QUOTA_EXCEEDED': 'quota_exceeded', 
        'CONNECTION_ERROR': 'connection_error',
        'USAGE_LIMIT': 'usage_limit',
        'API_KEY_INVALID': 'api_key_invalid',
        'GENERIC_ERROR': 'generic_error'
    }
    
    # Messaggi user-friendly per lingua italiana
    USER_MESSAGES_IT = {
        'rate_limit': "🔄 Il servizio è temporaneamente sovraccarico. Passo automaticamente al provider alternativo per continuare senza interruzioni...",
        'quota_exceeded': "⚡ Quota API raggiunta per questo provider. Continuo seamlessly con l'architetto alternativo...",
        'usage_limit': "⏳ Limite di utilizzo raggiunto. Effettuo il passaggio trasparente al backup per proseguire la sessione...",
        'connection_error': "🔗 Problema di connessione rilevato. Provo con il provider alternativo...",
        'api_key_invalid': "🔑 Chiave API non configurata o non valida per Gemini. Passo automaticamente a Claude per continuare senza interruzioni...",
        'generic_error': "⚠️ Errore temporaneo rilevato. Cambio provider per mantenere la continuità del servizio...",
        'both_failed': "🚫 Entrambi i provider hanno raggiunto i loro limiti di utilizzo. La sessione deve essere sospesa. Riprova più tardi quando i servizi saranno nuovamente disponibili.",
        'fallback_success': "✅ Passaggio completato con successo. La sessione continua con {provider}."
    }
    
    # Messaggi user-friendly per lingua inglese
    USER_MESSAGES_EN = {
        'rate_limit': "🔄 Service temporarily overloaded. Automatically switching to alternative provider to continue seamlessly...",
        'quota_exceeded': "⚡ API quota reached for this provider. Continuing seamlessly with alternative architect...",
        'usage_limit': "⏳ Usage limit reached. Making transparent switch to backup provider to continue the session...",
        'connection_error': "🔗 Connection issue detected. Trying with alternative provider...",
        'api_key_invalid': "🔑 API key not configured or invalid for Gemini. Automatically switching to Claude to continue seamlessly...",
        'generic_error': "⚠️ Temporary error detected. Switching provider to maintain service continuity...",
        'both_failed': "🚫 Both providers have reached their usage limits. Session must be suspended. Please try again later when services are available again.",
        'fallback_success': "✅ Switch completed successfully. Session continues with {provider}."
    }
    
    @staticmethod
    def detect_error_type(error_message, error_code=None):
        """
        Rileva il tipo di errore basandosi sul messaggio e codice.
        
        Args:
            error_message (str): Messaggio di errore
            error_code (int/str): Codice di errore (opzionale)
            
        Returns:
            str: Tipo di errore dalla enum ERROR_TYPES
        """
        if not error_message:
            return ProviderErrorHandler.ERROR_TYPES['GENERIC_ERROR']
        
        error_text = str(error_message).lower()
        
        # Detection per errori HTTP 429 (Rate Limit)
        if error_code == 429 or '429' in error_text or 'rate limit' in error_text or 'too many requests' in error_text:
            return ProviderErrorHandler.ERROR_TYPES['RATE_LIMIT']
        
        # Detection per quota API esaurite  
        if ('quota' in error_text and ('exceeded' in error_text or 'exhaust' in error_text)) or \
           'resource_exhausted' in error_text or \
           'quota_exceeded' in error_text or \
           'daily quota' in error_text or \
           'monthly quota' in error_text:
            return ProviderErrorHandler.ERROR_TYPES['QUOTA_EXCEEDED']
        
        # Detection per limiti di utilizzo Claude
        if 'limit reached' in error_text or 'usage limit' in error_text or 'daily limit' in error_text:
            return ProviderErrorHandler.ERROR_TYPES['USAGE_LIMIT']
        
        # Detection per API key non valide
        if any(keyword in error_text for keyword in ['api key not valid', 'api_key_invalid', 'invalid api key', 'api key is invalid']):
            return ProviderErrorHandler.ERROR_TYPES['API_KEY_INVALID']
        
        # Detection per errori di connessione
        if any(keyword in error_text for keyword in ['connection', 'timeout', 'network', 'unavailable']):
            return ProviderErrorHandler.ERROR_TYPES['CONNECTION_ERROR']
        
        return ProviderErrorHandler.ERROR_TYPES['GENERIC_ERROR']
    
    @staticmethod
    def get_user_message(error_type, lang='en', provider_name=None):
        """
        Restituisce messaggio user-friendly per il tipo di errore.
        
        Args:
            error_type (str): Tipo di errore
            lang (str): Lingua ('it' o 'en')
            provider_name (str): Nome del provider per messaggio di successo
            
        Returns:
            str: Messaggio formattato per l'utente
        """
        messages = ProviderErrorHandler.USER_MESSAGES_IT if lang == 'it' else ProviderErrorHandler.USER_MESSAGES_EN
        
        if error_type in messages:
            message = messages[error_type]
            if provider_name and '{provider}' in message:
                message = message.format(provider=provider_name)
            return message
        
        return messages['generic_error']
    
    @staticmethod
    def should_attempt_fallback(error_type):
        """
        Determina se tentare il fallback per questo tipo di errore.
        
        Args:
            error_type (str): Tipo di errore
            
        Returns:
            bool: True se si può tentare fallback
        """
        # Tutti gli errori tranne errori generici possono beneficiare del fallback
        return error_type != ProviderErrorHandler.ERROR_TYPES['GENERIC_ERROR']


CONVERSATIONS_DIR = "conversations"

# Costanti stato sviluppo
class StatusEnum:
    IDLE = "IDLE"
    RUNNING = "RUNNING" 
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    COMPLETED = "COMPLETED"

def _run_claude_with_prompt(prompt_text, working_dir=None, timeout=60):
    """Helper per eseguire Claude con prompt lunghi via stdin"""
    try:
        command_list = ["claude", "-p", "--dangerously-skip-permissions"]
        
        result = subprocess.run(
            command_list, 
            input=prompt_text,
            capture_output=True, 
            text=True, 
            check=False, 
            timeout=timeout,
            cwd=working_dir,
            encoding='utf-8'
        )
        
        
        if result.returncode != 0:
            error_msg = f"Errore: Claude command failed (code {result.returncode}): {result.stderr}"
            return error_msg
        
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        error_msg = f"Errore: Claude command timed out after {timeout} seconds"
        return error_msg
    except FileNotFoundError:
        error_msg = "Errore: Claude CLI not found. Please install Claude Code CLI."
        return error_msg
    except Exception as e:
        error_msg = f"Errore: Unexpected error: {e}"
        return error_msg

# I prompt ora sono multilingua
PROMPTS = {
    'it': {
        "system_instruction": (
            "Sei un architetto software di nome Prometheus. Il tuo compito è dialogare con l'utente per definire le specifiche di un'applicazione. "
            "Sii conciso e diretto. Fornisci risposte brevi e mirate. Elabora solo se l'utente te lo chiede esplicitamente. "
            "Se l'utente ti chiede un consiglio, spiega le opzioni in modo chiaro e fornisci una raccomandazione motivata. "
            "Il tuo output deve essere in formato Markdown."
        ),
        "initial_message": "Ciao! Sono Prometheus. Qual è la tua idea di base?",
        "error_create_directory": "ERRORE: Impossibile creare la directory: {error}",
        "error_not_directory": "ERRORE: Il percorso fornito esiste ma non è una directory.",
        "error_no_working_dir": "ERRORE CRITICO: Non posso avviare lo sviluppo senza una directory di lavoro impostata. Per favore, fornisci un percorso valido.",
        "error_no_working_dir_set": "ERRORE: La directory di lavoro non è impostata.",
        "success_directory_created": "OK. La directory non esisteva, l'ho creata e la userò: `{path}`",
        "success_directory_exists": "OK, userò la directory esistente: `{path}`"
    },
    'en': {
        "system_instruction": (
            "You are a software architect named Prometheus. Your task is to talk with the user to define the specifications for an application. "
            "Be concise and direct. Provide short, targeted answers. Elaborate only if the user explicitly asks you to. "
            "If the user asks for advice, explain the options clearly and provide a reasoned recommendation. "
            "Your output must be in Markdown format."
        ),
        "initial_message": "Hello! I'm Prometheus. What's your core idea?",
        "error_create_directory": "ERROR: Unable to create directory: {error}",
        "error_not_directory": "ERROR: The provided path exists but is not a directory.",
        "error_no_working_dir": "CRITICAL ERROR: Cannot start development without a working directory set. Please provide a valid path.",
        "error_no_working_dir_set": "ERROR: The working directory is not set.",
        "success_directory_created": "OK. The directory didn't exist, I created it and will use: `{path}`",
        "success_directory_exists": "OK, I will use the existing directory: `{path}`"
    }
}

class Orchestrator:
    """
    Il cervello di Project Prometheus.
    VERSIONE v10.0: Ciclo di sviluppo completamente autonomo SENZA break prematuro.
    """
    def __init__(self, session_id=None, lang='en', architect_llm='gemini'):
        # Orchestrator initialization
        self.lang = lang if lang in PROMPTS else 'en'
        self.architect_llm = architect_llm
        self.working_directory = None
        
        # Nuovi attributi per il ciclo autonomo
        self.dev_thread = None
        self.is_running = False
        self.output_queue = queue.Queue()
        
        # FIX: Gestione stati per UI dinamica e recovery
        self.status = StatusEnum.IDLE
        self.status_updated_at = datetime.now()
        
        # Attributi per gestione fallback provider
        self.original_architect = architect_llm  # Mantiene l'architetto originalmente selezionato
        self.current_architect = architect_llm   # Architetto attualmente in uso (può cambiare per fallback)
        self.fallback_active = False             # Flag per indicare se siamo in modalità fallback
        self.fallback_reason = None              # Motivo del fallback per logging/UI
        
        # Configura Gemini se selezionato e disponibile
        if self.architect_llm == 'gemini' and _lazy_import_gemini():
            self._configure_gemini()
        
        # --- LOGICA DI CORREZIONE DEL BUG ---
        session_file_path = os.path.join(CONVERSATIONS_DIR, f"{session_id}.json") if session_id else None

        if session_id and session_file_path and os.path.exists(session_file_path):
            self.load_state(session_id)
        else:
            self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
            self.mode = "BRAINSTORMING"
            self.project_plan = None
            self.conversation_history = []
            # Inizializza attributi fallback per nuove sessioni
            self.original_architect = architect_llm
            self.current_architect = architect_llm
            self.fallback_active = False
            self.fallback_reason = None
            self._setup_initial_chat_session()
            

    def _configure_gemini(self):
        load_dotenv()
        try:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key: raise ValueError("GEMINI_API_KEY non trovata.")
            _gemini.genai.configure(api_key=api_key)
        except Exception as e:
            print(f"ERRORE CRITICO in configurazione Gemini: {e}")
            raise

    def _update_status(self, new_status):
        """FIX: Aggiorna lo stato e il timestamp"""
        self.status = new_status
        self.status_updated_at = datetime.now()
        self.save_state(verbose=False)  # Salvataggio silenzioso per aggiornamenti automatici
        # Rimuovo anche il print del status che spamma l'output


    def _get_architect_response(self, full_dev_prompt):
        """Chiama l'architetto selezionato con fallback automatico intelligente."""
        
        # Prima prova con l'architetto corrente (può essere diverso dall'originale se già in fallback)
        if self.current_architect == 'gemini' and _lazy_import_gemini() and self.model:
            try:
                response = self.model.generate_content(full_dev_prompt, generation_config=self.generation_config)
                return response.text.strip()
            except Exception as e:
                # Analizza l'errore per determinare il tipo
                error_type = ProviderErrorHandler.detect_error_type(str(e))
                
                # Se possiamo tentare fallback e non siamo già in fallback
                if ProviderErrorHandler.should_attempt_fallback(error_type) and not self.fallback_active:
                    return self._attempt_fallback_to_claude(error_type, full_dev_prompt)
                else:
                    # Se siamo già in fallback o l'errore non è gestibile, propaga l'errore con messaggio user-friendly
                    user_message = ProviderErrorHandler.get_user_message(error_type, self.lang)
                    if self.fallback_active:
                        # Entrambi i provider hanno fallito
                        both_failed_msg = ProviderErrorHandler.get_user_message('both_failed', self.lang)
                        raise Exception(both_failed_msg)
                    else:
                        raise Exception(user_message)
        
        # Claude (selezionato originariamente o come fallback)
        try:
            claude_response = _run_claude_with_prompt(full_dev_prompt, timeout=180)
            
            # Controlla se Claude ha restituito un messaggio di limite raggiunto
            if self._is_claude_limit_error(claude_response):
                error_type = ProviderErrorHandler.detect_error_type(claude_response)
                
                # Se possiamo tentare fallback e non siamo già in fallback
                if ProviderErrorHandler.should_attempt_fallback(error_type) and not self.fallback_active:
                    return self._attempt_fallback_to_gemini(error_type, full_dev_prompt)
                else:
                    # Se siamo già in fallback o non possiamo fare altro
                    if self.fallback_active:
                        both_failed_msg = ProviderErrorHandler.get_user_message('both_failed', self.lang)
                        raise Exception(both_failed_msg)
                    else:
                        user_message = ProviderErrorHandler.get_user_message(error_type, self.lang)
                        raise Exception(user_message)
            
            return claude_response
            
        except subprocess.TimeoutExpired:
            error_type = ProviderErrorHandler.ERROR_TYPES['CONNECTION_ERROR']
            if not self.fallback_active and self.current_architect == 'claude':
                return self._attempt_fallback_to_gemini(error_type, full_dev_prompt)
            else:
                user_message = ProviderErrorHandler.get_user_message(error_type, self.lang)
                raise Exception(user_message)
        except Exception as e:
            # Gestione errori generici di Claude
            if "limit reached" in str(e).lower() and not self.fallback_active:
                error_type = ProviderErrorHandler.ERROR_TYPES['USAGE_LIMIT']
                return self._attempt_fallback_to_gemini(error_type, full_dev_prompt)
            else:
                raise e
    
    def _is_claude_limit_error(self, response):
        """Controlla se la risposta di Claude indica un limite raggiunto."""
        if not response:
            return False
        response_lower = response.lower()
        return any(phrase in response_lower for phrase in [
            'limit reached', 'usage limit', 'daily limit', 
            'too many requests', 'rate limit'
        ])
    
    def _attempt_fallback_to_claude_for_brainstorming(self, error_type, prompt):
        """Versione per brainstorming che manda messaggi separati nella coda."""
        print(f"[TEMP DEBUG] _attempt_fallback_to_claude_for_brainstorming chiamato con error_type: {error_type}")
        print(f"[TEMP DEBUG] Prompt length: {len(prompt)}")
        print(f"[TEMP DEBUG] Current fallback_active: {getattr(self, 'fallback_active', 'Non definito')}")
        
        # Aggiorna lo stato del fallback
        self.fallback_active = True
        self.current_architect = 'claude'
        self.fallback_reason = error_type
        
        try:
            # Messaggio di notifica del cambio
            user_message = ProviderErrorHandler.get_user_message(error_type, self.lang)
            print(f"[TEMP DEBUG] Inviando user_message nella coda: {user_message[:100]}...")
            self.output_queue.put(f"\n{user_message}\n")
            
            # Segnale di cambio architetto
            print(f"[TEMP DEBUG] Inviando segnale cambio architetto nella coda")
            self.output_queue.put("[ARCHITECT_CHANGE]claude")
            
            print(f"[TEMP DEBUG] Chiamando Claude...")
            claude_response = _run_claude_with_prompt(prompt, timeout=180)
            print(f"[TEMP DEBUG] Claude ha risposto con {len(claude_response) if claude_response else 0} caratteri")
            
            # Invia la risposta di Claude
            print(f"[TEMP DEBUG] Inviando risposta Claude nella coda")
            self.output_queue.put(claude_response)
            
            # Messaggio di successo
            success_message = ProviderErrorHandler.get_user_message('fallback_success', self.lang, 'Claude')
            print(f"[TEMP DEBUG] Inviando success_message nella coda: {success_message[:100]}...")
            self.output_queue.put(f"\n{success_message}\n")
            
            # Non restituire nulla - tutto è stato inviato tramite coda
            return None
            
        except Exception as claude_error:
            print(f"[TEMP DEBUG] Claude ha fallito: {claude_error}")
            # Se anche Claude fallisce, entrambi i provider sono inutilizzabili
            both_failed_msg = ProviderErrorHandler.get_user_message('both_failed', self.lang)
            self.output_queue.put(f"Errore: {both_failed_msg}")
            return None

    def _attempt_fallback_to_claude(self, error_type, prompt):
        """Tenta il fallback da Gemini a Claude (versione originale per sviluppo)."""
        
        # Notifica l'utente del cambio
        user_message = ProviderErrorHandler.get_user_message(error_type, self.lang)
        self.output_queue.put(f"\n{user_message}\n")
        
        # Aggiorna lo stato del fallback
        self.fallback_active = True
        self.current_architect = 'claude'
        self.fallback_reason = error_type
        
        # Invia segnale di cambio architetto al frontend
        self.output_queue.put("[ARCHITECT_CHANGE]claude")
        
        try:
            claude_response = _run_claude_with_prompt(prompt, timeout=180)
            
            # Notifica successo del fallback
            success_message = ProviderErrorHandler.get_user_message('fallback_success', self.lang, 'Claude')
            self.output_queue.put(f"{success_message}\n")
            
            return claude_response
        except Exception as claude_error:
            # Se anche Claude fallisce, entrambi i provider sono inutilizzabili
            both_failed_msg = ProviderErrorHandler.get_user_message('both_failed', self.lang)
            raise Exception(both_failed_msg)
    
    def _attempt_fallback_to_gemini(self, error_type, prompt):
        """Tenta il fallback da Claude a Gemini."""
        # Controlla se Gemini è disponibile
        if not _lazy_import_gemini() or not self.model:
            # Se Gemini non è disponibile, non possiamo fare fallback
            both_failed_msg = ProviderErrorHandler.get_user_message('both_failed', self.lang)
            raise Exception(both_failed_msg)
        
        # Notifica l'utente del cambio
        user_message = ProviderErrorHandler.get_user_message(error_type, self.lang)
        self.output_queue.put(f"\n{user_message}\n")
        
        # Aggiorna lo stato del fallback
        self.fallback_active = True
        self.current_architect = 'gemini'
        self.fallback_reason = error_type
        
        # Invia segnale di cambio architetto al frontend
        self.output_queue.put("[ARCHITECT_CHANGE]gemini")
        
        try:
            response = self.model.generate_content(prompt, generation_config=self.generation_config)
            
            # Notifica successo del fallback
            success_message = ProviderErrorHandler.get_user_message('fallback_success', self.lang, 'Gemini')
            self.output_queue.put(f"{success_message}\n")
            
            return response.text.strip()
        except Exception as gemini_error:
            # Se anche Gemini fallisce, entrambi i provider sono inutilizzabili
            both_failed_msg = ProviderErrorHandler.get_user_message('both_failed', self.lang)
            raise Exception(both_failed_msg)

    def _setup_initial_chat_session(self):
        # Solo inizializza Gemini se è l'architetto selezionato e disponibile
        if self.architect_llm == 'gemini' and _lazy_import_gemini():
            try:
                # --- CONFIGURAZIONE DI GENERAZIONE PER GEMINI ---
                self.generation_config = _gemini.GenerationConfig(
                    max_output_tokens=65536,
                    temperature=0.7,  # Un po' di creatività per il brainstorming
                )

                system_instruction = PROMPTS[self.lang]["system_instruction"]
                
                self.model = _gemini.genai.GenerativeModel(
                    model_name='gemini-2.5-pro', 
                    system_instruction=system_instruction,
                    generation_config=self.generation_config
                )
                self.chat_session = self.model.start_chat(history=[])
            except Exception as e:
                # Se l'inizializzazione di Gemini fallisce (es. API key invalida)
                # impostiamo tutto su None e il sistema userà Claude come fallback
                print(f"Warning: Gemini initialization failed: {e}")
                self.model = None
                self.chat_session = None
                self.generation_config = None
                # Non forziamo il fallback qui, lo faremo quando necessario
        else:
            # Per Claude o quando Gemini non è disponibile, non inizializziamo Gemini
            self.model = None
            self.chat_session = None
            self.generation_config = None
        
        if not self.conversation_history:
             initial_message = PROMPTS[self.lang]["initial_message"]
             self.conversation_history.append(f"[Prometheus]: {initial_message}")

    def set_working_directory(self, path_from_ui):
        """Nuova funzione per validare e impostare la directory di lavoro."""
        path = os.path.expanduser(path_from_ui.strip())
        if not os.path.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
                self.working_directory = os.path.abspath(path)
                msg = PROMPTS[self.lang]["success_directory_created"].format(path=self.working_directory)
                return msg
            except Exception as e:
                error_msg = PROMPTS[self.lang]["error_create_directory"].format(error=e)
                return error_msg
        elif os.path.isdir(path):
            self.working_directory = os.path.abspath(path)
            msg = PROMPTS[self.lang]["success_directory_exists"].format(path=self.working_directory)
            return msg
        else:
            error_msg = PROMPTS[self.lang]["error_not_directory"]
            return error_msg

    def save_state(self, verbose=True):
        if not os.path.exists(CONVERSATIONS_DIR):
            os.makedirs(CONVERSATIONS_DIR)
        
        # CORREZIONE: Serializzazione sicura della cronologia di Gemini (solo se esiste)
        gemini_history_serializable = []
        if self.chat_session is not None:
            for msg in self.chat_session.history:
                try:
                    gemini_history_serializable.append({
                        "role": msg.role,
                        "parts": [part.text for part in msg.parts]
                    })
                except Exception as e:
                    if verbose:  # Solo se richiesto esplicitamente
                        print(f"Warning: Skipping corrupted message in history: {e}")
                    continue

        state = {
            "session_id": self.session_id,
            "mode": self.mode,
            "project_plan": self.project_plan,
            "lang": self.lang,
            "architect_llm": self.architect_llm,
            "working_directory": self.working_directory,
            "gemini_history": gemini_history_serializable,
            "display_history": self.conversation_history,
            # FIX: Salva stato sviluppo per recovery
            "status": getattr(self, 'status', 'IDLE'),
            "status_updated_at": getattr(self, 'status_updated_at', datetime.now()).isoformat(),
            "is_running": self.is_running,
            "development_was_active": self.is_running and self.mode == "DEVELOPMENT",
            # Salva stato fallback provider
            "original_architect": getattr(self, 'original_architect', self.architect_llm),
            "current_architect": getattr(self, 'current_architect', self.architect_llm),
            "fallback_active": getattr(self, 'fallback_active', False),
            "fallback_reason": getattr(self, 'fallback_reason', None)
        }
        
        filepath = os.path.join(CONVERSATIONS_DIR, f"{self.session_id}.json")
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=4)
            if verbose:  # Solo se richiesto esplicitamente
                print(f"Stato conversazione salvato in {filepath}")
        except Exception as e:
            print(f"ERRORE nel salvataggio di {filepath}: {e}")

    def load_state(self, session_id):
        filepath = os.path.join(CONVERSATIONS_DIR, f"{session_id}.json")
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            # PRESERVA la selezione dell'architetto dell'utente
            user_selected_architect = self.architect_llm
            
            self.session_id = state["session_id"]
            self.mode = state["mode"]
            self.project_plan = state.get("project_plan")
            self.lang = state.get("lang", "en")
            # NON sovrascrivere l'architetto selezionato dall'utente
            self.architect_llm = user_selected_architect  # MANTIENI LA SELEZIONE UTENTE
            self.working_directory = state.get("working_directory")
            self.conversation_history = state["display_history"]
            
            # FIX: Ripristina stato sviluppo
            self.status = state.get("status", StatusEnum.IDLE)
            status_updated_str = state.get("status_updated_at")
            if status_updated_str:
                self.status_updated_at = datetime.fromisoformat(status_updated_str)
            else:
                self.status_updated_at = datetime.now()
            
            # FIX: Recupera stato thread sviluppo
            was_running = state.get("development_was_active", False)
            self.is_running = False  # Reset iniziale, verrà riavviato se necessario
            
            # Ripristina stato fallback provider
            self.original_architect = state.get("original_architect", user_selected_architect)
            self.current_architect = state.get("current_architect", user_selected_architect)
            self.fallback_active = state.get("fallback_active", False)
            self.fallback_reason = state.get("fallback_reason", None)
            
            self._setup_initial_chat_session()
            
            # CORREZIONE: Ricostruzione sicura della cronologia (solo per Gemini)
            if self.architect_llm == 'gemini' and _lazy_import_gemini() and self.chat_session is not None:
                for msg_data in state.get("gemini_history", []):
                    try:
                        # Prova diversi modi per accedere a Content e Part
                        try:
                            # Metodo moderno
                            content = _gemini.genai.types.Content(
                                role=msg_data['role'], 
                                parts=[_gemini.genai.types.Part(text=part) for part in msg_data['parts']]
                            )
                        except AttributeError:
                            # Metodo alternativo per versioni diverse
                            try:
                                import google.generativeai.types as genai_types
                                content = genai_types.Content(
                                    role=msg_data['role'], 
                                    parts=[genai_types.Part(text=part) for part in msg_data['parts']]
                                )
                            except (AttributeError, ImportError):
                                # Fallback - skip this message
                                print(f"Skipping message due to API version incompatibility")
                                continue
                        self.chat_session.history.append(content)
                    except Exception as e:
                        print(f"Warning: Skipping corrupted message in history: {e}")
                        continue
            
            # FIX: Riavvia ciclo sviluppo se era attivo
            if was_running and self.mode == "DEVELOPMENT" and self.project_plan and self.working_directory:
                self._update_status(StatusEnum.RUNNING)
                self.is_running = True
                # Avvia il thread con un messaggio di recovery
                self.dev_thread = threading.Thread(target=self._development_loop_recovery)
                self.dev_thread.start()
            
        except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
            print(f"ATTENZIONE: File di salvataggio {session_id} corrotto o non valido ({e}). Avvio di una nuova sessione con questo ID.")
            if os.path.exists(filepath):
                backup_path = filepath + f".corrupt.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                try:
                    os.rename(filepath, backup_path)
                    print(f"File corrotto salvato come backup: {backup_path}")
                except:
                    os.remove(filepath)
            
            self.session_id = session_id
            self.mode = "BRAINSTORMING"
            self.project_plan = None
            self.working_directory = None
            self.conversation_history = []
            # Inizializza attributi fallback per sessioni corrotte/ripristinate
            self.original_architect = self.architect_llm
            self.current_architect = self.architect_llm
            self.fallback_active = False
            self.fallback_reason = None
            self._setup_initial_chat_session()

    def get_output_stream(self):
        """
        Generator che yielda l'output dal ciclo di sviluppo autonomo.
        Da usare dall'interfaccia per ricevere aggiornamenti in tempo reale.
        """
        while True:
            try:
                # Aspetta per un output dalla coda (timeout per non bloccare)
                output = self.output_queue.get(timeout=1.0)
                if output is None:  # Segnale di fine
                    break
                yield output
                self.output_queue.task_done()
            except queue.Empty:
                continue

    def process_user_input(self, user_text):
        """Punto di ingresso che mette in coda le azioni."""
        self.conversation_history.append(f"[User]: {user_text}")
        
        if "ACCENDI I MOTORI!" in user_text.upper() and self.mode == "BRAINSTORMING":
            self.start_development_phase()
        else: # Qualsiasi altro input, sia brainstorming che feedback di sviluppo
            # Invece di restituire un generatore, mettiamo il messaggio in una coda di input
            # per essere elaborato dal thread principale (semplificazione per ora)
            for chunk in self.handle_brainstorming(user_text):
                 self.output_queue.put(chunk)
            self.output_queue.put(None) # Segnale di fine per questo stream

    def _create_brainstorm_prompt(self, user_text):
        """Crea il prompt standardizzato per il brainstorming."""
        conversation_context = "\n".join(self.conversation_history[:-1])  # Escludi l'ultimo messaggio utente
        
        return f"""Sei un architetto software di nome Prometheus. Il tuo compito è dialogare con l'utente per definire le specifiche di un'applicazione.

**FASE ATTUALE: BRAINSTORMING**
NON implementare ancora nulla. Siamo ancora nella fase di definizione dei requisiti e architettura.

Sii conciso e diretto. Fornisci risposte brevi e mirate. Elabora solo se l'utente te lo chiede esplicitamente.
Se l'utente ti chiede un consiglio, spiega le opzioni in modo chiaro e fornisci una raccomandazione motivata.
Il tuo output deve essere in formato Markdown.

**CRONOLOGIA CONVERSAZIONE:**
{conversation_context}

**DOMANDA ATTUALE DELL'UTENTE:**
{user_text}

IMPORTANTE: Rispondi solo come architetto che sta definendo i requisiti. NON scrivere codice o creare file. Continua la discussione per chiarire i dettagli dell'architettura."""

    def handle_brainstorming(self, user_text):
        """Gestisce il brainstorming e mette l'output nella coda."""
        try:
            full_response = ""
            
            # Controlla se Gemini è selezionato ma non disponibile (API key invalida, ecc.)
            if self.architect_llm == 'gemini' and (_lazy_import_gemini() is False or self.chat_session is None):
                # Gemini è selezionato ma non disponibile - forza fallback
                if not self.fallback_active:
                    error_type = ProviderErrorHandler.ERROR_TYPES['API_KEY_INVALID']
                    try:
                        brainstorm_prompt = self._create_brainstorm_prompt(user_text)
                        self._attempt_fallback_to_claude_for_brainstorming(error_type, brainstorm_prompt)
                        # Il fallback ha messo tutto nella coda - termina il generatore
                        self.output_queue.put(None)
                        return
                    except Exception as fallback_error:
                        yield f"Errore: {fallback_error}"
                        return
                else:
                    # Fallback già attivo, usa Claude direttamente
                    brainstorm_prompt = self._create_brainstorm_prompt(user_text)
                    full_response = _run_claude_with_prompt(brainstorm_prompt, timeout=60)
                    yield full_response
            elif self.architect_llm == 'gemini' and _lazy_import_gemini() and self.chat_session is not None:
                # Gemini con streaming
                try:
                    response_stream = self.chat_session.send_message(user_text, stream=True)
                    for chunk in response_stream:
                        try:
                            full_response += chunk.text
                            yield chunk.text
                        except ValueError:
                            pass # Ignora i chunk vuoti
                except Exception as gemini_error:
                    # Rileva il tipo di errore e tenta fallback se appropriato
                    error_type = ProviderErrorHandler.detect_error_type(str(gemini_error))
                    should_fallback = ProviderErrorHandler.should_attempt_fallback(error_type)
                    
                    if should_fallback and not self.fallback_active:
                        try:
                            # Fallback a Claude
                            brainstorm_prompt = self._create_brainstorm_prompt(user_text)
                            self._attempt_fallback_to_claude_for_brainstorming(error_type, brainstorm_prompt)
                            # Il fallback ha messo tutto nella coda - termina il generatore
                            self.output_queue.put(None)
                            return
                        except Exception as fallback_error:
                            # Se anche il fallback fallisce
                            yield f"Errore: {fallback_error}"
                            return
                    else:
                        # Non è possibile il fallback o entrambi i provider hanno fallito
                        yield f"Errore: {gemini_error}"
                        return
            else:
                # Claude (sia selezionato che fallback)
                brainstorm_prompt = self._create_brainstorm_prompt(user_text)
                full_response = _run_claude_with_prompt(brainstorm_prompt, timeout=60)
                yield full_response
            
            self.conversation_history.append(f"[Prometheus]: {full_response}")
            self.save_state(verbose=False)  # Salvataggio silenzioso durante brainstorming
        except Exception as e:
            yield f"Errore: {e}"

    def start_development_phase(self):
        """Prepara il PRP e avvia il ciclo di sviluppo autonomo in un thread."""
        self.output_queue.put("[THINKING]Sto analizzando la nostra conversazione per creare il Piano di Progetto (PRP)...")
        
        if not self.working_directory:
            error_msg = PROMPTS[self.lang]["error_no_working_dir"]
            self.output_queue.put(error_msg)
            self.output_queue.put(None)
            return

        self.mode = "DEVELOPMENT"
        
        try:
            # Crea il Piano di Progetto (PRP)
            prp_prompt = (
                f"Basandoti su tutta la conversazione precedente con l'utente, crea un Piano di Progetto (PRP) dettagliato e strutturato. "
                f"Il PRP deve includere: 1) Obiettivo del progetto, 2) Funzionalità principali, 3) Architettura tecnica suggerita, "
                f"4) Fasi di sviluppo ordinate, 5) Tecnologie consigliate. "
                f"Cronologia conversazione:\n---\n{self.conversation_history}\n---\n\n"
                f"Scrivi il PRP in formato Markdown, strutturato e professionale."
            )
            
            # FIX: Usa l'architetto selezionato anche per il PRP
            prp_response = self._get_architect_response(prp_prompt)
            self.project_plan = prp_response
            
            # MODIFICA: Invia il PRP come un blocco unico per una corretta renderizzazione
            prp_output = f"\n\n**Piano di Progetto Finalizzato!**\n\n---\n{self.project_plan}\n---\n\n"
            self.output_queue.put(prp_output)
            self.conversation_history.append(f"[System]: PRP Generato:\n{self.project_plan}")
            
            if self.lang == 'it':
                self.output_queue.put("\n🚀 **ACCENDO I MOTORI!** Avvio del ciclo di sviluppo autonomo. Scrivi 'PAUSA' per interrompere.\n")
            else:
                self.output_queue.put("\n🚀 **STARTING ENGINES!** Starting autonomous development cycle. Write 'STOP' to interrupt.\n")
            
            # Avvia il ciclo di sviluppo in un thread per non bloccare l'app
            self.is_running = True
            self.dev_thread = threading.Thread(target=self._development_loop)
            self.dev_thread.start()
            
        except Exception as e:
            self.output_queue.put(f"\n\nERRORE durante la creazione del PRP: {e}")
            self.mode = "BRAINSTORMING"
            self.output_queue.put(None)

    def _development_loop(self):
        """Il vero motore autonomo che gira in background, ora senza interruzioni."""
        user_feedback = "Inizia il lavoro basandoti sul PRP."
        
        while self.is_running:
            # Esegui un passo di sviluppo
            for chunk in self.handle_development_step(user_feedback):
                self.output_queue.put(chunk)
            
            # Resetta il feedback per il prossimo ciclo automatico
            user_feedback = None 
            
            # Se is_running è diventato False durante il passo, esci
            if not self.is_running:
                break
            
            time.sleep(2) # Piccola pausa per dare respiro al sistema
        
        self.output_queue.put("[INFO]Ciclo di sviluppo in pausa.")
        # Mettiamo un segnale di fine per chiudere lo stream se necessario
        self.output_queue.put(None)

    def _development_loop_recovery(self):
        """FIX: Ciclo di sviluppo che riprende dopo un riavvio dell'applicazione"""
        
        # Messaggio di recovery per l'utente
        recovery_msg = (
            "\n🔄 **RECOVERY AUTOMATICO** - L'applicazione è stata riavviata.\n"
            f"Riprendo il ciclo di sviluppo autonomo da dove si era interrotto.\n"
            f"Progetto: {os.path.basename(self.working_directory)}\n"
            f"Modalità: {self.mode} | Stato: {self.status}\n\n"
        )
        self.output_queue.put(recovery_msg)
        
        # Messaggio per l'architetto con context recovery
        recovery_feedback = (
            "RECOVERY: L'applicazione è stata riavviata. Analizza la cronologia delle azioni "
            "per determinare a che punto eravamo nel ciclo di sviluppo TDD e riprendi da lì. "
            "Se l'ultimo comando ha avuto successo, procedi al prossimo step logico. "
            "Se c'erano errori, risolvi prima quelli."
        )
        
        # Usa il ciclo normale con feedback di recovery
        user_feedback = recovery_feedback
        
        while self.is_running:
            # Esegui un passo di sviluppo
            for chunk in self.handle_development_step(user_feedback):
                self.output_queue.put(chunk)
            
            # Resetta il feedback per il prossimo ciclo automatico
            user_feedback = None 
            
            # Se is_running è diventato False durante il passo, esci
            if not self.is_running:
                break
            
            time.sleep(2) # Piccola pausa per dare respiro al sistema
        
        self.output_queue.put("[INFO]Ciclo di sviluppo recovery terminato.")
        self.output_queue.put(None)

    def handle_development_step(self, user_feedback=None):
        """Esegue UN singolo passo del ciclo di sviluppo."""
        if not self.working_directory:
            yield PROMPTS[self.lang]["error_no_working_dir_set"]
            return
        
        try:
            # Preparare il prompt per l'architetto con context-awareness MIGLIORATO
            dev_prompt_context = (
                f"Sei l'ARCHITETTO TDD per questo progetto. Analizza ATTENTAMENTE il contesto e guida lo sviluppo.\n\n"
                f"**PIANO DI PROGETTO (PRP):**\n---\n{self.project_plan}\n---\n\n"
                f"**CRONOLOGIA AZIONI COMPLETA:**\n---\n{self.conversation_history}\n---\n\n"
                f"**DIRECTORY LAVORO:** {self.working_directory}\n"
                f"**IMPORTANTE:** Questa directory È già la ROOT del progetto. NON creare sottocartelle con il nome del progetto.\n"
                f"Tutti i file devono essere creati direttamente in questa directory o nelle sue sottocartelle logiche.\n\n"
                
                f"**ANALISI OBBLIGATORIA - LEGGI ATTENTAMENTE L'ULTIMO OUTPUT:**\n"
                f"Prima di decidere, analizza ESATTAMENTE cosa è successo nell'ultima azione:\n"
                f"1. **Files Esistenti:** Quali file sono stati creati/modificati nell'ultima azione?\n"
                f"2. **Test Status:** I test sono stati eseguiti? Sono passati o falliti?\n"
                f"3. **Errori:** Ci sono stati errori di compilazione, import, o esecuzione?\n"
                f"4. **Output Specifico:** Leggi l'ultimo output di Claude per capire cosa è stato fatto\n"
                f"5. **Fase TDD Attuale:** RED (test falliti), GREEN (implementare), o REFACTOR (migliorare)\n\n"
            )
            
            if user_feedback and user_feedback.strip():
                 dev_prompt_context += f"L'utente ha fornito il seguente feedback o istruzione: '{user_feedback}'. Dagli la priorità.\n\n"
            
            # Aggiungi informazioni sullo stato attuale della directory
            try:
                import os
                files_in_dir = []
                if os.path.exists(self.working_directory):
                    for root, dirs, files in os.walk(self.working_directory):
                        for file in files:
                            rel_path = os.path.relpath(os.path.join(root, file), self.working_directory)
                            files_in_dir.append(rel_path)
                
                dev_prompt_context += f"**STATO DIRECTORY CORRENTE:**\n"
                if files_in_dir:
                    dev_prompt_context += f"Files presenti: {', '.join(files_in_dir[:10])}{'...' if len(files_in_dir) > 10 else ''}\n\n"
                else:
                    dev_prompt_context += f"Directory vuota - nessun file presente\n\n"
            except Exception:
                dev_prompt_context += f"**STATO DIRECTORY:** Impossibile leggere contenuto directory\n\n"

            # ISTRUZIONI SPECIFICHE PER ARCHITETTO TDD CON DECISION TREE
            dev_prompt_instruction = (
                "ANALIZZA L'ULTIMO OUTPUT DI CLAUDE E DECIDI IL PROSSIMO PASSO CON QUESTA LOGICA PRECISA:\n\n"
                
                "**DECISION TREE - LEGGI E SEGUI ESATTAMENTE:**\n"
                "1️⃣ **SE DIRECTORY VUOTA/NESSUN FILE:** → Setup iniziale (package.json, struttura base)\n"
                "2️⃣ **SE SETUP FATTO MA NO TESTING FRAMEWORK:** → Installa framework test\n"
                "3️⃣ **SE FRAMEWORK TEST OK MA NO TEST FILES:** → RED PHASE (crea primo test che fallisce)\n"
                "4️⃣ **SE TEST FALLISCONO (ERROR/FAILED):** → GREEN PHASE (implementa per far passare)\n"
                "5️⃣ **SE TEST PASSANO (PASSED/SUCCESS):** → Prossimo RED PHASE (test per nuova feature)\n"
                "6️⃣ **SE ERRORI DI COMPILAZIONE/IMPORT:** → Fix errori prima di continuare\n"
                "7️⃣ **SE CODICE FUNZIONA MA NON PULITO:** → REFACTOR PHASE (migliora qualità)\n\n"
                
                "**COMANDI SPECIFICI PER FASE:**\n"
                "• **Setup:** `npm init -y` o `touch requirements.txt`\n"
                "• **Test Framework:** `npm install --save-dev jest` o `pip install pytest`\n"
                "• **Run Test:** `npm test` o `python -m pytest` o `jest` o `pytest -v`\n"
                "• **Create Files:** Usa prompt high-level per implementazioni\n\n"
                
                "**ESEMPI DECISION MAKING:**\n"
                "❌ **SBAGLIATO:** 'Prima iterazione TDD - Setup progetto'\n"
                "✅ **CORRETTO:** 'npm install --save-dev jest' (se manca framework)\n"
                "✅ **CORRETTO:** 'pytest -v' (se devi vedere status test)\n"
                "✅ **CORRETTO:** 'Crea test/todo.test.js che testa addTodo() function - deve fallire inizialmente'\n\n"
                
                "**REGOLE FERREE:**\n"
                "1. NON ripetere lo stesso comando/decisione dell'iterazione precedente\n"
                "2. LEGGI attentamente l'ultimo output di Claude per capire cosa è successo\n"
                "3. SE vedi test FAILED → implementa codice per farli passare\n"
                "4. SE vedi test PASSED → crea nuovo test per prossima feature\n"
                "5. SE vedi errori → risolvili prima di continuare con TDD\n"
                "6. **CRITICAL:** NON creare sottocartelle con il nome del progetto. La directory corrente è già la root.\n"
                "7. **CRITICAL:** Tutti i file vanno nella directory corrente o in sottocartelle logiche (src/, tests/, etc.)\n\n"
                
                "**FORMATO OUTPUT:** \n"
                "Rispondi SOLO con:\n"
                "- Un comando shell (es: `npm test`)\n"
                "- O un prompt specifico per Claude (es: 'Implementa la funzione addTodo in src/todo.js')\n"
                
                "NO spiegazioni, NO 'Prima iterazione', NO ripetizioni. SOLO IL PROSSIMO PASSO CONCRETO."
            )
            
            full_dev_prompt = dev_prompt_context + dev_prompt_instruction

            yield "[THINKING]" # Segnale pulito per l'animazione
            
            # Ottieni il prossimo comando/prompt dall'architetto selezionato
            gemini_prompt_for_claude = self._get_architect_response(full_dev_prompt)
            
            self.conversation_history.append(f"[Prometheus (to Claude)]: {gemini_prompt_for_claude}")
            
            yield f"[CLAUDE_PROMPT]{gemini_prompt_for_claude}" # Segnale con il prompt
            
            # Esecuzione con Popen
            command_list = ["claude", "-p", "--dangerously-skip-permissions", gemini_prompt_for_claude]
            
            process = subprocess.Popen(
                command_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                cwd=self.working_directory
            )

            yield "[CLAUDE_WORKING]" # Segnale di inizio lavoro per Claude

            full_claude_output = ""
            # Leggi da stdout e stderr senza bloccare
            while process.poll() is None and self.is_running:
                reads = [process.stdout.fileno(), process.stderr.fileno()]
                ret = select.select(reads, [], [], 1.0)  # Timeout per permettere check di is_running

                for fd in ret[0]:
                    if fd == process.stdout.fileno():
                        line = process.stdout.readline()
                        if line:
                            yield line
                            full_claude_output += line
                    if fd == process.stderr.fileno():
                        line = process.stderr.readline()
                        if line:
                            stderr_line = f"[STDERR]: {line}"
                            yield stderr_line
                            full_claude_output += stderr_line
            
            # Se il processo è ancora in esecuzione ma dobbiamo fermarci, terminalo
            if process.poll() is None and not self.is_running:
                process.terminate()
                yield "\n[INTERRUPTED] Processo interrotto dall'utente."
            
            # Leggi output rimanente
            stdout, stderr = process.communicate()
            if stdout:
                yield stdout
                full_claude_output += stdout
            if stderr:
                stderr_final = f"[STDERR]: {stderr}"
                yield stderr_final
                full_claude_output += stderr_final

            # Segnala completamento del ciclo
            if self.lang == 'it':
                yield "\n\n[CYCLE_COMPLETE]🔄 **Passo completato.** Il ciclo continua autonomamente..."
            else:
                yield "\n\n[CYCLE_COMPLETE]🔄 **Step completed.** The cycle continues autonomously..."

            self.conversation_history.append(f"[Claude (Output)]: {full_claude_output}")
            self.save_state(verbose=False)  # Salvataggio silenzioso durante sviluppo automatico
            
        except Exception as e:
            yield f"\n\n**ERRORE CRITICO:** {e}"
