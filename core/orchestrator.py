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
import logging

# Setup debug logging to file in HOME directory (persists across git clones)
debug_logger = logging.getLogger('prometheus_debug')
debug_logger.setLevel(logging.DEBUG)
log_file_path = os.path.expanduser('~/prometheus_debug.log')
debug_handler = logging.FileHandler(log_file_path)
debug_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
debug_handler.setFormatter(debug_formatter)
debug_logger.addHandler(debug_handler)

# Setup PROMPT ANALYSIS logger - separate file for performance analysis
prompt_logger = logging.getLogger('prometheus_prompts')
prompt_logger.setLevel(logging.INFO)
prompt_log_path = os.path.expanduser('~/prometheus_prompts.log')
prompt_handler = logging.FileHandler(prompt_log_path)
prompt_formatter = logging.Formatter('%(asctime)s | %(message)s')
prompt_handler.setFormatter(prompt_formatter)
prompt_logger.addHandler(prompt_handler)

# Log startup message to confirm logging is working
debug_logger.info("="*50)
debug_logger.info("PROMETHEUS DEBUG LOGGING STARTED")
debug_logger.info(f"Debug log: {log_file_path}")
debug_logger.info(f"Prompt analysis log: {prompt_log_path}")
debug_logger.info("="*50)

prompt_logger.info("="*80)
prompt_logger.info("PROMETHEUS PROMPT ANALYSIS LOG - SESSION START")
prompt_logger.info("="*80)

# Prompt analysis utility functions
def log_prompt_interaction(phase, source, target, prompt_text, response_text="", timing_ms=0, tokens_estimate=0):
    """
    Log detailed prompt interaction for performance analysis
    
    Args:
        phase: "BRAINSTORMING" or "DEVELOPMENT"
        source: "USER", "PROMETHEUS", "GEMINI", "CLAUDE"  
        target: "USER", "PROMETHEUS", "GEMINI", "CLAUDE"
        prompt_text: The actual prompt sent
        response_text: The response received (first 200 chars)
        timing_ms: Time taken for the interaction
        tokens_estimate: Estimated token count
    """
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    # Calculate sizes
    prompt_chars = len(prompt_text) if prompt_text else 0
    response_chars = len(response_text) if response_text else 0
    prompt_words = len(prompt_text.split()) if prompt_text else 0
    response_words = len(response_text.split()) if response_text else 0
    
    # Estimate tokens if not provided
    if tokens_estimate == 0:
        tokens_estimate = (prompt_chars + response_chars) // 4
    
    prompt_logger.info(f"[{timestamp}] PHASE:{phase} | {source}→{target}")
    prompt_logger.info(f"  📊 METRICS: {prompt_chars:,}chars | {prompt_words:,}words | ~{tokens_estimate:,}tokens | {timing_ms}ms")
    
    if prompt_text:
        # Log first 300 chars of prompt for analysis
        prompt_preview = prompt_text[:300] + "..." if len(prompt_text) > 300 else prompt_text
        prompt_logger.info(f"  📝 PROMPT: {prompt_preview}")
    
    if response_text:
        # Log first 200 chars of response
        response_preview = response_text[:200] + "..." if len(response_text) > 200 else response_text
        prompt_logger.info(f"  💬 RESPONSE: {response_preview}")
    
    prompt_logger.info(f"  {'─'*80}")

def log_phase_transition(from_phase, to_phase, session_id="", reason=""):
    """Log when we switch between brainstorming and development phases"""
    prompt_logger.info(f"🔄 PHASE TRANSITION: {from_phase} → {to_phase}")
    if session_id:
        prompt_logger.info(f"  📋 Session: {session_id}")
    if reason:
        prompt_logger.info(f"  💡 Reason: {reason}")
    prompt_logger.info(f"  {'='*80}")

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

def _run_claude_with_prompt(prompt_text, working_dir=None, timeout=60, retry_count=0, max_retries=3):
    """
    Helper per eseguire Claude con prompt lunghi via stdin con retry intelligente e timeout progressivi.
    
    Args:
        prompt_text: Il prompt da inviare a Claude
        working_dir: Directory di lavoro
        timeout: Timeout iniziale (60s -> 120s -> 300s)
        retry_count: Numero retry corrente
        max_retries: Massimo numero di retry
    """
    
    # Timeout progressivi: 60s -> 120s -> 300s
    timeout_levels = [60, 120, 300]
    current_timeout = timeout_levels[min(retry_count, len(timeout_levels) - 1)]
    
    # Enhanced logging con metrics
    start_time = time.time()
    debug_logger.info(f"=== CLAUDE CLI EXECUTION START ===")
    debug_logger.info(f"Retry: {retry_count}/{max_retries}, Timeout: {current_timeout}s")
    debug_logger.info(f"Working dir: {working_dir}")
    debug_logger.info(f"Prompt length: {len(prompt_text)} characters")
    
    try:
        command_list = ["claude", "-p", "--dangerously-skip-permissions"]
        
        result = subprocess.run(
            command_list, 
            input=prompt_text,
            capture_output=True, 
            text=True, 
            check=False, 
            timeout=current_timeout,
            cwd=working_dir,
            encoding='utf-8'
        )
        
        execution_time = time.time() - start_time
        debug_logger.info(f"Claude CLI completed in {execution_time:.2f}s")
        debug_logger.info(f"Return code: {result.returncode}")
        
        if result.returncode != 0:
            error_msg = f"Errore: Claude command failed (code {result.returncode}): {result.stderr}"
            debug_logger.error(f"Claude CLI error: {error_msg}")
            
            # Classificazione errori per retry logic
            error_type = _classify_claude_error(result.stderr, result.returncode)
            debug_logger.info(f"Error classified as: {error_type}")
            
            # Retry solo per errori temporanei
            if error_type == "temporary" and retry_count < max_retries:
                debug_logger.info(f"Retrying due to temporary error...")
                return _retry_claude_with_backoff(prompt_text, working_dir, current_timeout, retry_count, max_retries)
            
            return error_msg
        
        debug_logger.info(f"Claude CLI successful - Output length: {len(result.stdout)} characters")
        return result.stdout.strip()
        
    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        error_msg = f"Errore: Claude command timed out after {current_timeout} seconds"
        debug_logger.error(f"Claude CLI timeout after {execution_time:.2f}s")
        
        # Retry con timeout maggiore
        if retry_count < max_retries:
            debug_logger.info(f"Retrying with increased timeout...")
            return _retry_claude_with_backoff(prompt_text, working_dir, current_timeout, retry_count, max_retries)
        
        return error_msg
        
    except FileNotFoundError:
        error_msg = "Errore: Claude CLI not found. Please install Claude Code CLI."
        debug_logger.error("Claude CLI not found")
        return error_msg
        
    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = f"Errore: Unexpected error: {e}"
        debug_logger.error(f"Unexpected error after {execution_time:.2f}s: {e}")
        return error_msg


def _classify_claude_error(stderr_output, return_code):
    """Classifica gli errori di Claude per determinare se vale la pena riprovare."""
    stderr_lower = stderr_output.lower() if stderr_output else ""
    
    # Errori temporanei (vale la pena riprovare)
    temporary_indicators = [
        "timeout", "connection", "network", "rate limit", 
        "temporarily", "try again", "server error", "503", "502", "504"
    ]
    
    # Errori permanenti (non vale la pena riprovare)  
    permanent_indicators = [
        "permission", "not found", "invalid", "authentication",
        "forbidden", "401", "403", "400"
    ]
    
    for indicator in temporary_indicators:
        if indicator in stderr_lower:
            return "temporary"
            
    for indicator in permanent_indicators:
        if indicator in stderr_lower:
            return "permanent"
    
    # Default: considera temporaneo per sicurezza
    return "temporary"


def _retry_claude_with_backoff(prompt_text, working_dir, timeout, retry_count, max_retries):
    """Implementa retry con backoff exponenziale."""
    retry_count += 1
    
    # Backoff exponenziale: 1s, 2s, 4s
    backoff_time = 2 ** (retry_count - 1)
    debug_logger.info(f"Waiting {backoff_time}s before retry {retry_count}/{max_retries}")
    
    time.sleep(backoff_time)
    
    return _run_claude_with_prompt(prompt_text, working_dir, timeout, retry_count, max_retries)

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
        self.tdd_mode = True  # Default: TDD abilitato
        
        # Nuovi attributi per il ciclo autonomo
        self.dev_thread = None
        self.is_running = False
        self.output_queue = queue.Queue()
        
        # Completion detection per evitare loop infiniti
        self.consecutive_completion_signals = 0
        self.max_consecutive_completions = 1  # Stop dopo 1 solo segnale (ULTRA aggressivo)
        self.total_cycles = 0
        self.max_total_cycles = 10  # Failsafe: stop dopo 10 cicli totali (molto ridotto)
        
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
        
        start_time = time.time()
        
        # Prima prova con l'architetto corrente (può essere diverso dall'originale se già in fallback)
        if self.current_architect == 'gemini' and _lazy_import_gemini() and self.model:
            try:
                # LOG: Prompt to Gemini
                log_prompt_interaction(
                    phase=self.mode,
                    source="PROMETHEUS",
                    target="GEMINI", 
                    prompt_text=full_dev_prompt,
                    response_text="",
                    timing_ms=0
                )
                
                response = self.model.generate_content(full_dev_prompt, generation_config=self.generation_config)
                response_text = response.text.strip()
                
                # LOG: Response from Gemini
                elapsed_ms = int((time.time() - start_time) * 1000)
                log_prompt_interaction(
                    phase=self.mode,
                    source="GEMINI",
                    target="PROMETHEUS",
                    prompt_text="",
                    response_text=response_text,
                    timing_ms=elapsed_ms
                )
                
                return response_text
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
            # LOG: Prompt to Claude
            log_prompt_interaction(
                phase=self.mode,
                source="PROMETHEUS",
                target="CLAUDE",
                prompt_text=full_dev_prompt,
                response_text="",
                timing_ms=0
            )
            
            claude_response = _run_claude_with_prompt(full_dev_prompt, self.working_directory, timeout=180)
            
            # LOG: Response from Claude
            elapsed_ms = int((time.time() - start_time) * 1000)
            log_prompt_interaction(
                phase=self.mode,
                source="CLAUDE",
                target="PROMETHEUS",
                prompt_text="",
                response_text=claude_response,
                timing_ms=elapsed_ms
            )
            
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
        
        # Aggiorna lo stato del fallback
        self.fallback_active = True
        self.current_architect = 'claude'
        self.fallback_reason = error_type
        
        try:
            # Messaggio di notifica del cambio
            user_message = ProviderErrorHandler.get_user_message(error_type, self.lang)
            self.output_queue.put(f"\n{user_message}\n")
            
            # Segnale di cambio architetto
            self.output_queue.put("[ARCHITECT_CHANGE]claude")
            
            claude_response = _run_claude_with_prompt(prompt, self.working_directory, timeout=180)
            
            # Invia la risposta di Claude
            self.output_queue.put(claude_response)
            
            # Messaggio di successo
            success_message = ProviderErrorHandler.get_user_message('fallback_success', self.lang, 'Claude')
            self.output_queue.put(f"\n{success_message}\n")
            
            # Non restituire nulla - tutto è stato inviato tramite coda
            return None
            
        except Exception as claude_error:
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
            claude_response = _run_claude_with_prompt(prompt, self.working_directory, timeout=180)
            
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
        debug_logger.info(f"set_working_directory called with: {path_from_ui}")
        
        path = os.path.expanduser(path_from_ui.strip())
        debug_logger.info(f"Expanded path: {path}")
        
        if not os.path.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
                self.working_directory = os.path.abspath(path)
                debug_logger.info(f"Created and set working_directory to: {self.working_directory}")
                msg = PROMPTS[self.lang]["success_directory_created"].format(path=self.working_directory)
                return msg
            except Exception as e:
                debug_logger.error(f"Failed to create directory {path}: {e}")
                error_msg = PROMPTS[self.lang]["error_create_directory"].format(error=e)
                return error_msg
        elif os.path.isdir(path):
            self.working_directory = os.path.abspath(path)
            debug_logger.info(f"Set working_directory to existing: {self.working_directory}")
            
            # SAFETY CHECK: Avvisa se la directory contiene file
            try:
                files_in_dir = []
                for root, dirs, files in os.walk(path):
                    for file in files:
                        # Ignora file di sistema come .DS_Store
                        if file == '.DS_Store':
                            continue
                        rel_path = os.path.relpath(os.path.join(root, file), path)
                        files_in_dir.append(rel_path)
                
                if files_in_dir:
                    file_list = ', '.join(files_in_dir[:5])
                    if len(files_in_dir) > 5:
                        file_list += f" (e altri {len(files_in_dir)-5} file)"
                    
                    msg = f"⚠️ **ATTENZIONE:** Directory non vuota - contiene: {file_list}. Durante lo sviluppo potrei modificare file esistenti. Assicurati che questa sia la directory corretta!"
                    return msg
            except Exception:
                pass
            
            msg = PROMPTS[self.lang]["success_directory_exists"].format(path=self.working_directory)
            return msg
        else:
            debug_logger.error(f"Path is not a directory: {path}")
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
            "tdd_mode": getattr(self, 'tdd_mode', True),
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
            "fallback_reason": getattr(self, 'fallback_reason', None),
            # Salva contatori completion detection
            "consecutive_completion_signals": getattr(self, 'consecutive_completion_signals', 0),
            "total_cycles": getattr(self, 'total_cycles', 0)
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
            self.tdd_mode = state.get("tdd_mode", True)  # Default: TDD abilitato
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
            
            # Ripristina contatori completion detection
            self.consecutive_completion_signals = state.get("consecutive_completion_signals", 0)
            self.total_cycles = state.get("total_cycles", 0)
            
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
        
        # LOG: User input in brainstorming phase
        log_prompt_interaction(
            phase=self.mode,
            source="USER", 
            target="PROMETHEUS",
            prompt_text=user_text,
            response_text="",
            timing_ms=0
        )
        
        self.conversation_history.append(f"[User]: {user_text}")
        
        # CRITICAL FIX: Salva sempre la sessione dopo aver aggiunto input utente
        self.save_state(verbose=False)
        
        # FIX: Trigger specifici e inequivocabili per avviare lo sviluppo
        trigger_phrases = [
            "accendi i motori", "inizia sviluppo", "avvia sviluppo", "start development",
            "iniziamo a implementare", "ora implementa", "crea l'app ora", "build it now", 
            "let's code", "iniziamo l'implementazione", "procedi con l'implementazione",
            "develop it", "create the app", "implement it", "code it", "make it happen"
        ]
        
        user_text_lower = user_text.lower()
        should_start_dev = any(phrase in user_text_lower for phrase in trigger_phrases)
        
        if should_start_dev and self.mode == "BRAINSTORMING":
            self.start_development_phase()
        elif self.mode == "DEVELOPMENT" and not self.is_running:
            # GESTIONE RISPOSTA UTENTE DURANTE SVILUPPO
            # Se siamo in modalità sviluppo ma il ciclo è fermo (domanda in attesa), riavvia con feedback
            self.output_queue.put("[INFO]🔄 Ricevuta risposta utente - riavvio ciclo di sviluppo...")
            
            # Reset contatori e riavvia con la risposta dell'utente
            self.consecutive_completion_signals = 0
            self.is_running = True
            
            # Crea feedback specifico con la risposta dell'utente
            user_feedback = f"RISPOSTA UTENTE AL CONFLITTO: {user_text}. Procedi di conseguenza seguendo le istruzioni dell'utente."
            
            # Riavvia il ciclo di sviluppo in un nuovo thread
            self.dev_thread = threading.Thread(target=self._development_loop_with_feedback, args=(user_feedback,))
            self.dev_thread.start()
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
                    full_response = _run_claude_with_prompt(brainstorm_prompt, self.working_directory, timeout=60)
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
                full_response = _run_claude_with_prompt(brainstorm_prompt, self.working_directory, timeout=60)
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

        # LOG: Phase transition
        log_phase_transition(
            from_phase="BRAINSTORMING", 
            to_phase="DEVELOPMENT",
            session_id=self.session_id,
            reason="User triggered development start"
        )
        
        self.mode = "DEVELOPMENT"
        
        # Reset contatori per detection del completamento
        self.consecutive_completion_signals = 0
        self.total_cycles = 0
        
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
    
    def _detect_project_completion(self, claude_response):
        """Rileva se Claude indica che il progetto è completato usando keyword inequivocabile."""
        if not claude_response:
            return False
        
        # CRITICAL FIX: Non rilevare completion durante brainstorming
        if self.mode == "BRAINSTORMING":
            return False
        
        # PRIMARY: Keyword inequivocabile (case-insensitive)
        completion_keyword = "[PROMETHEUS_COMPLETE]"
        if completion_keyword.lower() in claude_response.lower():
            debug_logger.info(f"🏁 INEQUIVOCABLE COMPLETION KEYWORD detected: {completion_keyword}")
            # Send signal to frontend for immediate UX feedback
            if hasattr(self, 'output_queue'):
                self.output_queue.put("[PROMETHEUS_COMPLETE]Task completato con keyword inequivocabile")
            return True
        
        response_lower = claude_response.lower()
        
        # FALLBACK: Detection legacy per compatibilità (ma keyword ha priorità)
        # ENHANCED: Rileva modifiche semplici (cambio colore, testo, etc)
        # Queste dovrebbero terminare immediatamente dopo la modifica
        simple_changes = [
            "colore", "color", "sostituisci", "replace", "cambia", "change",
            "modifica", "modify", "aggiorna", "update", "viola", "giallo", 
            "rosso", "blu", "green", "purple", "yellow", "red", "blue"
        ]
        
        # Check se è una richiesta di modifica semplice nella conversation history
        is_simple_change = False
        if hasattr(self, 'conversation_history') and self.conversation_history:
            recent_messages = ' '.join(self.conversation_history[-3:]).lower()
            is_simple_change = any(word in recent_messages for word in simple_changes)
        
        # Per modifiche semplici, detection più aggressivo
        if is_simple_change:
            simple_completion_indicators = [
                "sostituito", "replaced", "cambiato", "changed", 
                "aggiornato", "updated", "modificato", "modified",
                "applicato", "applied", "implementato", "implemented"
            ]
            if any(word in response_lower for word in simple_completion_indicators):
                debug_logger.info(f"🚀 SIMPLE CHANGE COMPLETION detected: {[w for w in simple_completion_indicators if w in response_lower]}")
                return True
        
        # Keywords di completamento (con frasi dalla chat reale)
        completion_phrases = [
            "applicazione completata",
            "progetto completato",
            "progetto completo", # FIX: Claude dice "completo" non "completato"
            "completamente implementata", 
            "completamente funzionante",
            "implementazione completata",
            "pronto all'uso",
            "pronta per l'uso",
            "implementation complete",
            "application completed", 
            "ready to use",
            "fully functional",
            "project completed",
            "tutto implementato",
            "all features implemented",
            # FIXES da chat reale:
            "completata con",  # "completata con viola implementato"
            "completo e funzionante",  # "progetto completo e funzionante"
            "è funzionale",
            "modificata correttamente",
            "modifica applicata",
            "modifica completata",  # Nuovo pattern dal prompt
            "changed successfully",
            "change completed"
        ]
        
        # Rileva frasi di repetizione (indica loop) - AGGIORNATE CON FRASI DAL LOG PIÙ RECENTE
        repetition_phrases = [
            "the directory appears to be empty",
            "l'applicazione è già",
            "è già implementata", 
            "è già completa",
            "già completa e funzionante",
            "applicazione è già completa",
            "already implemented",
            "already complete", 
            "già completamente implementata",
            "progetto è pronto",
            "tutto è implementato",
            # Nuove frasi dal log utente precedente
            "progetto è già completo",
            "already exists and contains exactly",
            "file già stato creato correttamente",
            "secondo le specifiche",
            "html file already exists",
            "exactly what was requested",
            "project is complete according",
            "meets the specifications",
            "il bottone è già implementato",
            "progetto è completo secondo",
            # NUOVE FRASI DAL LOG ATTUALE - ciclo HTML button
            "looking at the current state",
            "i understand you've completed",
            "following the decision tree",
            "files esistenti:",
            "status generale:",
            "claude confirmed implementation",
            "the jest configuration",
            "no tests found",
            "implementation completed",
            "red button has been implemented",
            "bottone.html exists",
            "since we have a working html file"
        ]
        
        completion_detected = any(phrase in response_lower for phrase in completion_phrases)
        repetition_detected = any(phrase in response_lower for phrase in repetition_phrases)
        
        # DEBUG: Log detection details - SEMPRE per diagnosticare
        matched_phrases = []
        for phrase in completion_phrases:
            if phrase in response_lower:
                matched_phrases.append(f"COMPLETION: {phrase}")
        for phrase in repetition_phrases:
            if phrase in response_lower:
                matched_phrases.append(f"REPETITION: {phrase}")
        
        if completion_detected or repetition_detected:
            debug_logger.info(f"✅ DETECTION TRIGGERED: {matched_phrases}")
            debug_logger.info(f"Response snippet: {response_lower[:200]}...")
        else:
            debug_logger.info(f"❌ No completion detected in response")
            # Mostra alcune parole chiave per debug
            key_words = [word for word in response_lower.split() if any(target in word for target in ['completo', 'complete', 'già', 'already', 'esistere', 'exists'])]
            if key_words:
                debug_logger.info(f"Key words found: {key_words[:10]}")
        
        # Se rileva completamento o ripetizione, conta come segnale di fine
        return completion_detected or repetition_detected

    def _detect_user_question(self, claude_response):
        """Rileva se Claude sta facendo domande all'utente che richiedono risposta."""
        if not claude_response:
            return False
        
        response_lower = claude_response.lower()
        
        # Pattern che indicano domande dirette all'utente
        question_patterns = [
            "come vuoi procedere?",
            "quale preferisci?", 
            "che cosa scegli?",
            "come procedere?",
            "quale opzione",
            "**opzioni:**",
            "**opzioni**",
            "1. **sovrascrivere**",
            "2. **creare**", 
            "3. **chiedere**",
            "vuoi che proceda",
            "how do you want to proceed",
            "which option do you prefer",
            "what would you like",
            "which do you prefer",
            "should i proceed",
            "what should i do"
        ]
        
        # Cerca anche pattern di domande con punti interrogativi in contesti specifici
        question_context_patterns = [
            "conflitto.*\\?",
            "scegli.*\\?", 
            "preferisci.*\\?",
            "vuoi.*\\?",
            "procedere.*\\?",
            "opzione.*\\?"
        ]
        
        import re
        
        # Check direct patterns
        for pattern in question_patterns:
            if pattern in response_lower:
                return True
        
        # Check regex patterns
        for pattern in question_context_patterns:
            if re.search(pattern, response_lower):
                return True
        
        return False

    def _development_loop(self):
        """Il vero motore autonomo che gira in background, con detection del completamento."""
        
        # CRITICAL FIX: Controlla se ci sono file esistenti per primo feedback intelligente
        try:
            import os
            files_in_dir = []
            if os.path.exists(self.working_directory):
                for root, dirs, files in os.walk(self.working_directory):
                    for file in files:
                        rel_path = os.path.relpath(os.path.join(root, file), self.working_directory)
                        files_in_dir.append(rel_path)
            
            if files_in_dir:
                user_feedback = f"CRITICAL: La directory contiene già questi file: {', '.join(files_in_dir)}. NON dire 'progetto già completo'. ANALIZZA il contenuto di questi file e confrontali con i requisiti del PRP attuale. Se NON corrispondono, avvisa l'utente del conflitto e chiedi come procedere. Se corrispondono, verifica che funzionino come da specifiche."
            else:
                user_feedback = "Inizia il lavoro basandoti sul PRP. La directory è vuota."
        except Exception:
            user_feedback = "Inizia il lavoro basandoti sul PRP."
        
        # Track consecutive errors to prevent infinite loops
        consecutive_errors = 0
        last_error_message = ""
        
        while self.is_running:
            self.total_cycles += 1
            
            # Failsafe: stop dopo troppi cicli
            if self.total_cycles > self.max_total_cycles:
                self.output_queue.put(f"[INFO]🛑 Interrotto automaticamente dopo {self.max_total_cycles} cicli per evitare loop infinito.")
                self.is_running = False
                break
            
            # Failsafe: stop after too many consecutive errors
            if consecutive_errors >= 3:
                self.output_queue.put(f"[INFO]🛑 Interrotto dopo {consecutive_errors} errori consecutivi. Possibile problema con Claude CLI.")
                self.is_running = False
                break
            
            # Esegui un passo di sviluppo e cattura la risposta
            step_response = ""
            step_had_error = False
            
            for chunk in self.handle_development_step(user_feedback):
                self.output_queue.put(chunk)
                step_response += str(chunk)
                
                # Check for errors in real-time
                if "**ERRORE" in str(chunk) or "[STDERR]" in str(chunk):
                    step_had_error = True
            
            # Update error tracking
            if step_had_error:
                current_error = step_response[-200:] if len(step_response) > 200 else step_response
                if current_error == last_error_message:
                    consecutive_errors += 1
                    debug_logger.warning(f"Consecutive error #{consecutive_errors}: Same error repeating")
                else:
                    consecutive_errors = 1
                    last_error_message = current_error
                    debug_logger.info(f"New error detected, consecutive count reset to 1")
            else:
                consecutive_errors = 0
                last_error_message = ""
            
            # FIRST: Rileva se Claude sta facendo domande all'utente
            user_question_detected = self._detect_user_question(step_response)
            if user_question_detected:
                debug_logger.info(f"USER QUESTION DETECTED - Pausing autonomous cycle")
                self.output_queue.put("[INFO]⏸️  Claude ha fatto una domanda. Ciclo autonomo in pausa - aspetto la tua risposta.")
                self.output_queue.put("[STREAM_END]")  # CRITICAL: Sblocca UI
                self.is_running = False
                break
            
            # SECOND: Rileva se il progetto è completato
            completion_detected = self._detect_project_completion(step_response)
            debug_logger.info(f"Cycle {self.total_cycles}: Completion detection = {completion_detected}")
            debug_logger.info(f"Response snippet for analysis: {step_response[:300]}...")
            
            if completion_detected:
                self.consecutive_completion_signals += 1
                debug_logger.info(f"Consecutive completion signals: {self.consecutive_completion_signals}/{self.max_consecutive_completions}")
                self.output_queue.put(f"[INFO]🔍 Rilevato segnale di completamento ({self.consecutive_completion_signals}/{self.max_consecutive_completions})")
                
                if self.consecutive_completion_signals >= self.max_consecutive_completions:
                    debug_logger.info(f"STOPPING LOOP: Reached max consecutive completions")
                    self.output_queue.put("[INFO]✅ Progetto completato! Ciclo di sviluppo terminato automaticamente.")
                    self._cleanup_checkpoint()  # Cleanup su completion successful
                    self.is_running = False
                    break
            else:
                # Reset counter se non rileva completamento
                if self.consecutive_completion_signals > 0:
                    debug_logger.info(f"Resetting completion counter from {self.consecutive_completion_signals} to 0")
                self.consecutive_completion_signals = 0
            
            # Resetta il feedback per il prossimo ciclo automatico
            user_feedback = None 
            
            # Se is_running è diventato False durante il passo, esci
            if not self.is_running:
                break
            
            time.sleep(2) # Piccola pausa per dare respiro al sistema
        
        self.output_queue.put("[INFO]Ciclo di sviluppo in pausa.")
        # Mettiamo un segnale di fine per chiudere lo stream se necessario
        self.output_queue.put(None)

    def _development_loop_with_feedback(self, initial_feedback):
        """Ciclo di sviluppo che inizia con feedback specifico dall'utente."""
        user_feedback = initial_feedback
        
        # Try to load checkpoint for resume capability
        checkpoint_loaded = self._load_checkpoint()
        if checkpoint_loaded:
            self.output_queue.put("[INFO]📋 Checkpoint trovato - riprendo da operazioni precedenti")
        
        while self.is_running:
            self.total_cycles += 1
            
            # Salva checkpoint ogni 2-3 operazioni per resume capability
            if self.total_cycles % 3 == 0:
                self._save_checkpoint()
            
            # Failsafe: stop dopo troppi cicli
            if self.total_cycles > self.max_total_cycles:
                self.output_queue.put(f"[INFO]🛑 Interrotto automaticamente dopo {self.max_total_cycles} cicli per evitare loop infinito.")
                self._cleanup_checkpoint()  # Cleanup su stop
                self.is_running = False
                break
            
            # Esegui un passo di sviluppo e cattura la risposta
            step_response = ""
            for chunk in self.handle_development_step(user_feedback):
                self.output_queue.put(chunk)
                step_response += str(chunk)
            
            # FIRST: Rileva se Claude sta facendo domande all'utente
            user_question_detected = self._detect_user_question(step_response)
            if user_question_detected:
                debug_logger.info(f"USER QUESTION DETECTED - Pausing autonomous cycle")
                self.output_queue.put("[INFO]⏸️  Claude ha fatto una domanda. Ciclo autonomo in pausa - aspetto la tua risposta.")
                self.output_queue.put("[STREAM_END]")  # CRITICAL: Sblocca UI
                self.is_running = False
                break
            
            # SECOND: Rileva se il progetto è completato
            completion_detected = self._detect_project_completion(step_response)
            debug_logger.info(f"Cycle {self.total_cycles}: Completion detection = {completion_detected}")
            debug_logger.info(f"Response snippet for analysis: {step_response[:300]}...")
            
            if completion_detected:
                self.consecutive_completion_signals += 1
                debug_logger.info(f"Consecutive completion signals: {self.consecutive_completion_signals}/{self.max_consecutive_completions}")
                self.output_queue.put(f"[INFO]🔍 Rilevato segnale di completamento ({self.consecutive_completion_signals}/{self.max_consecutive_completions})")
                
                if self.consecutive_completion_signals >= self.max_consecutive_completions:
                    debug_logger.info(f"STOPPING LOOP: Reached max consecutive completions")
                    self.output_queue.put("[INFO]✅ Progetto completato! Ciclo di sviluppo terminato automaticamente.")
                    self._cleanup_checkpoint()  # Cleanup su completion successful
                    self.is_running = False
                    break
            else:
                # Reset counter se non rileva completamento
                if self.consecutive_completion_signals > 0:
                    debug_logger.info(f"Resetting completion counter from {self.consecutive_completion_signals} to 0")
                self.consecutive_completion_signals = 0
            
            # Resetta il feedback per il prossimo ciclo automatico
            user_feedback = None 
            
            # Se is_running è diventato False durante il passo, esci
            if not self.is_running:
                break
            
            time.sleep(2) # Piccola pausa per dare respiro al sistema
        
        self.output_queue.put("[INFO]Ciclo di sviluppo in pausa.")
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

    def _create_batch_operations_prompt(self, operations_list):
        """
        Crea un prompt ottimizzato per eseguire multiple operazioni in batch.
        Riduce il numero di chiamate API raggruppando operazioni simili.
        """
        if len(operations_list) <= 1:
            return operations_list[0] if operations_list else ""
            
        debug_logger.info(f"Creating batch prompt for {len(operations_list)} operations")
        
        batch_prompt = f"""
BATCH OPERATIONS MODE: Esegui le seguenti operazioni in sequenza efficiente.
Per ogni operazione, fornisci una breve conferma di completamento.

OPERAZIONI DA ESEGUIRE:
"""
        for i, operation in enumerate(operations_list, 1):
            batch_prompt += f"\n{i}. {operation}"
        
        batch_prompt += f"""

ISTRUZIONI BATCH:
- Esegui tutte le operazioni sopra in sequenza
- Segnala brevemente il completamento di ogni operazione
- Se un'operazione fallisce, continua con le successive
- Alla fine fornisci un riepilogo di ciò che è stato completato
"""
        
        return batch_prompt

    def _save_checkpoint(self):
        """
        Salva un checkpoint dello stato corrente per permettere resume operations.
        """
        try:
            checkpoint_data = {
                "timestamp": datetime.now().isoformat(),
                "session_id": self.session_id,
                "mode": self.mode,
                "status": self.status.value if hasattr(self.status, 'value') else str(self.status),
                "working_directory": self.working_directory,
                "total_cycles": self.total_cycles,
                "consecutive_completion_signals": self.consecutive_completion_signals,
                "tdd_mode": self.tdd_mode,
                "project_plan": self.project_plan,
                "conversation_history": self.conversation_history[-10:],  # Solo ultime 10 entries
                "architect_llm": self.architect_llm,
                "current_architect": self.current_architect,
                "fallback_active": self.fallback_active
            }
            
            checkpoint_path = os.path.join(os.path.dirname(self.working_directory or "."), f"checkpoint_{self.session_id}.json")
            with open(checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
                
            debug_logger.info(f"Checkpoint saved: {checkpoint_path}")
            return True
            
        except Exception as e:
            debug_logger.error(f"Failed to save checkpoint: {e}")
            return False

    def _load_checkpoint(self, checkpoint_path=None):
        """
        Carica un checkpoint salvato per resume operations.
        """
        try:
            if not checkpoint_path:
                checkpoint_path = os.path.join(os.path.dirname(self.working_directory or "."), f"checkpoint_{self.session_id}.json")
            
            if not os.path.exists(checkpoint_path):
                debug_logger.info("No checkpoint found")
                return False
                
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
            
            # Restore state from checkpoint
            self.total_cycles = checkpoint_data.get("total_cycles", 0)
            self.consecutive_completion_signals = checkpoint_data.get("consecutive_completion_signals", 0)
            self.tdd_mode = checkpoint_data.get("tdd_mode", True)
            self.architect_llm = checkpoint_data.get("architect_llm", "gemini")
            self.current_architect = checkpoint_data.get("current_architect", self.architect_llm)
            self.fallback_active = checkpoint_data.get("fallback_active", False)
            
            debug_logger.info(f"Checkpoint loaded from: {checkpoint_path}")
            debug_logger.info(f"Resumed at cycle: {self.total_cycles}")
            
            return True
            
        except Exception as e:
            debug_logger.error(f"Failed to load checkpoint: {e}")
            return False

    def _cleanup_checkpoint(self):
        """
        Rimuove il checkpoint dopo completamento successful.
        """
        try:
            checkpoint_path = os.path.join(os.path.dirname(self.working_directory or "."), f"checkpoint_{self.session_id}.json")
            if os.path.exists(checkpoint_path):
                os.remove(checkpoint_path)
                debug_logger.info("Checkpoint cleaned up")
        except Exception as e:
            debug_logger.error(f"Failed to cleanup checkpoint: {e}")

    def handle_development_step(self, user_feedback=None):
        """Esegue UN singolo passo del ciclo di sviluppo."""
        if not self.working_directory:
            yield PROMPTS[self.lang]["error_no_working_dir_set"]
            return
        
        try:
            # Preparare il prompt per l'architetto con metodologia appropriata
            if self.tdd_mode:
                # MODALITÀ TDD: Cicli Red-Green-Refactor
                methodology_prompt = (
                    f"Sei l'ARCHITETTO TDD per questo progetto. Segui rigorosamente il ciclo Red-Green-Refactor.\n\n"
                    f"**METODOLOGIA TDD:**\n"
                    f"1. **RED PHASE:** Crea test che falliscono\n"
                    f"2. **GREEN PHASE:** Implementa codice minimo per far passare i test\n"
                    f"3. **REFACTOR PHASE:** Migliora il codice mantenendo i test verdi\n\n"
                    f"**ANALISI FASE TDD ATTUALE:**\n"
                    f"5. **Fase TDD Attuale:** RED (test falliti), GREEN (implementare), o REFACTOR (migliorare)\n"
                )
            else:
                # MODALITÀ CLASSICA: Sviluppo diretto senza TDD
                # Check if this is a simple static web app (HTML/CSS/JS only)
                is_simple_static = False
                if self.project_plan:
                    plan_lower = self.project_plan.lower()
                    static_indicators = ["vanilla js", "html", "css", "static", "browser", "file statici"]
                    complex_indicators = ["npm", "node", "server", "api", "database", "framework", "webpack", "build"]
                    
                    has_static = any(indicator in plan_lower for indicator in static_indicators)
                    has_complex = any(indicator in plan_lower for indicator in complex_indicators)
                    
                    is_simple_static = has_static and not has_complex
                
                if is_simple_static:
                    methodology_prompt = (
                        f"Sei l'ARCHITETTO per un progetto WEB STATICO semplice. Sviluppo RAPIDO e DIRETTO.\n\n"
                        f"**METODOLOGIA STATIC-FIRST:**\n"
                        f"1. **IMPLEMENTAZIONE DIRETTA:** Crea i file HTML/CSS/JS immediatamente\n"
                        f"2. **TUTTO IN UNA VOLTA:** Non frammentare in micro-task\n"
                        f"3. **NO SETUP:** Evita npm, testing framework, build tools\n"
                        f"4. **FILE READY:** Codice immediatamente utilizzabile nel browser\n\n"
                        f"**PRIORITÀ ASSOLUTA:**\n"
                        f"- Crea tutti i file principali in 1-2 iterazioni MAX\n"
                        f"- Codice funzionante subito, refinement dopo\n"
                        f"- NO testing setup per progetti statici semplici\n"
                    )
                else:
                    methodology_prompt = (
                        f"Sei l'ARCHITETTO per questo progetto. Segui un approccio di sviluppo diretto e pragmatico.\n\n"
                        f"**METODOLOGIA CLASSICA:**\n"
                        f"1. **ANALISI:** Comprendi il requirement\n"
                        f"2. **IMPLEMENTAZIONE:** Crea direttamente il codice funzionante\n"
                        f"3. **VERIFICA:** Testa manualmente o con esempi semplici\n"
                        f"4. **ITERAZIONE:** Migliora basandoti sui feedback\n\n"
                        f"**FOCUS SVILUPPO CLASSICO:**\n"
                        f"- Priorità su funzionalità rapidamente utilizzabili\n"
                        f"- Codice semplice e diretto\n"
                        f"- Testing opzionale o di verifica finale\n"
                    )
            
            # OTTIMIZZAZIONE COSTI: Prompt condensato con solo info essenziali
            # Include solo ultimi 3 elementi della cronologia invece di tutta
            recent_history = self.conversation_history[-3:] if len(self.conversation_history) > 3 else self.conversation_history
            history_summary = "\n".join(recent_history) if recent_history else "Inizio progetto"
            
            # Piano progetto: solo summary se troppo lungo
            plan_summary = self.project_plan[:300] + "..." if self.project_plan and len(self.project_plan) > 300 else self.project_plan
            
            dev_prompt_context = (
                methodology_prompt +
                f"**PIANO:** {plan_summary}\n\n"
                f"**STORIA RECENTE:** {history_summary}\n\n"
                f"**DIRECTORY:** {self.working_directory}\n"
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

            # ISTRUZIONI SPECIFICHE CON DECISION TREE ADATTIVO (OTTIMIZZATO)
            completion_instruction = (
                "IMPORTANTE: Quando il task è completato, aggiungi ESATTAMENTE questa keyword: [PROMETHEUS_COMPLETE]\n"
                "Questa keyword ferma automaticamente il ciclo di sviluppo.\n\n"
            )
            
            if is_simple_static and not self.tdd_mode:
                dev_prompt_instruction = (
                    completion_instruction +
                    "STATICO: Directory vuota→crea HTML/CSS/JS. File esistenti→completa. Modifica fatta→aggiungi [PROMETHEUS_COMPLETE].\n"
                    "NO npm, NO server, NO test framework. Output: comando diretto o testo + [PROMETHEUS_COMPLETE].\n"
                )
            else:
                dev_prompt_instruction = (
                    completion_instruction +
                    "LOGICA:\n"
                    "1. Vuota→setup framework\n"
                    "2. File esistenti→analizza vs piano\n" 
                    "3. TDD: test falliti→implementa, test passano→nuovo test\n"
                    "4. Errori→fix first\n"
                    "5. Progetto completo→aggiungi [PROMETHEUS_COMPLETE]\n\n"
                    "Output: comando shell o prompt Claude specifico. NO spiegazioni.\n"
                )
            
            full_dev_prompt = dev_prompt_context + dev_prompt_instruction

            # Comunica l'inizio dell'iterazione (specialmente importante per la prima)
            yield "⚡ **Comando in esecuzione**\n\n"
            
            yield "[THINKING]" # Segnale pulito per l'animazione
            
            # Ottieni il prossimo comando/prompt dall'architetto selezionato
            gemini_prompt_for_claude = self._get_architect_response(full_dev_prompt)
            
            self.conversation_history.append(f"[Prometheus (to Claude)]: {gemini_prompt_for_claude}")
            
            yield f"[CLAUDE_PROMPT]{gemini_prompt_for_claude}" # Segnale con il prompt
            
            # LOG: Prometheus sending command to Claude CLI
            start_claude_time = time.time()
            log_prompt_interaction(
                phase="DEVELOPMENT",
                source="PROMETHEUS",
                target="CLAUDE_CLI", 
                prompt_text=gemini_prompt_for_claude,
                response_text="",
                timing_ms=0
            )
            
            # Esecuzione con Popen
            command_list = ["claude", "-p", "--dangerously-skip-permissions", gemini_prompt_for_claude]
            
            # ENHANCED DEBUG: Log full execution context
            debug_logger.info(f"=== CLAUDE CLI EXECUTION DEBUG ===")
            debug_logger.info(f"Command: {' '.join(command_list)}")
            debug_logger.info(f"Working directory: {self.working_directory}")
            debug_logger.info(f"Current working directory: {os.getcwd()}")
            debug_logger.info(f"Prompt length: {len(gemini_prompt_for_claude)} chars")
            debug_logger.info(f"Files in working directory: {os.listdir(self.working_directory) if os.path.exists(self.working_directory) else 'DIR_NOT_EXISTS'}")
            debug_logger.info(f"=====================================")
            
            process = subprocess.Popen(
                command_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                cwd=self.working_directory
            )
            
            debug_logger.info(f"subprocess.Popen started with pid: {process.pid}")
            
            # Track if we got any meaningful output
            has_stdout_output = False
            has_stderr_output = False

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
                            has_stdout_output = True
                            debug_logger.info(f"STDOUT: {line.strip()}")
                            yield line
                            full_claude_output += line
                    if fd == process.stderr.fileno():
                        line = process.stderr.readline()
                        if line:
                            has_stderr_output = True
                            debug_logger.error(f"STDERR: {line.strip()}")
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
                has_stdout_output = True
                debug_logger.info(f"FINAL STDOUT: {stdout.strip()}")
                yield stdout
                full_claude_output += stdout
            if stderr:
                has_stderr_output = True
                debug_logger.error(f"FINAL STDERR: {stderr.strip()}")
                stderr_final = f"[STDERR]: {stderr}"
                yield stderr_final
                full_claude_output += stderr_final

            # Get process exit code
            exit_code = process.returncode
            debug_logger.info(f"Claude CLI process exit code: {exit_code}")
            
            # ENHANCED ERROR DETECTION
            if exit_code != 0 or not has_stdout_output or "error" in full_claude_output.lower():
                error_details = []
                if exit_code != 0:
                    error_details.append(f"Exit code: {exit_code}")
                if has_stderr_output:
                    error_details.append("Stderr output present")
                if not has_stdout_output:
                    error_details.append("No stdout output")
                
                debug_logger.error(f"Claude CLI FAILED: {'; '.join(error_details)}")
                
                # Instead of generic "Execution error", provide specific details
                if has_stderr_output and stderr:
                    yield f"\n\n**ERRORE SPECIFICO CLAUDE CLI:** {stderr.strip()}"
                elif exit_code != 0:
                    yield f"\n\n**ERRORE CLAUDE CLI:** Processo terminato con codice {exit_code}. Comando: {' '.join(command_list[:3])}..."
                else:
                    yield f"\n\n**ERRORE CLAUDE CLI:** Nessun output ricevuto. Verificare installazione e permessi."
            
            # Segnala completamento del ciclo
            if self.lang == 'it':
                yield "\n\n[CYCLE_COMPLETE]🔄 **Passo completato.** Il ciclo continua autonomamente..."
            else:
                yield "\n\n[CYCLE_COMPLETE]🔄 **Step completed.** The cycle continues autonomously..."

            # LOG: Response from Claude CLI
            claude_elapsed_ms = int((time.time() - start_claude_time) * 1000)
            log_prompt_interaction(
                phase="DEVELOPMENT",
                source="CLAUDE_CLI",
                target="PROMETHEUS",
                prompt_text="",
                response_text=full_claude_output,
                timing_ms=claude_elapsed_ms
            )
            
            self.conversation_history.append(f"[Claude (Output)]: {full_claude_output}")
            self.save_state(verbose=False)  # Salvataggio silenzioso durante sviluppo automatico
            
        except Exception as e:
            yield f"\n\n**ERRORE CRITICO:** {e}"
