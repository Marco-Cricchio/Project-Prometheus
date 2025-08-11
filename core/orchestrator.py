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
import resource
import platform

# Safe import of psutil with fallback
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    debug_logger = logging.getLogger('prometheus_debug')
    debug_logger.warning("psutil not available - system monitoring will be limited")

# Setup debug logging to file in logs directory
debug_logger = logging.getLogger('prometheus_debug')
debug_logger.setLevel(logging.DEBUG)
log_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs', 'prometheus_debug.log')
# Ensure logs directory exists
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
debug_handler = logging.FileHandler(log_file_path)
debug_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
debug_handler.setFormatter(debug_formatter)
debug_logger.addHandler(debug_handler)

# Setup PROMPT ANALYSIS logger - separate file for performance analysis
prompt_logger = logging.getLogger('prometheus_prompts')
prompt_logger.setLevel(logging.INFO)
prompt_log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs', 'prometheus_prompts.log')
# Ensure logs directory exists
os.makedirs(os.path.dirname(prompt_log_path), exist_ok=True)
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

# User Communication System for better UX during development
class UserCommunicator:
    """Translates technical operations into user-friendly streaming messages"""
    
    def __init__(self, lang='it'):
        self.lang = lang
        self.messages = {
            'it': {
                'analyzing_response': "🔍 Sto analizzando cosa fare dopo...",
                'creating_file': "📄 Sto creando il file: {}",
                'updating_file': "✏️ Sto aggiornando il file: {}",
                'installing_deps': "📦 Sto installando le dipendenze...",
                'running_tests': "🧪 Esecuzione test in corso...",
                'building_project': "🔨 Compilazione del progetto...",
                'starting_server': "🚀 Avviando il server di sviluppo...",
                'fixing_error': "🔧 Sto risolvendo un errore: {}",
                'thinking': "💭 Sto pensando alla prossima operazione...",
                'almost_done': "🎯 Quasi finito! Ultimi dettagli in corso...",
                'completed_step': "✅ Completato: {}",
                'working_on': "⚡ Sto lavorando su: {}",
                'pause_question': "❓ Ho una domanda per te - sviluppo in pausa",
                'resuming': "▶️ Riprendo lo sviluppo con le tue indicazioni...",
                'optimizing': "⚡ Ottimizzazione in corso...",
                'verifying': "🔍 Verifica finale del progetto...",
                'preparing': "📋 Preparando l'ambiente di sviluppo..."
            },
            'en': {
                'analyzing_response': "🔍 Analyzing next steps...",
                'creating_file': "📄 Creating file: {}",
                'updating_file': "✏️ Updating file: {}",
                'installing_deps': "📦 Installing dependencies...",
                'running_tests': "🧪 Running tests...",
                'building_project': "🔨 Building project...",
                'starting_server': "🚀 Starting development server...",
                'fixing_error': "🔧 Fixing error: {}",
                'thinking': "💭 Thinking about next operation...",
                'almost_done': "🎯 Almost done! Final touches...",
                'completed_step': "✅ Completed: {}",
                'working_on': "⚡ Working on: {}",
                'pause_question': "❓ I have a question for you - development paused",
                'resuming': "▶️ Resuming development with your guidance...",
                'optimizing': "⚡ Optimizing...",
                'verifying': "🔍 Final project verification...",
                'preparing': "📋 Preparing development environment..."
            }
        }
    
    def extract_activity_from_ai_response(self, response_text):
        """Extract key activities from AI response for user communication"""
        if not response_text:
            return []
        
        activities = []
        response_lower = response_text.lower()
        
        # File operations
        if any(word in response_lower for word in ['creating', 'creando', 'create', 'crea']):
            files_mentioned = self._extract_file_names(response_text)
            for file in files_mentioned:
                activities.append(('creating_file', file))
        
        if any(word in response_lower for word in ['updating', 'aggiornando', 'modifying', 'modificando']):
            files_mentioned = self._extract_file_names(response_text)
            for file in files_mentioned:
                activities.append(('updating_file', file))
        
        # Dependencies and setup
        if any(word in response_lower for word in ['npm install', 'pip install', 'installing', 'installando']):
            activities.append(('installing_deps', ''))
        
        # Testing and building
        if any(word in response_lower for word in ['test', 'testing', 'jest']):
            activities.append(('running_tests', ''))
        
        if any(word in response_lower for word in ['build', 'compile', 'building']):
            activities.append(('building_project', ''))
        
        # Server operations
        if any(word in response_lower for word in ['server', 'localhost', 'port', 'running on']):
            activities.append(('starting_server', ''))
        
        # Error handling
        if any(word in response_lower for word in ['error', 'errore', 'fix', 'fixing']):
            error_context = self._extract_error_context(response_text)
            activities.append(('fixing_error', error_context))
        
        return activities
    
    def _extract_file_names(self, text):
        """Extract file names from AI response"""
        import re
        # Common file patterns
        patterns = [
            r'`([^`]+\.[a-zA-Z]{1,4})`',  # Files in backticks
            r'"([^"]+\.[a-zA-Z]{1,4})"',  # Files in quotes
            r'([a-zA-Z0-9_.-]+\.[a-zA-Z]{1,4})',  # General file pattern
        ]
        
        files = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            files.extend(matches)
        
        # Filter common file extensions and limit to first 3
        common_extensions = ['.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.json', '.py', '.md']
        relevant_files = []
        for file in files:
            if any(file.endswith(ext) for ext in common_extensions):
                relevant_files.append(file)
                if len(relevant_files) >= 3:  # Limit to avoid spam
                    break
        
        return relevant_files
    
    def _extract_error_context(self, text):
        """Extract brief error context"""
        # Look for common error indicators
        lines = text.split('\n')
        for line in lines:
            line_lower = line.lower()
            if any(word in line_lower for word in ['error', 'errore', 'failed', 'problem']):
                return line.strip()[:100]  # First 100 chars
        return ""
    
    def generate_progress_message(self, activity_type, context=""):
        """Generate user-friendly message for an activity"""
        messages = self.messages[self.lang]
        
        if activity_type in messages:
            if context:
                return messages[activity_type].format(context)
            else:
                return messages[activity_type]
        
        # Fallback
        if self.lang == 'it':
            return f"⚡ Operazione in corso: {activity_type}..."
        else:
            return f"⚡ Working on: {activity_type}..."
    
    def should_stream_thinking(self):
        """Determine if we should show a thinking message to keep user engaged"""
        import random
        thinking_messages = [
            self.messages[self.lang]['thinking'],
            self.messages[self.lang]['analyzing_response'],
            self.messages[self.lang]['preparing']
        ]
        return random.choice(thinking_messages)

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


class SystemResourceMonitor:
    """Monitor di risorse sistema per diagnosticare timeout e performance issues."""
    
    def __init__(self):
        self.monitoring_active = False
        self.resource_snapshots = []
        
    def start_monitoring(self, operation_name="unknown"):
        """Avvia il monitoraggio risorse per un'operazione."""
        self.monitoring_active = True
        self.operation_name = operation_name
        self.start_time = time.time()
        
        # Snapshot iniziale
        initial_snapshot = self._capture_system_snapshot("start")
        self.resource_snapshots = [initial_snapshot]
        
        debug_logger.info(f"🔍 RESOURCE MONITORING START: {operation_name}")
        debug_logger.info(f"🖥️  Initial State: CPU={initial_snapshot['cpu_percent']}% | "
                         f"Memory={initial_snapshot['memory_percent']}% | "
                         f"Available Memory={initial_snapshot['memory_available_gb']:.1f}GB")
        
        return initial_snapshot
    
    def capture_periodic_snapshot(self):
        """Cattura snapshot periodico durante l'operazione."""
        if not self.monitoring_active:
            return None
            
        snapshot = self._capture_system_snapshot("periodic")
        self.resource_snapshots.append(snapshot)
        
        elapsed = time.time() - self.start_time
        debug_logger.debug(f"📊 Resource Snapshot @{elapsed:.1f}s: "
                          f"CPU={snapshot['cpu_percent']}% | "
                          f"Memory={snapshot['memory_percent']}%")
        
        return snapshot
    
    def stop_monitoring(self, success=True):
        """Ferma il monitoraggio e genera report finale."""
        if not self.monitoring_active:
            return None
            
        # Snapshot finale
        final_snapshot = self._capture_system_snapshot("end")
        self.resource_snapshots.append(final_snapshot)
        
        duration = time.time() - self.start_time
        self.monitoring_active = False
        
        # Genera report
        report = self._generate_resource_report(duration, success)
        
        debug_logger.info(f"🔍 RESOURCE MONITORING END: {self.operation_name}")
        debug_logger.info(f"📊 Final State: CPU={final_snapshot['cpu_percent']}% | "
                         f"Memory={final_snapshot['memory_percent']}% | "
                         f"Duration={duration:.1f}s | Success={success}")
        debug_logger.info(f"📋 Resource Report: {report['summary']}")
        
        return report
    
    def _capture_system_snapshot(self, stage):
        """Cattura uno snapshot completo dello stato del sistema."""
        try:
            if not PSUTIL_AVAILABLE:
                return {
                    'timestamp': time.time(),
                    'stage': stage,
                    'error': 'psutil not available',
                    'fallback_info': {
                        'platform': platform.system(),
                        'cpu_count': os.cpu_count()
                    }
                }
            
            # CPU e Memory
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            
            # Disk I/O
            disk_io = psutil.disk_io_counters()
            
            # Network I/O
            network_io = psutil.net_io_counters()
            
            # Process info
            current_process = psutil.Process()
            
            # Load average (Unix-like systems)
            load_avg = None
            if hasattr(os, 'getloadavg'):
                try:
                    load_avg = os.getloadavg()
                except:
                    pass
            
            snapshot = {
                'timestamp': time.time(),
                'stage': stage,
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_gb': memory.available / (1024**3),
                'memory_used_gb': memory.used / (1024**3),
                'disk_read_mb': disk_io.read_bytes / (1024**2) if disk_io else 0,
                'disk_write_mb': disk_io.write_bytes / (1024**2) if disk_io else 0,
                'network_sent_mb': network_io.bytes_sent / (1024**2) if network_io else 0,
                'network_recv_mb': network_io.bytes_recv / (1024**2) if network_io else 0,
                'process_memory_mb': current_process.memory_info().rss / (1024**2),
                'process_cpu_percent': current_process.cpu_percent(),
                'load_average': load_avg,
                'platform': platform.system(),
            }
            
            return snapshot
            
        except Exception as e:
            debug_logger.error(f"Error capturing system snapshot: {e}")
            return {
                'timestamp': time.time(),
                'stage': stage,
                'error': str(e)
            }
    
    def _generate_resource_report(self, duration, success):
        """Genera report dettagliato dell'utilizzo risorse."""
        if len(self.resource_snapshots) < 2:
            return {'summary': 'Insufficient data for report'}
        
        start_snapshot = self.resource_snapshots[0]
        end_snapshot = self.resource_snapshots[-1]
        
        # Calcola differenze
        cpu_avg = sum(s.get('cpu_percent', 0) for s in self.resource_snapshots) / len(self.resource_snapshots)
        memory_avg = sum(s.get('memory_percent', 0) for s in self.resource_snapshots) / len(self.resource_snapshots)
        
        # Peak usage
        cpu_peak = max(s.get('cpu_percent', 0) for s in self.resource_snapshots)
        memory_peak = max(s.get('memory_percent', 0) for s in self.resource_snapshots)
        
        # Classificazione performance
        performance_class = "🟢 OPTIMAL"
        if cpu_avg > 80 or memory_avg > 85:
            performance_class = "🔴 HIGH LOAD"
        elif cpu_avg > 60 or memory_avg > 70:
            performance_class = "🟡 MODERATE LOAD"
        
        # Identificazione possibili bottleneck
        bottlenecks = []
        if cpu_peak > 90:
            bottlenecks.append("CPU overload")
        if memory_peak > 90:
            bottlenecks.append("Memory pressure")
        if duration > 60 and cpu_avg < 30:
            bottlenecks.append("Possible I/O wait")
        
        summary = f"{performance_class} | CPU avg:{cpu_avg:.1f}% peak:{cpu_peak:.1f}% | " \
                 f"Memory avg:{memory_avg:.1f}% peak:{memory_peak:.1f}%"
        
        if bottlenecks:
            summary += f" | Bottlenecks: {', '.join(bottlenecks)}"
        
        return {
            'summary': summary,
            'duration': duration,
            'cpu_average': cpu_avg,
            'cpu_peak': cpu_peak,
            'memory_average': memory_avg,
            'memory_peak': memory_peak,
            'performance_class': performance_class,
            'bottlenecks': bottlenecks,
            'success': success,
            'snapshots_count': len(self.resource_snapshots)
        }


class PerformanceTracker:
    """Traccia metriche di performance in tempo reale per ottimizzare l'esperienza utente."""
    
    def __init__(self):
        self.session_start = time.time()
        self.operations_count = 0
        self.total_tokens_processed = 0
        self.total_response_time = 0
        self.error_count = 0
        self.retry_count = 0
        self.longest_operation = 0
        self.shortest_operation = float('inf')
        
    def record_operation(self, duration_seconds, tokens_estimate=0, had_error=False, was_retry=False):
        """Registra una operazione completata con le sue metriche."""
        self.operations_count += 1
        self.total_response_time += duration_seconds
        self.total_tokens_processed += tokens_estimate
        
        if had_error:
            self.error_count += 1
        if was_retry:
            self.retry_count += 1
            
        self.longest_operation = max(self.longest_operation, duration_seconds)
        if duration_seconds > 0:
            self.shortest_operation = min(self.shortest_operation, duration_seconds)
    
    def get_session_summary(self):
        """Restituisce un sommario elegante delle performance della sessione."""
        if self.operations_count == 0:
            return "📊 **Performance**: Sessione appena iniziata"
        
        session_duration = time.time() - self.session_start
        avg_response_time = self.total_response_time / self.operations_count
        success_rate = ((self.operations_count - self.error_count) / self.operations_count) * 100
        
        summary = f"📊 **Performance Sessione**: "
        summary += f"{self.operations_count} ops"
        summary += f" | {avg_response_time:.1f}s avg"
        summary += f" | {success_rate:.0f}% success"
        
        if self.total_tokens_processed > 0:
            tokens_per_min = (self.total_tokens_processed / session_duration) * 60
            summary += f" | ~{tokens_per_min:.0f} tokens/min"
            
        return summary
    
    def get_efficiency_rating(self):
        """Calcola un rating di efficienza del sistema (1-5 stelle)."""
        if self.operations_count == 0:
            return "⭐⭐⭐ **Efficienza**: In attesa di dati"
        
        avg_response_time = self.total_response_time / self.operations_count
        success_rate = ((self.operations_count - self.error_count) / self.operations_count) * 100
        
        # Algoritmo di rating basato su performance reali
        stars = 5
        if avg_response_time > 60:
            stars -= 1
        if avg_response_time > 120:
            stars -= 1
        if success_rate < 90:
            stars -= 1
        if success_rate < 70:
            stars -= 1
        if self.retry_count > self.operations_count * 0.3:
            stars -= 1
            
        stars = max(1, stars)
        star_display = "⭐" * stars + "☆" * (5 - stars)
        
        return f"{star_display} **Efficienza Sistema**"


class PromptOptimizer:
    """Sistema avanzato di ottimizzazione prompt con controllo dimensioni e compression intelligente."""
    
    def __init__(self):
        self.common_patterns = {}
        self.template_cache = {}
        self.max_safe_size = 5000  # Soglia per attivazione compression aggressiva
        self.critical_size = 7000  # Soglia per emergency compression
        
    def optimize_prompt(self, prompt_text, context_type="general", conversation_history=None):
        """
        Sistema di ottimizzazione multi-livello con controllo dimensioni.
        """
        original_length = len(prompt_text)
        
        # LIVELLO 1: Ottimizzazioni standard
        if context_type == "development":
            optimized = self._optimize_development_prompt(prompt_text)
        elif context_type == "brainstorming":
            optimized = self._optimize_brainstorming_prompt(prompt_text)
        elif context_type == "error_recovery":
            optimized = self._optimize_error_prompt(prompt_text)
        else:
            optimized = self._optimize_general_prompt(prompt_text)
        
        # LIVELLO 2: Size control intelligente
        if len(optimized) > self.max_safe_size:
            optimized = self._apply_size_control(optimized, conversation_history)
        
        # LIVELLO 3: Emergency compression per prompt critici
        if len(optimized) > self.critical_size:
            optimized = self._emergency_compression(optimized)
        
        # Log optimization metrics  
        saved_chars = original_length - len(optimized)
        if saved_chars > 0:
            save_percentage = (saved_chars/original_length*100)
            if save_percentage > 5:  # Solo log se risparmio significativo
                debug_logger.info(f"💡 PROMPT OPTIMIZED: {saved_chars} chars saved ({save_percentage:.1f}%)")
        
        return optimized
    
    def _apply_size_control(self, prompt, conversation_history):
        """Applica controllo dimensioni intelligente per prompt grandi."""
        debug_logger.info(f"🎯 SIZE CONTROL: Prompt {len(prompt)} chars > {self.max_safe_size} - applying compression")
        
        # Strategia 1: Rimuovi conversation history ridondante
        if conversation_history and len(conversation_history) > 3:
            # Mantieni solo gli ultimi 2 elementi + primo elemento
            compressed_history = [conversation_history[0]] + conversation_history[-2:]
            compressed_conversation = " ".join([str(item) for item in compressed_history])
            
            # Sostituisci la conversazione completa con quella compressa
            lines = prompt.split('\n')
            new_lines = []
            skip_conversation = False
            
            for line in lines:
                if "conversazione precedente" in line.lower() or "cronologia:" in line.lower():
                    skip_conversation = True
                    new_lines.append(line)
                    new_lines.append(f"CONVERSAZIONE (compressa): {compressed_conversation}")
                elif skip_conversation and line.strip().startswith("USER:") or line.strip().startswith("ASSISTANT:"):
                    continue  # Salta le righe della conversazione originale
                elif skip_conversation and (line.strip() == "" or not line.strip().startswith(("USER:", "ASSISTANT:"))):
                    skip_conversation = False
                    new_lines.append(line)
                elif not skip_conversation:
                    new_lines.append(line)
            
            prompt = '\n'.join(new_lines)
        
        # Strategia 2: Comprimi decision tree se presente
        if "decision tree" in prompt.lower() and len(prompt) > self.max_safe_size:
            prompt = self._compress_decision_tree(prompt)
        
        return prompt
    
    def _emergency_compression(self, prompt):
        """Compression aggressiva per prompt criticamente grandi."""
        debug_logger.info(f"🚨 EMERGENCY COMPRESSION: Prompt {len(prompt)} chars > {self.critical_size}")
        
        # Rimuovi righe non essenziali
        lines = prompt.split('\n')
        essential_lines = []
        
        for line in lines:
            # Mantieni solo righe essenziali
            if any(keyword in line.lower() for keyword in [
                'obiettivo', 'architetto', 'implementa', 'crea', 'sviluppa',
                'requisiti', 'specifiche', 'prometheus_complete', 'working directory'
            ]):
                essential_lines.append(line)
            elif len(line.strip()) < 80 and line.strip():  # Righe corte probabilmente importanti
                essential_lines.append(line)
            elif line.strip().startswith(('**', '##', '-', '1.', '2.', '3.')):  # Headers e liste
                essential_lines.append(line)
        
        compressed = '\n'.join(essential_lines)
        
        # Se ancora troppo grande, taglia ulteriormente
        if len(compressed) > self.critical_size:
            compressed = compressed[:self.critical_size-100] + "\n\n[PROMPT TRUNCATED FOR EFFICIENCY]"
        
        return compressed
    
    def _compress_decision_tree(self, prompt):
        """Comprimi decision tree mantenendo solo logica essenziale."""
        # Sostituisci decision tree dettagliato con versione ultra-compatta
        compressed_tree = """
**DECISION TREE COMPATTO:**
- Directory vuota → Setup progetto base
- File esistenti → Analisi + implementazione mancante  
- Errori → Fix + continua
- Completato → [PROMETHEUS_COMPLETE]
"""
        
        # Trova e sostituisci il decision tree
        lines = prompt.split('\n')
        new_lines = []
        skip_tree = False
        tree_replaced = False
        
        for line in lines:
            if "decision tree" in line.lower() and not tree_replaced:
                new_lines.append(compressed_tree)
                tree_replaced = True
                skip_tree = True
            elif skip_tree and (line.startswith('**') and 'decision' not in line.lower()):
                skip_tree = False
                new_lines.append(line)
            elif not skip_tree:
                new_lines.append(line)
        
        return '\n'.join(new_lines)
    
    def _optimize_development_prompt(self, prompt):
        """Ottimizza prompt di sviluppo riducendo boilerplate."""
        # Rimuovi decision tree ridondante per progetti statici
        if "decision tree" in prompt.lower() and "static" in prompt.lower():
            # Sostituisci decision tree completo con versione compatta
            optimized = prompt.replace(
                "Segui questo decision tree dettagliato per decidere la prossima azione:",
                "Azione: "
            )
            # Rimuovi le righe del decision tree se presenti
            lines = optimized.split('\n')
            filtered_lines = []
            skip_tree = False
            for line in lines:
                if "decision tree" in line.lower() or line.strip().startswith("- Se"):
                    skip_tree = True
                elif skip_tree and line.strip().startswith("**"):
                    skip_tree = False
                    filtered_lines.append(line)
                elif not skip_tree:
                    filtered_lines.append(line)
            return '\n'.join(filtered_lines)
        
        return prompt
    
    def _optimize_brainstorming_prompt(self, prompt):
        """Ottimizza prompt di brainstorming.""" 
        # Rimuovi istruzioni ripetitive
        optimized = prompt.replace(
            "Sii conciso e diretto. Fornisci risposte brevi e mirate. Elabora solo se l'utente te lo chiede esplicitamente.",
            "Sii conciso."
        )
        return optimized
        
    def _optimize_error_prompt(self, prompt):
        """Ottimizza prompt di recovery da errori."""
        # Mantieni solo informazioni essenziali per recovery
        lines = prompt.split('\n')
        essential_lines = []
        for line in lines:
            if any(keyword in line.lower() for keyword in ['error', 'fix', 'recovery', 'problema']):
                essential_lines.append(line)
            elif len(line.strip()) < 50:  # Mantieni righe corte (probabilmente importanti)
                essential_lines.append(line)
        
        return '\n'.join(essential_lines) if essential_lines else prompt
        
    def _optimize_general_prompt(self, prompt):
        """Ottimizzazione generale per tutti i prompt."""
        # Rimuovi spazi multipli e righe vuote eccessive
        optimized = ' '.join(prompt.split())  # Rimuove spazi multipli
        
        # Sostituzioni comuni per ridurre token
        replacements = {
            "che cosa": "cosa",
            "per favore": "prego", 
            "dovrebbe essere": "deve essere",
            "è necessario che": "deve",
            "in modo che": "così che",
            "al fine di": "per",
            "è possibile": "si può"
        }
        
        for old, new in replacements.items():
            optimized = optimized.replace(old, new)
            
        return optimized


class TimeoutPredictor:
    """Sistema di predizione intelligente dei timeout basato su dati reali di performance."""
    
    def __init__(self):
        # Dati calibrati sui log reali di Prometheus
        self.performance_benchmarks = {
            # Formato: (max_chars, expected_time_seconds, risk_level, recommended_timeout)
            1000: {"time": 12, "risk": "LOW", "timeout": 60},
            2000: {"time": 14, "risk": "LOW", "timeout": 60}, 
            3000: {"time": 18, "risk": "MEDIUM", "timeout": 90},
            4000: {"time": 25, "risk": "MEDIUM", "timeout": 120},
            5000: {"time": 35, "risk": "HIGH", "timeout": 150},
            6000: {"time": 50, "risk": "HIGH", "timeout": 180},
            7000: {"time": 70, "risk": "CRITICAL", "timeout": 240},
            8000: {"time": 90, "risk": "CRITICAL", "timeout": 300}
        }
        
    def predict_performance(self, prompt_length):
        """Predice performance basandosi su dimensione prompt."""
        # Trova il benchmark più vicino
        best_match = None
        for threshold in sorted(self.performance_benchmarks.keys()):
            if prompt_length <= threshold:
                best_match = self.performance_benchmarks[threshold]
                break
        
        # Per prompt molto grandi, estrapola
        if not best_match:
            # Crescita lineare oltre 8k chars
            extra_chars = prompt_length - 8000
            base_time = 90
            extra_time = (extra_chars // 1000) * 15  # +15s ogni 1k chars
            
            best_match = {
                "time": base_time + extra_time,
                "risk": "EXTREME",
                "timeout": min(300, base_time + extra_time + 60)  # +60s buffer, max 5min
            }
        
        # Aggiungi buffer di sicurezza basato sul risk level
        safety_multiplier = {
            "LOW": 1.2,
            "MEDIUM": 1.4, 
            "HIGH": 1.6,
            "CRITICAL": 1.8,
            "EXTREME": 2.0
        }
        
        predicted_time = best_match["time"]
        risk_level = best_match["risk"]
        safe_timeout = int(predicted_time * safety_multiplier[risk_level])
        
        # Forza timeout minimi per evitare timeout inutili
        if safe_timeout < best_match["timeout"]:
            safe_timeout = best_match["timeout"]
            
        return {
            "predicted_time": predicted_time,
            "risk_level": risk_level,
            "recommended_timeout": safe_timeout,
            "confidence": "HIGH" if prompt_length <= 8000 else "MEDIUM"
        }
    
    def should_skip_lower_timeouts(self, prompt_length):
        """Determina se saltare timeout più bassi per efficienza."""
        prediction = self.predict_performance(prompt_length)
        
        # Se il prompt è grande, salta direttamente a timeout alto
        if prediction["risk_level"] in ["HIGH", "CRITICAL", "EXTREME"]:
            return True, prediction["recommended_timeout"]
        
        return False, 60  # Usa timeout standard


class ClaudeCLITracer:
    """Sistema di tracing dettagliato per esecuzioni Claude CLI."""
    
    def __init__(self):
        self.execution_traces = []
        
    def start_trace(self, operation_id, prompt_length, timeout, working_dir):
        """Inizia il tracciamento di una esecuzione."""
        trace = {
            'operation_id': operation_id,
            'start_time': time.time(),
            'prompt_length': prompt_length,
            'timeout': timeout,
            'working_dir': working_dir,
            'environment': self._capture_environment(),
            'command_line': None,
            'process_info': None,
            'execution_phases': [],
            'resource_snapshots': [],
            'final_result': None
        }
        self.execution_traces.append(trace)
        
        debug_logger.info(f"🔍 CLAUDE CLI TRACE START: {operation_id}")
        debug_logger.info(f"📋 Environment: {trace['environment']['summary']}")
        
        return trace
    
    def add_execution_phase(self, operation_id, phase_name, details=None):
        """Aggiunge una fase di esecuzione al trace."""
        trace = self._get_trace(operation_id)
        if trace:
            phase = {
                'timestamp': time.time(),
                'phase': phase_name,
                'details': details or {},
                'elapsed_from_start': time.time() - trace['start_time']
            }
            trace['execution_phases'].append(phase)
            
            debug_logger.debug(f"📊 TRACE {operation_id}: {phase_name} @{phase['elapsed_from_start']:.1f}s")
    
    def complete_trace(self, operation_id, success, result_details):
        """Completa il trace con i risultati finali."""
        trace = self._get_trace(operation_id)
        if trace:
            trace['final_result'] = {
                'success': success,
                'duration': time.time() - trace['start_time'],
                'details': result_details
            }
            
            debug_logger.info(f"🔍 CLAUDE CLI TRACE END: {operation_id}")
            debug_logger.info(f"📊 Result: Success={success}, Duration={trace['final_result']['duration']:.2f}s")
            
            # Generate detailed trace summary
            self._log_trace_summary(trace)
            
        return trace
    
    def _get_trace(self, operation_id):
        """Trova trace per ID operazione."""
        for trace in self.execution_traces:
            if trace['operation_id'] == operation_id:
                return trace
        return None
    
    def _capture_environment(self):
        """Cattura informazioni ambiente per diagnostica."""
        try:
            env_info = {
                'python_version': platform.python_version(),
                'platform': platform.platform(),
                'cpu_count': os.cpu_count(),
                'available_memory_gb': psutil.virtual_memory().available / (1024**3),
                'load_average': getattr(os, 'getloadavg', lambda: [0,0,0])(),
                'claude_cli_path': subprocess.run(['which', 'claude'], capture_output=True, text=True).stdout.strip(),
                'working_directory_exists': True,
                'environment_variables': {
                    'ANTHROPIC_API_KEY': 'SET' if os.getenv('ANTHROPIC_API_KEY') else 'NOT_SET',
                    'GEMINI_API_KEY': 'SET' if os.getenv('GEMINI_API_KEY') else 'NOT_SET',
                    'PATH_LENGTH': len(os.getenv('PATH', '')),
                }
            }
            
            env_info['summary'] = f"Python {env_info['python_version']} on {platform.system()} | " \
                                f"CPU:{env_info['cpu_count']} | Memory:{env_info['available_memory_gb']:.1f}GB"
            
            return env_info
            
        except Exception as e:
            return {
                'error': str(e),
                'summary': f"Environment capture failed: {e}"
            }
    
    def _log_trace_summary(self, trace):
        """Genera log riassuntivo dettagliato del trace."""
        debug_logger.info("="*50)
        debug_logger.info(f"CLAUDE CLI EXECUTION TRACE SUMMARY")
        debug_logger.info(f"Operation ID: {trace['operation_id']}")
        debug_logger.info(f"Duration: {trace['final_result']['duration']:.2f}s")
        debug_logger.info(f"Success: {trace['final_result']['success']}")
        debug_logger.info(f"Phases executed: {len(trace['execution_phases'])}")
        
        for phase in trace['execution_phases']:
            debug_logger.info(f"  • {phase['phase']} @{phase['elapsed_from_start']:.1f}s")
        
        debug_logger.info("="*50)


class PerformanceRollbackManager:
    """Sistema di rollback per test comparativi di performance ottimizzazioni."""
    
    def __init__(self):
        self.rollback_points = {}
        self.performance_baselines = {}
        self.test_sessions = {}
        
    def create_rollback_point(self, session_id, point_name, orchestrator_state):
        """Crea un punto di rollback salvando lo stato corrente."""
        rollback_data = {
            'timestamp': time.time(),
            'point_name': point_name,
            'session_id': session_id,
            'orchestrator_state': {
                'performance_tracker': {
                    'operations_count': orchestrator_state.performance_tracker.operations_count,
                    'total_response_time': orchestrator_state.performance_tracker.total_response_time,
                    'error_count': orchestrator_state.performance_tracker.error_count,
                    'retry_count': orchestrator_state.performance_tracker.retry_count,
                    'session_start': orchestrator_state.performance_tracker.session_start
                },
                'timeout_predictor_state': getattr(orchestrator_state.timeout_predictor, 'timeout_history', []),
                'prompt_optimizer_stats': getattr(orchestrator_state.prompt_optimizer, 'optimization_stats', {}),
                'working_directory': orchestrator_state.working_directory,
                'total_cycles': getattr(orchestrator_state, 'total_cycles', 0)
            }
        }
        
        rollback_key = f"{session_id}_{point_name}"
        self.rollback_points[rollback_key] = rollback_data
        
        debug_logger.info(f"🔄 ROLLBACK POINT CREATED: {point_name} for session {session_id}")
        debug_logger.info(f"📊 Baseline: {rollback_data['orchestrator_state']['performance_tracker']['operations_count']} ops, "
                         f"{rollback_data['orchestrator_state']['performance_tracker']['total_response_time']:.1f}s total")
        
        return rollback_key
    
    def start_performance_test(self, session_id, test_name, baseline_point=None):
        """Inizia un test di performance con baseline."""
        test_key = f"{session_id}_{test_name}"
        
        test_session = {
            'start_time': time.time(),
            'test_name': test_name,
            'session_id': session_id,
            'baseline_point': baseline_point,
            'test_metrics': {
                'operations_before': 0,
                'operations_after': 0,
                'response_time_before': 0,
                'response_time_after': 0,
                'errors_before': 0,
                'errors_after': 0
            }
        }
        
        if baseline_point and baseline_point in self.rollback_points:
            baseline = self.rollback_points[baseline_point]
            test_session['test_metrics'].update({
                'operations_before': baseline['orchestrator_state']['performance_tracker']['operations_count'],
                'response_time_before': baseline['orchestrator_state']['performance_tracker']['total_response_time'],
                'errors_before': baseline['orchestrator_state']['performance_tracker']['error_count']
            })
        
        self.test_sessions[test_key] = test_session
        
        debug_logger.info(f"🧪 PERFORMANCE TEST START: {test_name}")
        if baseline_point:
            debug_logger.info(f"📈 Baseline: {test_session['test_metrics']['operations_before']} ops, "
                             f"{test_session['test_metrics']['response_time_before']:.1f}s")
        
        return test_key
    
    def complete_performance_test(self, test_key, orchestrator_state):
        """Completa il test e calcola i risultati comparativi."""
        if test_key not in self.test_sessions:
            debug_logger.error(f"Test session {test_key} not found")
            return None
        
        test_session = self.test_sessions[test_key]
        
        # Cattura metriche finali
        test_session['test_metrics'].update({
            'operations_after': orchestrator_state.performance_tracker.operations_count,
            'response_time_after': orchestrator_state.performance_tracker.total_response_time,
            'errors_after': orchestrator_state.performance_tracker.error_count,
            'duration': time.time() - test_session['start_time']
        })
        
        # Calcola differenze e percentuali di miglioramento
        metrics = test_session['test_metrics']
        ops_delta = metrics['operations_after'] - metrics['operations_before']
        time_delta = metrics['response_time_after'] - metrics['response_time_before']
        errors_delta = metrics['errors_after'] - metrics['errors_before']
        
        if ops_delta > 0:
            avg_time_before = metrics['response_time_before'] / max(metrics['operations_before'], 1)
            avg_time_after = time_delta / ops_delta
            time_improvement = ((avg_time_before - avg_time_after) / avg_time_before * 100) if avg_time_before > 0 else 0
        else:
            time_improvement = 0
        
        results = {
            'test_name': test_session['test_name'],
            'duration': metrics['duration'],
            'operations_delta': ops_delta,
            'time_delta': time_delta,
            'errors_delta': errors_delta,
            'time_improvement_percent': time_improvement,
            'success_rate_improvement': 0  # Calculate if needed
        }
        
        # Classifica il risultato
        if time_improvement > 10 and errors_delta <= 0:
            results['classification'] = "🟢 SIGNIFICATIVO MIGLIORAMENTO"
        elif time_improvement > 0 and errors_delta <= 0:
            results['classification'] = "🟡 MIGLIORAMENTO LIEVE"
        elif errors_delta > 0:
            results['classification'] = "🔴 PEGGIORAMENTO"
        else:
            results['classification'] = "⚪ NEUTRO"
        
        test_session['results'] = results
        
        debug_logger.info(f"🧪 PERFORMANCE TEST COMPLETED: {test_session['test_name']}")
        debug_logger.info(f"📊 Results: {results['classification']}")
        debug_logger.info(f"⏱️ Time improvement: {time_improvement:.1f}% | Operations: {ops_delta} | Errors: {errors_delta}")
        
        return results
    
    def rollback_to_point(self, session_id, point_name, orchestrator_instance):
        """Rollback dello stato orchestratore a un punto precedente."""
        rollback_key = f"{session_id}_{point_name}"
        
        if rollback_key not in self.rollback_points:
            debug_logger.error(f"Rollback point {rollback_key} not found")
            return False
        
        rollback_data = self.rollback_points[rollback_key]
        saved_state = rollback_data['orchestrator_state']
        
        # Ripristina performance tracker
        orchestrator_instance.performance_tracker.operations_count = saved_state['performance_tracker']['operations_count']
        orchestrator_instance.performance_tracker.total_response_time = saved_state['performance_tracker']['total_response_time']
        orchestrator_instance.performance_tracker.error_count = saved_state['performance_tracker']['error_count']
        orchestrator_instance.performance_tracker.retry_count = saved_state['performance_tracker']['retry_count']
        orchestrator_instance.performance_tracker.session_start = saved_state['performance_tracker']['session_start']
        
        # Ripristina altri stati se necessario
        if hasattr(orchestrator_instance, 'total_cycles'):
            orchestrator_instance.total_cycles = saved_state['total_cycles']
        
        debug_logger.info(f"🔄 ROLLBACK COMPLETED: Restored to {point_name}")
        debug_logger.info(f"📊 Restored state: {saved_state['performance_tracker']['operations_count']} ops, "
                         f"{saved_state['performance_tracker']['total_response_time']:.1f}s total")
        
        return True
    
    def get_test_comparison_report(self, session_id):
        """Genera report comparativo di tutti i test per una sessione."""
        session_tests = {k: v for k, v in self.test_sessions.items() if v['session_id'] == session_id}
        
        if not session_tests:
            return "📊 Nessun test di performance disponibile per questa sessione"
        
        report = f"📊 **PERFORMANCE COMPARISON REPORT** - Session {session_id}\n"
        report += "="*60 + "\n"
        
        for test_key, test_data in session_tests.items():
            if 'results' in test_data:
                r = test_data['results']
                report += f"🧪 **{r['test_name']}**: {r['classification']}\n"
                report += f"   ⏱️ Time improvement: {r['time_improvement_percent']:.1f}%\n"
                report += f"   🔢 Operations: +{r['operations_delta']} | Errors: {r['errors_delta']:+d}\n"
                report += f"   📅 Duration: {r['duration']:.1f}s\n\n"
        
        return report


class EnvironmentDiagnostics:
    """Sistema diagnostico completo per analisi root cause di timeout e performance issues."""
    
    def __init__(self):
        self.diagnostic_reports = []
        self.baseline_environment = None
        
    def capture_baseline_environment(self):
        """Cattura baseline dell'ambiente al primo avvio per confronti."""
        self.baseline_environment = self._comprehensive_environment_check()
        debug_logger.info("🏥 ENVIRONMENT BASELINE CAPTURED")
        debug_logger.info(f"📊 System: {self.baseline_environment['system_summary']}")
        return self.baseline_environment
    
    def diagnose_timeout_issue(self, operation_details, timeout_duration, environment_snapshot=None):
        """Esegue diagnosi completa per issue di timeout."""
        diagnosis = {
            'timestamp': time.time(),
            'operation_details': operation_details,
            'timeout_duration': timeout_duration,
            'environment_check': environment_snapshot or self._comprehensive_environment_check(),
            'probable_causes': [],
            'recommendations': [],
            'severity_level': 'UNKNOWN'
        }
        
        # Analizza possibili cause
        diagnosis['probable_causes'] = self._analyze_timeout_causes(diagnosis)
        
        # Genera raccomandazioni
        diagnosis['recommendations'] = self._generate_timeout_recommendations(diagnosis)
        
        # Calcola severità
        diagnosis['severity_level'] = self._calculate_severity_level(diagnosis)
        
        self.diagnostic_reports.append(diagnosis)
        
        debug_logger.info(f"🔍 TIMEOUT DIAGNOSIS COMPLETED - Severity: {diagnosis['severity_level']}")
        debug_logger.info(f"📋 Probable causes: {len(diagnosis['probable_causes'])}")
        debug_logger.info(f"💡 Recommendations: {len(diagnosis['recommendations'])}")
        
        return diagnosis
    
    def _comprehensive_environment_check(self):
        """Controllo completo dell'ambiente per diagnostica."""
        env_check = {
            'timestamp': time.time(),
            'system_info': {
                'platform': platform.platform(),
                'python_version': platform.python_version(),
                'cpu_count': os.cpu_count(),
                'architecture': platform.architecture()
            },
            'resources': {},
            'network': {},
            'claude_cli': {},
            'environment_vars': {},
            'disk_space': {},
            'processes': {},
            'system_summary': ''
        }
        
        try:
            # Resource monitoring
            if PSUTIL_AVAILABLE:
                memory = psutil.virtual_memory()
                cpu_percent = psutil.cpu_percent(interval=1.0)
            
            if PSUTIL_AVAILABLE:
                env_check['resources'] = {
                    'total_memory_gb': memory.total / (1024**3),
                    'available_memory_gb': memory.available / (1024**3),
                    'memory_percent': memory.percent,
                    'cpu_percent': cpu_percent,
                    'load_average': getattr(os, 'getloadavg', lambda: [0,0,0])(),
                    'swap_memory_percent': psutil.swap_memory().percent if hasattr(psutil, 'swap_memory') else 0
                }
            else:
                env_check['resources'] = {
                    'total_memory_gb': 'N/A',
                    'available_memory_gb': 'N/A', 
                    'memory_percent': 0,
                    'cpu_percent': 0,
                    'load_average': getattr(os, 'getloadavg', lambda: [0,0,0])(),
                    'swap_memory_percent': 0,
                    'psutil_warning': 'Resource monitoring limited - psutil not available'
                }
            
            # Network connectivity check
            try:
                import socket
                socket.create_connection(("8.8.8.8", 53), timeout=3)
                env_check['network']['connectivity'] = 'OK'
            except:
                env_check['network']['connectivity'] = 'LIMITED'
            
            # Claude CLI availability and version
            try:
                claude_version = subprocess.run(['claude', '--version'], capture_output=True, text=True, timeout=5)
                env_check['claude_cli'] = {
                    'available': claude_version.returncode == 0,
                    'version': claude_version.stdout.strip() if claude_version.returncode == 0 else 'UNKNOWN',
                    'path': subprocess.run(['which', 'claude'], capture_output=True, text=True).stdout.strip()
                }
            except:
                env_check['claude_cli'] = {'available': False, 'error': 'Command not found or timeout'}
            
            # Environment variables check
            env_check['environment_vars'] = {
                'ANTHROPIC_API_KEY': 'SET' if os.getenv('ANTHROPIC_API_KEY') else 'NOT_SET',
                'GEMINI_API_KEY': 'SET' if os.getenv('GEMINI_API_KEY') else 'NOT_SET',
                'PATH_segments': len(os.getenv('PATH', '').split(os.pathsep)),
                'PYTHONPATH': 'SET' if os.getenv('PYTHONPATH') else 'NOT_SET',
                'HOME': 'SET' if os.getenv('HOME') else 'NOT_SET'
            }
            
            # Disk space check
            try:
                current_dir = os.getcwd()
                if PSUTIL_AVAILABLE:
                    disk_usage = psutil.disk_usage(current_dir)
                    env_check['disk_space'] = {
                        'total_gb': disk_usage.total / (1024**3),
                        'free_gb': disk_usage.free / (1024**3),
                        'used_percent': (disk_usage.used / disk_usage.total) * 100,
                        'current_directory': current_dir
                    }
                else:
                    # Fallback using shutil for basic disk space info
                    try:
                        import shutil
                        disk_usage = shutil.disk_usage(current_dir)
                        env_check['disk_space'] = {
                            'total_gb': disk_usage.total / (1024**3),
                            'free_gb': disk_usage.free / (1024**3), 
                            'used_percent': ((disk_usage.total - disk_usage.free) / disk_usage.total) * 100,
                            'current_directory': current_dir,
                            'method': 'shutil_fallback'
                        }
                    except:
                        env_check['disk_space'] = {'error': 'Unable to check disk space - no psutil or shutil'}
            except:
                env_check['disk_space'] = {'error': 'Unable to check disk space'}
            
            # Process information
            try:
                if PSUTIL_AVAILABLE:
                    current_process = psutil.Process()
                    env_check['processes'] = {
                        'prometheus_memory_mb': current_process.memory_info().rss / (1024**2),
                        'prometheus_cpu_percent': current_process.cpu_percent(),
                        'open_files_count': len(current_process.open_files()) if hasattr(current_process, 'open_files') else 0,
                        'threads_count': current_process.num_threads()
                    }
                else:
                    # Fallback with basic process info
                    env_check['processes'] = {
                        'prometheus_memory_mb': 'N/A',
                        'prometheus_cpu_percent': 'N/A', 
                        'open_files_count': 'N/A',
                        'threads_count': 'N/A',
                        'fallback_pid': os.getpid(),
                        'method': 'basic_fallback'
                    }
            except:
                env_check['processes'] = {'error': 'Unable to get process info'}
            
            # Generate summary
            if PSUTIL_AVAILABLE:
                env_check['system_summary'] = f"{env_check['system_info']['platform']} | " \
                                            f"CPU:{env_check['system_info']['cpu_count']}@{env_check['resources']['cpu_percent']:.1f}% | " \
                                            f"Memory:{env_check['resources']['available_memory_gb']:.1f}GB free | " \
                                            f"Claude CLI:{env_check['claude_cli'].get('available', False)}"
            else:
                env_check['system_summary'] = f"{env_check['system_info']['platform']} | " \
                                            f"CPU:{env_check['system_info']['cpu_count']} cores | " \
                                            f"Monitoring:Limited(no psutil) | " \
                                            f"Claude CLI:{env_check['claude_cli'].get('available', False)}"
            
        except Exception as e:
            env_check['error'] = f"Environment check failed: {str(e)}"
            env_check['system_summary'] = f"Environment check failed: {str(e)}"
        
        return env_check
    
    def _analyze_timeout_causes(self, diagnosis):
        """Analizza le possibili cause del timeout basandosi sui dati diagnostici."""
        causes = []
        env = diagnosis['environment_check']
        operation = diagnosis['operation_details']
        
        # Resource constraints
        if env.get('resources', {}).get('memory_percent', 0) > 85:
            causes.append({
                'category': 'MEMORY_PRESSURE',
                'description': f"Alta pressione memoria: {env['resources']['memory_percent']:.1f}%",
                'severity': 'HIGH',
                'likelihood': 0.8
            })
        
        if env.get('resources', {}).get('cpu_percent', 0) > 80:
            causes.append({
                'category': 'CPU_OVERLOAD',
                'description': f"Alto utilizzo CPU: {env['resources']['cpu_percent']:.1f}%",
                'severity': 'MEDIUM',
                'likelihood': 0.6
            })
        
        # Claude CLI issues
        if not env.get('claude_cli', {}).get('available', True):
            causes.append({
                'category': 'CLAUDE_CLI_UNAVAILABLE',
                'description': "Claude CLI non disponibile o non funzionante",
                'severity': 'CRITICAL',
                'likelihood': 0.9
            })
        
        # Network connectivity
        if env.get('network', {}).get('connectivity') != 'OK':
            causes.append({
                'category': 'NETWORK_ISSUES',
                'description': "Problemi di connettività di rete",
                'severity': 'HIGH',
                'likelihood': 0.7
            })
        
        # API Keys
        if env.get('environment_vars', {}).get('ANTHROPIC_API_KEY') != 'SET':
            causes.append({
                'category': 'MISSING_API_KEY',
                'description': "ANTHROPIC_API_KEY non configurata",
                'severity': 'CRITICAL',
                'likelihood': 0.85
            })
        
        # Disk space
        if env.get('disk_space', {}).get('used_percent', 0) > 95:
            causes.append({
                'category': 'DISK_FULL',
                'description': f"Disco quasi pieno: {env['disk_space']['used_percent']:.1f}%",
                'severity': 'HIGH',
                'likelihood': 0.4
            })
        
        # Operation-specific analysis
        if operation.get('prompt_length', 0) > 10000:
            causes.append({
                'category': 'LARGE_PROMPT',
                'description': f"Prompt molto grande: {operation['prompt_length']} caratteri",
                'severity': 'MEDIUM',
                'likelihood': 0.6
            })
        
        return sorted(causes, key=lambda x: x['likelihood'], reverse=True)
    
    def _generate_timeout_recommendations(self, diagnosis):
        """Genera raccomandazioni per risolvere i timeout."""
        recommendations = []
        causes = diagnosis['probable_causes']
        
        for cause in causes:
            if cause['category'] == 'MEMORY_PRESSURE':
                recommendations.append({
                    'action': 'FREE_MEMORY',
                    'description': 'Chiudere applicazioni non necessarie o aumentare RAM',
                    'priority': 'HIGH',
                    'estimated_impact': 'SIGNIFICANT'
                })
            
            elif cause['category'] == 'CPU_OVERLOAD':
                recommendations.append({
                    'action': 'REDUCE_CPU_LOAD',
                    'description': 'Interrompere processi CPU-intensivi durante operazioni Prometheus',
                    'priority': 'MEDIUM',
                    'estimated_impact': 'MODERATE'
                })
            
            elif cause['category'] == 'CLAUDE_CLI_UNAVAILABLE':
                recommendations.append({
                    'action': 'REINSTALL_CLAUDE_CLI',
                    'description': 'Reinstallare o aggiornare Claude CLI',
                    'priority': 'CRITICAL',
                    'estimated_impact': 'COMPLETE_FIX'
                })
            
            elif cause['category'] == 'NETWORK_ISSUES':
                recommendations.append({
                    'action': 'CHECK_NETWORK',
                    'description': 'Verificare connessione internet e firewall',
                    'priority': 'HIGH',
                    'estimated_impact': 'SIGNIFICANT'
                })
            
            elif cause['category'] == 'MISSING_API_KEY':
                recommendations.append({
                    'action': 'SET_API_KEY',
                    'description': 'Configurare ANTHROPIC_API_KEY nel file .env',
                    'priority': 'CRITICAL',
                    'estimated_impact': 'COMPLETE_FIX'
                })
            
            elif cause['category'] == 'LARGE_PROMPT':
                recommendations.append({
                    'action': 'OPTIMIZE_PROMPT',
                    'description': 'Attivare ottimizzazioni prompt più aggressive',
                    'priority': 'MEDIUM',
                    'estimated_impact': 'MODERATE'
                })
        
        # Add general recommendations
        recommendations.append({
            'action': 'INCREASE_TIMEOUT',
            'description': 'Aumentare timeout per operazioni complesse',
            'priority': 'LOW',
            'estimated_impact': 'PARTIAL'
        })
        
        return recommendations
    
    def _calculate_severity_level(self, diagnosis):
        """Calcola il livello di severità del problema."""
        causes = diagnosis['probable_causes']
        
        critical_causes = [c for c in causes if c.get('severity') == 'CRITICAL']
        high_causes = [c for c in causes if c.get('severity') == 'HIGH']
        
        if critical_causes:
            return 'CRITICAL'
        elif len(high_causes) >= 2:
            return 'HIGH'
        elif high_causes:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def generate_diagnostic_report(self, session_id=None):
        """Genera report diagnostico completo per una sessione."""
        session_reports = [r for r in self.diagnostic_reports if not session_id or session_id in str(r.get('operation_details', {}))]
        
        if not session_reports:
            return "🏥 Nessun report diagnostico disponibile"
        
        report = f"🏥 **ENVIRONMENT DIAGNOSTIC REPORT**\n"
        if session_id:
            report += f"Session: {session_id}\n"
        report += "="*60 + "\n\n"
        
        # Summary statistics
        critical_count = sum(1 for r in session_reports if r['severity_level'] == 'CRITICAL')
        high_count = sum(1 for r in session_reports if r['severity_level'] == 'HIGH')
        
        report += f"📊 **SUMMARY**: {len(session_reports)} diagnosi | "
        report += f"🔴 Critical: {critical_count} | 🟡 High: {high_count}\n\n"
        
        # Most recent diagnosis details
        if session_reports:
            latest = session_reports[-1]
            report += f"🔍 **LATEST DIAGNOSIS** ({latest['severity_level']}):\n"
            
            for cause in latest['probable_causes'][:3]:  # Top 3 causes
                report += f"   • {cause['description']} (likelihood: {cause['likelihood']:.0%})\n"
            
            report += f"\n💡 **TOP RECOMMENDATIONS**:\n"
            for rec in latest['recommendations'][:3]:  # Top 3 recommendations
                report += f"   • {rec['description']} (priority: {rec['priority']})\n"
        
        return report


def _run_claude_with_prompt(prompt_text, working_dir=None, timeout=60, retry_count=0, max_retries=3, progress_queue=None, performance_tracker=None, prompt_optimizer=None, timeout_predictor=None):
    """
    Helper per eseguire Claude con prompt lunghi via stdin con retry intelligente e timeout progressivi.
    
    Args:
        prompt_text: Il prompt da inviare a Claude
        working_dir: Directory di lavoro
        timeout: Timeout iniziale (60s -> 120s -> 300s)
        retry_count: Numero retry corrente
        max_retries: Massimo numero di retry
        progress_queue: Queue per inviare feedback progress in tempo reale
        performance_tracker: Performance tracking instance
        prompt_optimizer: Prompt optimization instance
        timeout_predictor: Timeout prediction instance
    """
    
    # Initialize resource monitoring and tracing
    resource_monitor = SystemResourceMonitor()
    operation_name = f"Claude_CLI_{retry_count+1}_{len(prompt_text)}chars"
    
    # Initialize CLI tracing
    cli_tracer = ClaudeCLITracer()
    trace = cli_tracer.start_trace(operation_name, len(prompt_text), timeout, working_dir)
    
    # Define timeout levels at start for consistent access
    timeout_levels = [60, 120, 300]
    
    # NUOVO: Timeout prediction intelligente per eliminare timeout inutili
    cli_tracer.add_execution_phase(operation_name, "timeout_calculation", {"original_timeout": timeout})
    
    if timeout_predictor and retry_count == 0:
        # Per il primo tentativo, usa prediction intelligente
        should_skip, recommended_timeout = timeout_predictor.should_skip_lower_timeouts(len(prompt_text))
        if should_skip:
            current_timeout = recommended_timeout
            debug_logger.info(f"⚡ TIMEOUT PREDICTION: Prompt {len(prompt_text)} chars → Direct timeout {current_timeout}s")
            cli_tracer.add_execution_phase(operation_name, "smart_timeout_applied", 
                                         {"recommended_timeout": current_timeout, "reason": "intelligent_prediction"})
            if progress_queue:
                prediction = timeout_predictor.predict_performance(len(prompt_text))
                progress_queue.put(f"[INFO]🎯 **Smart Timeout**: {current_timeout}s (previsto {prediction['predicted_time']}s, risk {prediction['risk_level']})")
        else:
            current_timeout = timeout
            cli_tracer.add_execution_phase(operation_name, "standard_timeout_used", {"timeout": current_timeout})
    else:
        # Timeout progressivi per retry: 60s -> 120s -> 300s
        current_timeout = timeout_levels[min(retry_count, len(timeout_levels) - 1)]
        cli_tracer.add_execution_phase(operation_name, "progressive_timeout", 
                                     {"timeout": current_timeout, "retry_count": retry_count})
    
    # Progress feedback elegante per l'utente con performance prediction
    if progress_queue:
        if retry_count == 0:
            status_msg = _get_elegant_status_message("claude_processing", 0)
            progress_queue.put(f"[INFO]{status_msg}")
            
            # PROACTIVE FEEDBACK: Informa l'utente delle performance previste
            if timeout_predictor and len(prompt_text) > 3000:
                prediction = timeout_predictor.predict_performance(len(prompt_text))
                if prediction["risk_level"] in ["HIGH", "CRITICAL", "EXTREME"]:
                    progress_queue.put(f"[INFO]⏱️ **Performance Preview**: Operazione {prediction['risk_level'].lower()}, tempo previsto ~{prediction['predicted_time']}s")
        else:
            status_msg = _get_elegant_status_message("error_recovery", retry_count * 2, f"Retry {retry_count}/{max_retries}")
            progress_queue.put(f"[INFO]{status_msg}")
    
    # Optimize prompt if optimizer provided
    original_prompt_length = len(prompt_text)
    if prompt_optimizer:
        context_type = "development" if "ARCHITETTO" in prompt_text else "general"
        prompt_text = prompt_optimizer.optimize_prompt(prompt_text, context_type, None)  # conversation_history passed separately when available
    
    # Enhanced logging con metrics
    start_time = time.time()
    debug_logger.info(f"=== CLAUDE CLI EXECUTION START ===")
    debug_logger.info(f"Retry: {retry_count}/{max_retries}, Timeout: {current_timeout}s")
    debug_logger.info(f"Working dir: {working_dir}")
    debug_logger.info(f"Prompt length: {len(prompt_text)} characters")
    
    # Start resource monitoring
    resource_monitor.start_monitoring(operation_name)
    cli_tracer.add_execution_phase(operation_name, "resource_monitoring_started")
    
    if prompt_optimizer and original_prompt_length != len(prompt_text):
        saved_chars = original_prompt_length - len(prompt_text)
        debug_logger.info(f"Prompt optimized: -{saved_chars} chars ({saved_chars/original_prompt_length*100:.1f}%)")
        cli_tracer.add_execution_phase(operation_name, "prompt_optimized", 
                                     {"chars_saved": saved_chars, "optimization_percent": saved_chars/original_prompt_length*100})
    
    try:
        command_list = ["claude", "-p", "--dangerously-skip-permissions"]
        cli_tracer.add_execution_phase(operation_name, "command_preparation", 
                                     {"command": " ".join(command_list), "working_dir": working_dir})
        
        # Progress feedback durante l'esecuzione per operazioni lunghe
        if progress_queue and current_timeout > 60:
            status_msg = _get_elegant_status_message("claude_processing", 10, f"Timeout {current_timeout}s")
            progress_queue.put(f"[INFO]{status_msg}")
        
        # Execute subprocess with periodic resource monitoring
        cli_tracer.add_execution_phase(operation_name, "subprocess_execution_start", 
                                     {"timeout": current_timeout, "prompt_length": len(prompt_text)})
        
        try:
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
            execution_success = True
            cli_tracer.add_execution_phase(operation_name, "subprocess_execution_success", 
                                         {"return_code": result.returncode, "stdout_length": len(result.stdout or ""),
                                          "stderr_length": len(result.stderr or "")})
        except subprocess.TimeoutExpired as e:
            debug_logger.error(f"Claude CLI timeout after {current_timeout:.2f}s")
            execution_success = False
            result = None
            cli_tracer.add_execution_phase(operation_name, "subprocess_timeout", 
                                         {"timeout_after": current_timeout, "exception": str(e)})
        
        execution_time = time.time() - start_time
        
        # Stop resource monitoring and get report
        resource_report = resource_monitor.stop_monitoring(success=execution_success)
        cli_tracer.add_execution_phase(operation_name, "resource_monitoring_completed", 
                                     {"resource_report": resource_report['summary'] if resource_report else "No report"})
        
        if execution_success:
            debug_logger.info(f"Claude CLI completed in {execution_time:.2f}s")
            debug_logger.info(f"Return code: {result.returncode}")
        else:
            debug_logger.error(f"Claude CLI timeout after {current_timeout:.2f}s")
        
        # Handle timeout case
        if not execution_success:
            # Timeout case - no result object
            tokens_estimate = len(prompt_text) // 4
            if performance_tracker:
                performance_tracker.record_operation(
                    duration_seconds=execution_time,
                    tokens_estimate=tokens_estimate,
                    had_error=True,
                    was_retry=retry_count > 0
                )
            
            if progress_queue:
                progress_queue.put(f"[INFO]⏱️ **Timeout** dopo {execution_time:.1f}s - Trying recovery...")
            
            # Try retry with higher timeout
            if retry_count < max_retries:
                debug_logger.info(f"Retrying due to timeout...")
                return _retry_claude_with_backoff(prompt_text, working_dir, current_timeout, retry_count, max_retries, progress_queue, performance_tracker, prompt_optimizer, timeout_predictor)
            else:
                raise subprocess.TimeoutExpired(command_list, current_timeout)
        
        # Success feedback con metriche performance
        if result.returncode == 0:
            # Calcola metriche di performance
            tokens_estimate = len(prompt_text) // 4  # Rough estimate
            chars_per_second = len(prompt_text) / execution_time if execution_time > 0 else 0
            
            # Registra nel performance tracker
            if performance_tracker:
                performance_tracker.record_operation(
                    duration_seconds=execution_time,
                    tokens_estimate=tokens_estimate,
                    had_error=False,
                    was_retry=retry_count > 0
                )
            
            if progress_queue:
                # Messaggio elegante con metriche
                perf_msg = f"✅ **Completato** in {execution_time:.1f}s"
                if tokens_estimate > 100:
                    perf_msg += f" | ~{tokens_estimate} tokens"
                if chars_per_second > 100:
                    perf_msg += f" | {chars_per_second:.0f} chars/s"
                
                progress_queue.put(f"[INFO]{perf_msg}")
                
                # Aggiungi summary delle performance ogni 3 operazioni + efficienza rating
                if performance_tracker and performance_tracker.operations_count % 3 == 0:
                    summary = performance_tracker.get_session_summary()
                    efficiency = performance_tracker.get_efficiency_rating()
                    progress_queue.put(f"[INFO]{summary}")
                    progress_queue.put(f"[INFO]{efficiency}")
        
        if result.returncode != 0:
            error_msg = f"Errore: Claude command failed (code {result.returncode}): {result.stderr}"
            debug_logger.error(f"Claude CLI error: {error_msg}")
            
            # Error feedback per l'utente
            if progress_queue:
                progress_queue.put(f"[INFO]⚠️ **Errore temporaneo** - Analizzando e tentando recovery...")
            
            # Classificazione errori per retry logic
            error_type = _classify_claude_error(result.stderr, result.returncode)
            debug_logger.info(f"Error classified as: {error_type}")
            
            # Registra errore nel performance tracker
            if performance_tracker:
                tokens_estimate = len(prompt_text) // 4
                performance_tracker.record_operation(
                    duration_seconds=execution_time,
                    tokens_estimate=tokens_estimate,
                    had_error=True,
                    was_retry=retry_count > 0
                )
            
            # Retry solo per errori temporanei
            if error_type == "temporary" and retry_count < max_retries:
                debug_logger.info(f"Retrying due to temporary error...")
                return _retry_claude_with_backoff(prompt_text, working_dir, current_timeout, retry_count, max_retries, progress_queue, performance_tracker, prompt_optimizer, timeout_predictor)
            
            # Final error feedback
            if progress_queue:
                progress_queue.put(f"[INFO]❌ **Errore persistente** - Tentativo automatico di recovery...")
            
            return error_msg
        
        debug_logger.info(f"Claude CLI successful - Output length: {len(result.stdout)} characters")
        
        # Complete trace with success
        cli_tracer.complete_trace(operation_name, True, {
            "execution_time": execution_time,
            "output_length": len(result.stdout),
            "return_code": result.returncode,
            "resource_report": resource_report
        })
        
        return result.stdout.strip()
        
    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        error_msg = f"Errore: Claude command timed out after {current_timeout} seconds"
        debug_logger.error(f"Claude CLI timeout after {execution_time:.2f}s")
        
        # Complete trace with timeout failure
        trace_result = cli_tracer.complete_trace(operation_name, False, {
            "execution_time": execution_time,
            "timeout_duration": current_timeout,
            "failure_reason": "subprocess_timeout",
            "resource_report": resource_monitor.stop_monitoring(success=False) if resource_monitor else None
        })
        
        # Trigger environment diagnostics for timeout analysis
        # Note: In a real implementation, environment_diagnostics would be passed as parameter
        # or accessed through a global diagnostics manager
        debug_logger.info("🔍 TIMEOUT DETECTED - Environment diagnostics would be triggered here")
        debug_logger.info(f"📋 Timeout details: {current_timeout}s timeout, {len(prompt_text)} chars prompt")
        
        # Timeout feedback per l'utente
        if progress_queue:
            if retry_count < max_retries:
                next_timeout = timeout_levels[min(retry_count + 1, len(timeout_levels) - 1)]
                progress_queue.put(f"[INFO]⏱️ **Timeout** dopo {current_timeout}s - Aumento timeout a {next_timeout}s per operazioni complesse...")
            else:
                progress_queue.put(f"[INFO]⏰ **Timeout persistente** - Tentativo recovery con strategia alternativa...")
        
        # Retry con timeout maggiore
        if retry_count < max_retries:
            debug_logger.info(f"Retrying with increased timeout...")
            return _retry_claude_with_backoff(prompt_text, working_dir, current_timeout, retry_count, max_retries, progress_queue, performance_tracker, prompt_optimizer, timeout_predictor)
        
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
    """Classifica gli errori di Claude con diagnostica dettagliata per l'utente."""
    stderr_lower = stderr_output.lower() if stderr_output else ""
    
    # Mappa errori con diagnostica dettagliata
    error_diagnostics = {
        # Network/Connection Issues  
        "timeout": {
            "type": "temporary",
            "category": "Network", 
            "user_msg": "Timeout di rete - Claude impiega più tempo del previsto",
            "suggestion": "Retry automatico con timeout aumentato"
        },
        "connection": {
            "type": "temporary",
            "category": "Network",
            "user_msg": "Problema di connessione al server Claude",
            "suggestion": "Verifica connessione internet e retry automatico"
        },
        "network": {
            "type": "temporary", 
            "category": "Network",
            "user_msg": "Errore di rete generico",
            "suggestion": "Retry automatico tra qualche secondo"
        },
        
        # Rate Limiting
        "rate limit": {
            "type": "temporary",
            "category": "Rate Limit",
            "user_msg": "Limite di richieste raggiunto temporaneamente",
            "suggestion": "Attesa automatica prima del retry"
        },
        
        # Server Errors
        "server error": {
            "type": "temporary",
            "category": "Server",
            "user_msg": "Errore interno del server Claude",
            "suggestion": "Retry automatico - problema lato server"
        },
        "503": {
            "type": "temporary",
            "category": "Server", 
            "user_msg": "Servizio Claude temporaneamente non disponibile",
            "suggestion": "Retry automatico tra qualche minuto"
        },
        
        # Authentication/Permission
        "permission": {
            "type": "permanent",
            "category": "Permission",
            "user_msg": "Problema di permessi nell'accesso ai file", 
            "suggestion": "Controlla permessi directory di lavoro"
        },
        "authentication": {
            "type": "permanent",
            "category": "Auth",
            "user_msg": "Problema di autenticazione Claude CLI",
            "suggestion": "Verifica configurazione Claude Code CLI"
        },
        "401": {
            "type": "permanent",
            "category": "Auth",
            "user_msg": "Credenziali Claude CLI non valide",
            "suggestion": "Riavvia Claude Code CLI o verifica login"
        },
        
        # File/Path Issues
        "not found": {
            "type": "permanent",
            "category": "File System",
            "user_msg": "File o directory non trovata",
            "suggestion": "Verifica working directory impostata correttamente"
        },
        "invalid": {
            "type": "permanent", 
            "category": "Configuration",
            "user_msg": "Configurazione o parametro non valido",
            "suggestion": "Controlla impostazioni di Prometheus"
        }
    }
    
    # Cerca il primo match per diagnostica dettagliata
    for indicator, diagnostic in error_diagnostics.items():
        if indicator in stderr_lower:
            # Log diagnostica dettagliata
            debug_logger.info(f"🔍 ERROR DIAGNOSTIC:")
            debug_logger.info(f"   Category: {diagnostic['category']}")  
            debug_logger.info(f"   Type: {diagnostic['type']}")
            debug_logger.info(f"   User Message: {diagnostic['user_msg']}")
            debug_logger.info(f"   Suggestion: {diagnostic['suggestion']}")
            
            return diagnostic["type"]
    
    # Default: considera temporaneo per sicurezza
    debug_logger.info(f"🔍 ERROR DIAGNOSTIC: Unknown error - classified as temporary for safety")
    return "temporary"


def _get_elegant_status_message(operation_type, duration_seconds=0, extra_info=""):
    """
    Genera messaggi di status eleganti basati sul tipo di operazione e durata.
    """
    status_templates = {
        "claude_processing": {
            0: "🤖 **Claude** sta elaborando la richiesta...",
            10: "🤖 **Claude** - Elaborazione in corso (~{duration}s passati)...",
            30: "🤖 **Claude** - Operazione complessa in corso (~{duration}s)...",
            60: "🤖 **Claude** - Elaborazione approfondita (~{duration}s, quasi pronto)...",
            120: "🤖 **Claude** - Analisi dettagliata in corso (~{duration}s, operazione avanzata)..."
        },
        
        "gemini_processing": {
            0: "💎 **Gemini** sta elaborando la richiesta...",
            10: "💎 **Gemini** - Elaborazione in corso (~{duration}s passati)...",
            30: "💎 **Gemini** - Generazione creativa in corso (~{duration}s)...",
            60: "💎 **Gemini** - Elaborazione approfondita (~{duration}s, quasi pronto)...",
            120: "💎 **Gemini** - Analisi complessa in corso (~{duration}s, operazione avanzata)..."
        },
        
        "project_planning": {
            0: "📋 **Pianificazione Progetto** - Creando PRP dettagliato...",
            10: "📋 **Pianificazione** - Analizzando requisiti (~{duration}s)...",
            30: "📋 **Pianificazione** - Definendo architettura (~{duration}s)...",
            60: "📋 **Pianificazione** - Finalizzando strategia (~{duration}s)..."
        },
        
        "development_cycle": {
            0: "⚙️ **Ciclo Sviluppo** - Inizializzando iterazione...",
            15: "⚙️ **Sviluppo** - Implementando funzionalità (~{duration}s)...",
            45: "⚙️ **Sviluppo** - Refinement e ottimizzazioni (~{duration}s)...", 
            90: "⚙️ **Sviluppo** - Completamento iterazione (~{duration}s)..."
        },
        
        "error_recovery": {
            0: "🔧 **Recovery** - Analizzando errore...",
            5: "🔧 **Recovery** - Implementando strategia alternativa (~{duration}s)...",
            15: "🔧 **Recovery** - Tentativo avanzato di ripristino (~{duration}s)..."
        }
    }
    
    if operation_type not in status_templates:
        return f"⚡ **{operation_type.title()}** in corso{f' - {extra_info}' if extra_info else ''}..."
    
    templates = status_templates[operation_type]
    
    # Trova il template più appropriato per la durata
    best_threshold = 0
    for threshold in sorted(templates.keys()):
        if duration_seconds >= threshold:
            best_threshold = threshold
    
    message = templates[best_threshold]
    
    # Sostituisce placeholder
    if "{duration}" in message:
        message = message.format(duration=duration_seconds)
    
    if extra_info:
        message += f" {extra_info}"
        
    return message


def _retry_claude_with_backoff(prompt_text, working_dir, timeout, retry_count, max_retries, progress_queue=None, performance_tracker=None, prompt_optimizer=None, timeout_predictor=None):
    """Implementa retry con backoff exponenziale."""
    retry_count += 1
    
    # Backoff exponenziale: 1s, 2s, 4s
    backoff_time = 2 ** (retry_count - 1)
    debug_logger.info(f"Waiting {backoff_time}s before retry {retry_count}/{max_retries}")
    
    # Progress feedback durante backoff
    if progress_queue:
        progress_queue.put(f"[INFO]⏳ **Attendo {backoff_time}s** prima del retry per ottimizzare la connessione...")
    
    time.sleep(backoff_time)
    
    return _run_claude_with_prompt(prompt_text, working_dir, timeout, retry_count, max_retries, progress_queue, performance_tracker, prompt_optimizer, timeout_predictor)

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
        
        # NEW: Performance tracking per ottimizzazione esperienza utente
        self.performance_tracker = PerformanceTracker()
        
        # NEW: Sistema di ottimizzazione avanzato
        self.prompt_optimizer = PromptOptimizer()
        self.timeout_predictor = TimeoutPredictor()
        
        # NEW: System resource monitoring per debugging timeout
        self.resource_monitor = SystemResourceMonitor()
        
        # NEW: Detailed Claude CLI execution tracing
        self.cli_tracer = ClaudeCLITracer()
        
        # NEW: Performance rollback manager per test comparativi
        self.rollback_manager = PerformanceRollbackManager()
        
        # NEW: Environment diagnostics per root cause analysis
        self.environment_diagnostics = EnvironmentDiagnostics()
        
        # NEW: User communication system for better UX during development
        self.user_communicator = UserCommunicator(lang=self.lang)
        
        # Capture baseline environment on initialization
        try:
            self.environment_diagnostics.capture_baseline_environment()
        except Exception as e:
            debug_logger.error(f"Failed to capture baseline environment: {e}")
        
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
                
                # NEW: Estrae informazioni intermedie utili per l'utente
                self._extract_llm_intermediate_info(response_text, self.output_queue)
                
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
            
            claude_response = _run_claude_with_prompt(full_dev_prompt, self.working_directory, timeout=180, progress_queue=self.output_queue, performance_tracker=self.performance_tracker, prompt_optimizer=self.prompt_optimizer, timeout_predictor=self.timeout_predictor)
            
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
            
            # NEW: Estrae informazioni intermedie utili per l'utente
            self._extract_llm_intermediate_info(claude_response, self.output_queue)
            
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
            
            claude_response = _run_claude_with_prompt(prompt, self.working_directory, timeout=180, progress_queue=self.output_queue, performance_tracker=self.performance_tracker, prompt_optimizer=self.prompt_optimizer, timeout_predictor=self.timeout_predictor)
            
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
            claude_response = _run_claude_with_prompt(prompt, self.working_directory, timeout=180, progress_queue=self.output_queue, performance_tracker=self.performance_tracker, prompt_optimizer=self.prompt_optimizer, timeout_predictor=self.timeout_predictor)
            
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
            response_text = response.text.strip()
            
            # NEW: Estrae informazioni intermedie utili per l'utente
            self._extract_llm_intermediate_info(response_text, self.output_queue)
            
            # Notifica successo del fallback
            success_message = ProviderErrorHandler.get_user_message('fallback_success', self.lang, 'Gemini')
            self.output_queue.put(f"{success_message}\n")
            
            return response_text
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
            # NUOVO: Messaggio user-friendly per riavvio
            resuming_message = self.user_communicator.generate_progress_message('resuming')
            self.output_queue.put(f"[USER_FEEDBACK]💬 {resuming_message}")
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
            debug_logger.info(f"Starting brainstorming for: {user_text[:50]}...")
            chunks_sent = 0
            for chunk in self.handle_brainstorming(user_text):
                debug_logger.info(f"Sending chunk {chunks_sent+1}: {len(chunk) if chunk else 0} chars")
                self.output_queue.put(chunk)
                chunks_sent += 1
            debug_logger.info(f"Brainstorming complete, sent {chunks_sent} chunks, sending None")
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
        debug_logger.info(f"handle_brainstorming called with text: {user_text[:50]}...")
        debug_logger.info(f"architect_llm: {self.architect_llm}, working_directory: {self.working_directory}")
        full_response = ""  # Inizializza FUORI dal try per scope corretto
        try:
            
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
                    full_response = _run_claude_with_prompt(brainstorm_prompt, self.working_directory, timeout=60, progress_queue=self.output_queue, performance_tracker=self.performance_tracker, prompt_optimizer=self.prompt_optimizer, timeout_predictor=self.timeout_predictor)
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
                full_response = _run_claude_with_prompt(brainstorm_prompt, self.working_directory, timeout=60, progress_queue=self.output_queue, performance_tracker=self.performance_tracker, prompt_optimizer=self.prompt_optimizer, timeout_predictor=self.timeout_predictor)
                debug_logger.info(f"Claude brainstorm response received: {len(full_response) if full_response else 0} chars")
                if full_response and full_response.strip():
                    yield full_response
                else:
                    yield "Errore: Risposta vuota da Claude CLI"
            
            # Salva nella cronologia solo se abbiamo una risposta valida
            if full_response and full_response.strip():
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
        
        # Pattern che indicano domande dirette all'utente che richiedono PAUSA
        # ATTENZIONE: Questi devono essere MOLTO specifici per evitare falsi positivi
        question_patterns = [
            "come vuoi procedere?",
            "quale preferisci?", 
            "che cosa scegli?",
            "vuoi che proceda",  # Rimosso "come procedere?" che è troppo generico
            "how do you want to proceed",
            "which option do you prefer",
            "what would you like me to do",
            "which do you prefer",
            "should i proceed with",
            "what should i do next",
            "please let me know"
        ]
        
        # Pattern che indicano liste di opzioni multiple (segnale forte di domanda)
        option_list_patterns = [
            "1\\.**.*2\\.**",  # Cerca pattern "1. ... 2. ..."
            "opzione 1.*opzione 2",
            "option 1.*option 2",
            "**1.**.*2.**",
            "\\*\\*opzioni\\*\\*",
            "**options**"
        ]
        
        import re
        
        # PRIMO: Check per liste di opzioni (segnale più forte)
        for pattern in option_list_patterns:
            if re.search(pattern, response_lower, re.DOTALL):
                return True
        
        # SECONDO: Check direct patterns (molto specifici)
        for pattern in question_patterns:
            if pattern in response_lower:
                return True
        
        # TERZO: Pattern richiesto: domanda con contesto + lista numerata
        # Solo se c'è una vera lista di opzioni numerata
        if re.search(r'come procedo\?.*1\..*2\..*3\.', response_lower, re.DOTALL):
            return True
        
        return False
    
    def _extract_llm_intermediate_info(self, claude_response, progress_queue):
        """
        Estrae informazioni utili dalle risposte di Claude per fornire feedback intermedio elegante all'utente.
        """
        if not claude_response or not progress_queue:
            return
        
        response_lower = claude_response.lower()
        
        # Estrae azioni principali in corso
        action_patterns = {
            "creo": "🎨 **Creando** componenti dell'applicazione...",
            "sto creando": "🎨 **Creando** componenti dell'applicazione...",
            "implementing": "⚙️ **Implementando** logica dell'applicazione...",
            "adding": "➕ **Aggiungendo** nuove funzionalità...",
            "configurando": "🔧 **Configurando** l'ambiente di sviluppo...",
            "installing": "📦 **Installando** dipendenze necessarie...",
            "testing": "🧪 **Testing** funzionalità implementate...",
            "verifico": "✅ **Verificando** correttezza dell'implementazione...",
            "fixing": "🔧 **Correggendo** problemi identificati...",
            "organizing": "📁 **Organizzando** struttura del progetto...",
            "styling": "🎨 **Applicando** stili e design...",
            "connecting": "🔗 **Collegando** componenti dell'app..."
        }
        
        # Estrae file specifici menzionati
        file_patterns = {
            "index.html": "📄 **File HTML** - Struttura principale",
            "style.css": "🎨 **File CSS** - Design e layout", 
            "script.js": "⚡ **File JS** - Logica applicazione",
            "app.js": "⚡ **File JS** - Logica applicazione",
            "package.json": "📦 **Package.json** - Configurazione progetto"
        }
        
        # Cerca ed estrae azioni
        found_actions = []
        for pattern, message in action_patterns.items():
            if pattern in response_lower:
                found_actions.append(message)
                
        # Cerca file menzionati
        found_files = []
        for pattern, message in file_patterns.items():
            if pattern in response_lower:
                found_files.append(message)
        
        # Invia feedback elegante se trovato qualcosa di utile
        if found_actions:
            # Prendi solo le prime 2 azioni per non spammare
            for action in found_actions[:2]:
                progress_queue.put(f"[INFO]{action}")
        
        if found_files:
            # Prendi solo i primi 2 file per non spammare
            files_msg = " | ".join(found_files[:2])
            progress_queue.put(f"[INFO]📁 **Lavorando su**: {files_msg}")
        
        # Estrae progress indicators da Claude
        progress_patterns = {
            "completato": "✅ **Fase completata**",
            "implemented": "✅ **Implementazione completata**",
            "creato con successo": "✅ **Creazione riuscita**",
            "ready to": "🚀 **Pronto per il prossimo step**",
            "moving to": "➡️ **Procedendo al prossimo task**"
        }
        
        for pattern, message in progress_patterns.items():
            if pattern in response_lower:
                progress_queue.put(f"[INFO]{message}")
                break  # Solo un messaggio di progress

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
                # Filtra file di sistema che possono essere ignorati
                system_files = ['.DS_Store', 'Thumbs.db', '.gitkeep', 'desktop.ini']
                relevant_files = [f for f in files_in_dir if f not in system_files]
                
                if relevant_files:
                    user_feedback = f"CRITICAL: La directory contiene già questi file: {', '.join(relevant_files)}. NON dire 'progetto già completo'. ANALIZZA il contenuto di questi file e confrontali con i requisiti del PRP attuale. Se NON corrispondono, avvisa l'utente del conflitto e chiedi come procedere. Se corrispondono, verifica che funzionino come da specifiche."
                else:
                    # Solo file di sistema - tratta come directory vuota
                    user_feedback = "DIRECTORY PRATICAMENTE VUOTA (solo file di sistema). INIZIA IMMEDIATAMENTE il setup del progetto seguendo esattamente le tecnologie specificate nel PRP. NON chiedere conferma, PROCEDI DIRETTAMENTE con il comando appropriato."
            else:
                user_feedback = "DIRECTORY COMPLETAMENTE VUOTA. INIZIA IMMEDIATAMENTE il setup del progetto seguendo esattamente le tecnologie specificate nel PRP. NON chiedere conferma, PROCEDI DIRETTAMENTE con il comando appropriato basato sulle specifiche del PRP."
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
            
            # CRITICAL FIX: Salva la risposta del development step nella cronologia
            if step_response and step_response.strip():
                self.conversation_history.append(f"[Prometheus]: {step_response}")
                self.save_state(verbose=False)  # Salvataggio silenzioso
            
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
                # NUOVO: Messaggio user-friendly per pausa
                pause_message = self.user_communicator.generate_progress_message('pause_question')
                self.output_queue.put(f"[USER_FEEDBACK]💬 {pause_message}")
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
            
            # CRITICAL FIX: Salva la risposta del development step nella cronologia
            if step_response and step_response.strip():
                self.conversation_history.append(f"[Prometheus]: {step_response}")
                self.save_state(verbose=False)  # Salvataggio silenzioso
            
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
            step_response = ""
            for chunk in self.handle_development_step(user_feedback):
                self.output_queue.put(chunk)
                step_response += str(chunk)
            
            # CRITICAL FIX: Salva la risposta del development step nella cronologia
            if step_response and step_response.strip():
                self.conversation_history.append(f"[Prometheus]: {step_response}")
                self.save_state(verbose=False)  # Salvataggio silenzioso
            
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
                "REGOLA CRITICA - SVILUPPO AUTONOMO:\n"
                "- Directory vuota o con solo file di sistema (.DS_Store, etc) = PROCEDI IMMEDIATAMENTE con setup\n"
                "- NON chiedere mai conferma per operazioni ovvie (setup, installazioni, creazione file)\n"
                "- Output: SEMPRE comando shell diretto o istruzione Claude specifica\n"
                "- Solo pause per conflitti REALI o decisioni architetturali complesse\n\n"
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
            
            # NUOVO: User-friendly thinking message
            thinking_message = self.user_communicator.should_stream_thinking()
            yield f"[USER_THINKING]{thinking_message}"
            
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
            
            # CRITICAL FIX: Calculate elapsed time FIRST
            claude_elapsed_ms = int((time.time() - start_claude_time) * 1000)
            
            # Segnala completamento del ciclo con metriche di performance
            chars_per_second = int(len(full_claude_output) / (claude_elapsed_ms / 1000)) if claude_elapsed_ms > 0 else 0
            prompt_tokens_estimate = len(gemini_prompt_for_claude) // 4
            response_tokens_estimate = len(full_claude_output) // 4
            total_tokens_estimate = prompt_tokens_estimate + response_tokens_estimate
            
            performance_metrics = f"Completato in {claude_elapsed_ms/1000:.1f}s | ~{total_tokens_estimate} tokens | {chars_per_second} chars/s"
            
            if self.lang == 'it':
                yield f"\n\n[CYCLE_COMPLETE]🔄 **Passo completato.** Il ciclo continua autonomamente... ({performance_metrics})"
            else:
                yield f"\n\n[CYCLE_COMPLETE]🔄 **Step completed.** The cycle continues autonomously... ({performance_metrics})"

            # LOG: Response from Claude CLI
            log_prompt_interaction(
                phase="DEVELOPMENT",
                source="CLAUDE_CLI",
                target="PROMETHEUS",
                prompt_text="",
                response_text=full_claude_output,
                timing_ms=claude_elapsed_ms
            )
            
            # NUOVO: Analizza la risposta di Claude per feedback user-friendly
            try:
                # Combina sia il comando inviato che la risposta per un'analisi completa
                combined_ai_output = gemini_prompt_for_claude + "\n" + full_claude_output
                activities = self.user_communicator.extract_activity_from_ai_response(combined_ai_output)
                
                # Fornisci feedback per ogni attività rilevata
                for activity_type, context in activities:
                    user_message = self.user_communicator.generate_progress_message(activity_type, context)
                    yield f"\n[USER_FEEDBACK]💬 {user_message}"
                
                # Se non sono state rilevate attività specifiche, fornisci un messaggio generico di progresso
                if not activities and full_claude_output.strip():
                    if self.lang == 'it':
                        yield f"\n[USER_FEEDBACK]⚡ Operazione completata con successo - continuo con lo sviluppo..."
                    else:
                        yield f"\n[USER_FEEDBACK]⚡ Operation completed successfully - continuing development..."
                        
            except Exception as comm_error:
                debug_logger.warning(f"User communication analysis failed: {comm_error}")
                # Non bloccare il processo per errori di comunicazione
            
            self.conversation_history.append(f"[Claude (Output)]: {full_claude_output}")
            self.save_state(verbose=False)  # Salvataggio silenzioso durante sviluppo automatico
            
        except Exception as e:
            yield f"\n\n**ERRORE CRITICO:** {e}"
