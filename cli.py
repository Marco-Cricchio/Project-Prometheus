# cli.py
import os
import tkinter as tk
from tkinter import filedialog
import queue
from core.orchestrator import Orchestrator, CONVERSATIONS_DIR
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt


def get_multiline_input(console, lang='en'):
    """Gestisce l'input multiriga dall'utente."""
    if lang == 'it':
        console.print("[dim]Puoi usare più righe. Premi Invio su una riga vuota per inviare.[/dim]")
        prompt_text = "[bold cyan]Tu[/bold cyan]"
    else:
        console.print("[dim]You can use multiple lines. Press Enter on empty line to send.[/dim]")
        prompt_text = "[bold cyan]You[/bold cyan]"
    
    lines = []
    try:
        while True:
            if lines:
                line = console.input("[dim]...[/dim] ")  # Continuazione
            else:
                line = console.input(f"{prompt_text}: ")  # Prima riga
                
            if not line:  # Riga vuota = fine input
                if lines:  # Se ci sono già righe, invia
                    break
                else:  # Se è la prima riga vuota, chiedi di nuovo
                    continue
            lines.append(line)
    except KeyboardInterrupt:
        # Ritorna None per indicare che l'utente vuole uscire
        return None
    
    return "\n".join(lines)

def main():
    console = Console()
    console.print(Markdown("# Benvenuto in Project Prometheus (CLI v5.1) / Welcome to Project Prometheus"))
    
    # 1. Selezione Lingua
    lang = Prompt.ask("Scegli una lingua / Choose a language", choices=["it", "en"], default="en")
    
    # 2. Selezione Architetto
    architect_choices = {
        'it': {
            'prompt': 'Scegli l\'architetto AI',
            'options': {'gemini': '🔷 Gemini (Creativo)', 'claude': '🧠 Claude (Analitico)'}
        },
        'en': {
            'prompt': 'Choose AI architect', 
            'options': {'gemini': '🔷 Gemini (Creative)', 'claude': '🧠 Claude (Analytical)'}
        }
    }
    
    console.print(f"\n[bold yellow]{architect_choices[lang]['prompt']}:[/bold yellow]")
    for key, desc in architect_choices[lang]['options'].items():
        console.print(f"  [{key}] - {desc}")
    
    architect_llm = Prompt.ask("Architetto / Architect", choices=["gemini", "claude"], default="gemini")
    
    # Messaggi localizzati
    messages = {
        'it': {
            'development_trigger': 'Per avviare lo sviluppo, scrivi `ACCENDI I MOTORI!`',
            'continue_session': 'Vuoi continuare una conversazione esistente?',
            'select_session': 'Scegli una sessione da riprendere:',
            'session_number': 'Numero sessione',
            'new_session_name': 'Dai un nome a questa nuova conversazione',
            'starting_new': 'Avvio di una nuova sessione...',
            'goodbye': 'Arrivederci!',
            'thinking': 'Sto pensando...',
            'directory_prompt': 'Per favore, seleziona la cartella di lavoro per il progetto...',
            'selection_canceled': 'Selezione annullata. Riprova.',
            'directory_set': 'Directory di lavoro impostata con successo!'
        },
        'en': {
            'development_trigger': 'To start development, write `START THE ENGINES!`',
            'continue_session': 'Do you want to continue an existing conversation?',
            'select_session': 'Choose a session to resume:',
            'session_number': 'Session number',
            'new_session_name': 'Give a name to this new conversation',
            'starting_new': 'Starting a new session...',
            'goodbye': 'Goodbye!',
            'thinking': 'Thinking...',
            'directory_prompt': 'Please select the working folder for the project...',
            'selection_canceled': 'Selection canceled. Try again.',
            'directory_set': 'Working directory set successfully!'
        }
    }
    
    msg = messages[lang]
    console.print(Markdown(f"*{msg['development_trigger']}*"))

    # 2. Ripristino o Nuova Sessione
    orchestrator = None
    if not os.path.exists(CONVERSATIONS_DIR): 
        os.makedirs(CONVERSATIONS_DIR)
    
    saved_sessions = sorted([f.replace('.json', '') for f in os.listdir(CONVERSATIONS_DIR) if f.endswith('.json')], reverse=True)

    if saved_sessions:
        try:
            if Prompt.ask(msg['continue_session'], choices=["si", "yes", "no"], default="no") in ["si", "yes"]:
                console.print(f"\n[bold green]{msg['select_session']}[/bold green]")
                session_choices = {str(i+1): s for i, s in enumerate(saved_sessions)}
                for key, val in session_choices.items():
                    console.print(f"  [{key}] - {val}")
                
                session_choice = Prompt.ask(msg['session_number'], choices=session_choices.keys())
                selected_session_id = session_choices[session_choice]
                orchestrator = Orchestrator(session_id=selected_session_id, lang=lang, architect_llm=architect_llm)
        except KeyboardInterrupt:
            console.print(f"\n[bold red]{msg['goodbye']}[/bold red]")
            return

    # 3. Nuova sessione con nome personalizzato e selezione directory
    if not orchestrator:
        console.print(f"\n[bold green]{msg['starting_new']}[/bold green]")
        try:
            session_name = Prompt.ask(msg['new_session_name'])
        except KeyboardInterrupt:
            console.print(f"\n[bold red]{msg['goodbye']}[/bold red]")
            return
        # Sostituisce spazi e caratteri non validi per un nome file
        session_id = session_name.replace(" ", "_").replace("/", "_").replace("\\", "_").lower()
        orchestrator = Orchestrator(session_id=session_id, lang=lang, architect_llm=architect_llm)
        
        # Chiedi la directory di lavoro usando il selettore nativo
        while not orchestrator.working_directory:
            console.print(f"\n[bold yellow]{msg['directory_prompt']}[/bold yellow]")
            root = tk.Tk()
            root.withdraw()  # Nasconde la finestra principale di Tkinter
            
            # Localizza il titolo del dialog
            dialog_title = "Seleziona la cartella di progetto" if lang == 'it' else "Select project folder"
            directory_path = filedialog.askdirectory(title=dialog_title)
            root.destroy()
            
            if not directory_path:
                console.print(f"[bold red]{msg['selection_canceled']}[/bold red]")
                continue
                
            response = orchestrator.set_working_directory(directory_path)
            console.print(f"[bold green]Prometheus:[/bold green] {response}")
            
            if "ERRORE" in response or "ERROR" in response:
                orchestrator.working_directory = None  # Resetta se c'è stato un errore
            else:
                console.print(f"[bold blue]{msg['directory_set']}[/bold blue]")
                orchestrator.save_state()  # Salva lo stato con la nuova directory

    # Stampa la cronologia esistente o il messaggio iniziale
    for line in orchestrator.conversation_history:
        speaker, text = line.split("]: ", 1)
        speaker = speaker.replace("[", "")
        if speaker == "User":
             console.print(f"[bold cyan]{speaker}:[/bold cyan] {text}")
        else:
            console.print(f"[bold green]{speaker}:[/bold green] {text}")

    # Mostra la directory di lavoro se impostata
    if orchestrator.working_directory:
        working_dir_msg = f"Directory di lavoro: {orchestrator.working_directory}" if lang == 'it' else f"Working directory: {orchestrator.working_directory}"
        console.print(f"[dim]{working_dir_msg}[/dim]\n")

    # 4. Ciclo principale con input multiriga
    while True:
        try:
            user_input = get_multiline_input(console, lang)
            if user_input is None or not user_input or user_input.lower() in ["esci", "exit", "quit"]: 
                break

            console.print("[bold green]Prometheus:[/bold green] ", end="")
            
            # Controlla se stiamo avviando lo sviluppo
            is_starting_development = "ACCENDI I MOTORI!" in user_input.upper()
            
            # Status indicator dinamico basato sulla modalità
            if orchestrator.mode == "DEVELOPMENT" or is_starting_development:
                status_msg = "Sto sviluppando..." if lang == 'it' else "Developing..."
                status_style = "bold green"
            else:
                status_msg = msg['thinking']
                status_style = "italic"
            
            with console.status(f"[{status_style}]{status_msg}...[/{status_style}]", spinner="dots"):
                # Process input (non-blocking, puts output in queue)
                orchestrator.process_user_input(user_input)
                
                # Read from output queue until we get the end signal (None)
                first_phase_done = False
                while True:
                    try:
                        chunk = orchestrator.output_queue.get(timeout=1.0)
                        if chunk is None:  # End signal
                            if is_starting_development and not first_phase_done:
                                # Prima fase completata (brainstorming), ma continua per lo sviluppo
                                first_phase_done = True
                                continue
                            else:
                                # Fine normale o sviluppo terminato
                                break
                        # Gestisci segnali speciali anche nella prima fase
                        if chunk.startswith("[THINKING]"):
                            console.print("🤔 ", end="", style="yellow")
                        elif chunk.startswith("[CLAUDE_PROMPT]"):
                            # Skip durante la prima fase per evitare spam
                            pass
                        elif chunk.startswith("[CLAUDE_WORKING]"):
                            # Skip durante la prima fase
                            pass 
                        elif chunk.startswith("[CYCLE_COMPLETE]"):
                            # Skip durante la prima fase
                            pass
                        elif chunk.startswith("[INFO]"):
                            console.print(f"\nℹ️  {chunk[6:]}", style="blue")
                        else:
                            console.print(chunk, end="")
                        orchestrator.output_queue.task_done()
                    except queue.Empty:
                        # Se stiamo sviluppando e il thread è ancora attivo, continua ad aspettare
                        if is_starting_development and orchestrator.is_running:
                            continue
                        else:
                            break
                    except:
                        break
            console.print()
            
            # Se lo sviluppo è in corso, entra in modalità monitoring
            if is_starting_development and orchestrator.is_running:
                console.print(f"\n[bold yellow]🔄 Ciclo di sviluppo autonomo attivo![/bold yellow]")
                console.print(f"[dim]Il sistema continuerà a sviluppare autonomamente. Vedrai l'output in tempo reale.[/dim]")
                console.print(f"[dim]Premi Ctrl+C in qualsiasi momento per tornare al controllo manuale.[/dim]\n")
                
                # Loop di monitoraggio sviluppo
                try:
                    while orchestrator.is_running:
                        try:
                            # Controlla se c'è nuovo output (timeout più lungo per ridurre CPU usage)
                            chunk = orchestrator.output_queue.get(timeout=2.0)
                            if chunk is None:
                                continue
                            
                            # Mostra tutto l'output sviluppo, inclusi i segnali di debug per trasparenza
                            if chunk.startswith("[THINKING]"):
                                console.print("🤔 ", end="", style="yellow")
                            elif chunk.startswith("[CLAUDE_PROMPT]"):
                                prompt_text = chunk[15:].strip()
                                console.print(f"\n📝 [bold blue]Architetto → Claude:[/bold blue]")
                                console.print(f"[dim]{prompt_text[:100]}{'...' if len(prompt_text) > 100 else ''}[/dim]")
                            elif chunk.startswith("[CLAUDE_WORKING]"):
                                console.print("\n⚡ [bold green]Claude al lavoro...[/bold green]")
                            elif chunk.startswith("[CYCLE_COMPLETE]"):
                                console.print(f"\n{chunk[17:]}", style="bold cyan")  # Rimuove il prefisso e aggiunge newline
                            elif chunk.startswith("[INFO]"):
                                console.print(f"\nℹ️  {chunk[6:]}", style="blue")  # Messaggi informativi
                            else:
                                console.print(chunk, end="")
                            orchestrator.output_queue.task_done()
                        except queue.Empty:
                            # Nessun output, continua il loop
                            continue
                except KeyboardInterrupt:
                    # Ctrl+C per tornare al controllo manuale
                    orchestrator.is_running = False
                    console.print("\n\n[bold yellow]⏸️  Sviluppo messo in pausa. Tornando al controllo manuale...[/bold yellow]\n")
                    # Non fare break dal loop principale, continua con il prompt normale

        except KeyboardInterrupt:
            break
    
    console.print(f"\n[bold red]{msg['goodbye']}[/bold red]")

if __name__ == "__main__":
    main()