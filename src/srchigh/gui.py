import re
import sys
import io
import os
import threading
import contextlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

from .session import ECourtSession
from .config import COURT_NAMES, BASE_URL

class StdoutRedirector:
    """Redirects stdout/stderr writes to a custom callback function."""
    def __init__(self, callback):
        self.callback = callback

    def write(self, string):
        if string:
            self.callback(string)

    def flush(self):
        pass

class GuiECourtSession(ECourtSession):
    """Subclass of ECourtSession to intercept captcha images via HTTP GET requests."""
    def __init__(self, on_image_callback=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.on_image_callback = on_image_callback

    def _get(self, path, **kwargs):
        res = super()._get(path, **kwargs)
        if "securimage_show.php" in path and self.on_image_callback:
            try:
                img = Image.open(io.BytesIO(res.content))
                self.on_image_callback(img)
            except Exception:
                pass
        return res

class GuiController:
    """Controller that coordinates the UI state, background threading, and scraping task."""
    
    def __init__(self):
        self.search_term = ""
        self.count = 5
        self.court = ""
        self.from_date = ""
        self.to_date = ""
        self.is_running = False
        self.error_message = ""
        self.on_log = None
        self.on_image = None
        self.output_dir = os.path.expanduser("~/myJud")
        self._thread = None

    def validate(self):
        """Validates input fields."""
        if not self.search_term.strip():
            self.error_message = "Search term is required"
            return False
        
        date_pattern = re.compile(r"^\d{2}-\d{2}-\d{4}$")
        if self.from_date and not date_pattern.match(self.from_date):
            self.error_message = "Invalid from_date format. Must be DD-MM-YYYY"
            return False
            
        if self.to_date and not date_pattern.match(self.to_date):
            self.error_message = "Invalid to_date format. Must be DD-MM-YYYY"
            return False
            
        self.error_message = ""
        return True

    def log(self, message):
        """Dispatches progress messages to the log listener."""
        if self.on_log:
            self.on_log(message)

    def run_scraper(self, on_complete=None):
        """Starts the scraper in a background thread."""
        if not self.validate():
            self.log(f"Validation Error: {self.error_message}\n")
            if on_complete:
                on_complete()
            return False

        self.is_running = True
        self._thread = threading.Thread(
            target=self._threaded_run,
            args=(on_complete,),
            daemon=True
        )
        self._thread.start()
        return True

    def _run_core(self):
        """Core execution logic of the scraper."""
        ec = GuiECourtSession(on_image_callback=self.on_image)
        self.log(f"Establishing session...\n")
        ec.s.get(BASE_URL, timeout=30)
        
        self.log(f"Solving captcha...\n")
        court_code = ""
        if self.court:
            court_code = str(COURT_NAMES.get(self.court.lower(), ""))
            if not court_code:
                for name, code in COURT_NAMES.items():
                    if self.court.lower() in name.lower():
                        court_code = str(code)
                        break
        
        captcha_text, token = ec.solve_captcha(search_text=self.search_term, search_opt="PHRASE")
        self.log(f"Loading search page...\n")
        ec.load_results_page(self.search_term, mode="PHRASE")

        # Warmup and download page loops
        page_size = min(self.count, 25)
        for _ in range(3):
            ec.get_results(
                self.search_term, page=0, page_size=page_size, mode="PHRASE",
                state_code=court_code, from_date=self.from_date, to_date=self.to_date
            )
        
        entries, total = ec.get_results(
            self.search_term, page=0, page_size=page_size, mode="PHRASE",
            state_code=court_code, from_date=self.from_date, to_date=self.to_date
        )
        
        self.log(f"\nTotal matching: {total}\n")
        
        out_path = os.path.join(self.output_dir, self.search_term.lower().replace(" ", "_"))
        if not os.path.exists(out_path):
            os.makedirs(out_path, exist_ok=True)
            
        self.log(f"Downloading to {out_path}...\n")
        dl_count = 0
        for e in entries:
            cnr = e.get("cnr", "").replace("/", "_").replace(" ", "_")
            if not cnr or cnr == "N/A":
                cnr = "judgment_%d" % (hash(e.get("path", "")) % 1000000)
            
            filename = os.path.join(out_path, cnr + ".pdf")
            if os.path.exists(filename) and os.path.getsize(filename) > 1000:
                self.log(f"Already downloaded: {cnr}\n")
                dl_count += 1
                continue
                
            self.log(f"Downloading {cnr}...\n")
            url = ec.get_pdf_url(e)
            if url:
                sz = ec.download_pdf(url, filename)
                if sz > 1000:
                    self.log(f"   ✓ OK {os.path.basename(filename)} ({sz} bytes)\n")
                    dl_count += 1
                else:
                    if os.path.exists(filename):
                        try:
                            os.remove(filename)
                        except OSError:
                            pass
            else:
                self.log(f"   ✗ Could not get PDF URL\n")
                
        self.log(f"\nDone! {dl_count} PDFs downloaded.\n")

    def _threaded_run(self, on_complete):
        """Thread worker function that captures stdout/stderr prints."""
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = StdoutRedirector(self.log)
        sys.stderr = StdoutRedirector(self.log)
        try:
            self._run_core()
        except Exception as e:
            self.log(f"\nError running scraper: {e}\n")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self.is_running = False
            if on_complete:
                try:
                    on_complete()
                except Exception:
                    pass

class GuiApp:
    """Tkinter application wrapping the scraper controller into a graphical panel."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("srchigh — eCourts India Scraper Dashboard")
        self.root.geometry("950x680")
        self.root.configure(bg="#1e1e1e")
        
        self.ctrl = GuiController()
        self.ctrl.on_log = self.append_log
        self.ctrl.on_image = self.display_captcha
        
        self.tk_img = None
        self.setup_styles()
        self.create_widgets()
        
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        # Dark themes
        style.configure(".", background="#1e1e1e", foreground="#f0f0f0")
        style.configure("TLabel", background="#1e1e1e", foreground="#f0f0f0", font=("Helvetica", 10))
        style.configure("Header.TLabel", font=("Helvetica", 14, "bold"), foreground="#00adb5")
        style.configure("TEntry", fieldbackground="#333333", foreground="#f0f0f0", insertcolor="#f0f0f0")
        style.configure("TCombobox", fieldbackground="#333333", background="#1e1e1e", foreground="#f0f0f0")
        
        # Primary Action Button
        style.configure("Action.TButton", background="#00adb5", foreground="#ffffff", font=("Helvetica", 10, "bold"))
        style.map("Action.TButton", background=[("active", "#008080")])
        
        # Normal Button
        style.configure("Browse.TButton", background="#444444", foreground="#ffffff")
        style.map("Browse.TButton", background=[("active", "#555555")])

    def create_widgets(self):
        self.root.columnconfigure(0, weight=1, minsize=320)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(0, weight=1)
        
        # Left Panel (Config Forms)
        left_frame = tk.Frame(self.root, bg="#252526", padx=15, pady=15, width=320)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        
        # Right Panel (Logging and Captcha Visualizer)
        right_frame = tk.Frame(self.root, bg="#1e1e1e", padx=10, pady=15)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)
        
        # App Title
        title_label = ttk.Label(left_frame, text="srchigh Scraper GUI", style="Header.TLabel")
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20), sticky="w")
        
        # Search Term Field
        ttk.Label(left_frame, text="Search Term:").grid(row=1, column=0, sticky="w", pady=5)
        self.search_entry = ttk.Entry(left_frame, width=28)
        self.search_entry.grid(row=2, column=0, columnspan=2, sticky="w", pady=2)
        
        # High Court Dropdown
        ttk.Label(left_frame, text="Filter High Court:").grid(row=3, column=0, sticky="w", pady=5)
        courts = [""] + sorted(list(COURT_NAMES.keys()))
        self.court_combo = ttk.Combobox(left_frame, values=courts, width=26, state="readonly")
        self.court_combo.grid(row=4, column=0, columnspan=2, sticky="w", pady=2)
        
        # Download Count
        ttk.Label(left_frame, text="Max Results count:").grid(row=5, column=0, sticky="w", pady=5)
        self.count_spin = tk.Spinbox(left_frame, from_=1, to=200, width=10, bg="#333333", fg="#f0f0f0", buttonbackground="#252526", insertbackground="#f0f0f0")
        self.count_spin.delete(0, "end")
        self.count_spin.insert(0, "5")
        self.count_spin.grid(row=6, column=0, sticky="w", pady=2)
        
        # Date Bounds
        ttk.Label(left_frame, text="Dates Bounds (DD-MM-YYYY):").grid(row=7, column=0, columnspan=2, sticky="w", pady=(15, 5))
        
        ttk.Label(left_frame, text="From Date:", font=("Helvetica", 9)).grid(row=8, column=0, sticky="w")
        self.from_entry = ttk.Entry(left_frame, width=12)
        self.from_entry.grid(row=9, column=0, sticky="w", pady=2)
        
        ttk.Label(left_frame, text="To Date:", font=("Helvetica", 9)).grid(row=8, column=1, sticky="w")
        self.to_entry = ttk.Entry(left_frame, width=12)
        self.to_entry.grid(row=9, column=1, sticky="w", pady=2)
        
        # Download Output Directory
        ttk.Label(left_frame, text="Output Directory:").grid(row=10, column=0, columnspan=2, sticky="w", pady=(20, 5))
        self.dir_entry = ttk.Entry(left_frame, width=20)
        self.dir_entry.insert(0, self.ctrl.output_dir)
        self.dir_entry.grid(row=11, column=0, sticky="w", pady=2)
        
        self.browse_btn = ttk.Button(left_frame, text="Browse", style="Browse.TButton", command=self.browse_directory, width=8)
        self.browse_btn.grid(row=11, column=1, sticky="w", padx=(5, 0), pady=2)
        
        # Trigger button
        self.run_btn = ttk.Button(left_frame, text="Start Scraper", style="Action.TButton", command=self.start_scrape)
        self.run_btn.grid(row=12, column=0, columnspan=2, pady=(35, 0), sticky="ew")

        # Captcha Display Frame
        captcha_frame = tk.LabelFrame(right_frame, text=" Captcha Image ", bg="#1e1e1e", fg="#00adb5", padx=10, pady=5, font=("Helvetica", 10, "bold"))
        captcha_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        self.captcha_label = tk.Label(captcha_frame, text="Waiting for scraper to download captcha...", bg="#1e1e1e", fg="#888888", font=("Helvetica", 10, "italic"))
        self.captcha_label.pack(pady=10)
        
        # Output Terminal Frame
        log_frame = tk.LabelFrame(right_frame, text=" Scraper Output Log ", bg="#1e1e1e", fg="#00adb5", font=("Helvetica", 10, "bold"))
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        
        self.log_text = tk.Text(log_frame, bg="#0d0d0d", fg="#a6e22e", insertbackground="#f8f8f2", font=("Courier New", 10), state="disabled", wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 5), pady=5)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
    def browse_directory(self):
        path = filedialog.askdirectory(initialdir=self.ctrl.output_dir)
        if path:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, path)
            
    def append_log(self, text):
        def append():
            self.log_text.configure(state="normal")
            # Strip out ANSI escape codes (colors) from the printed text
            clean_text = re.sub(r'\033\[[0-9;]*m', '', text)
            self.log_text.insert("end", clean_text)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(0, append)
        
    def display_captcha(self, pil_img):
        def update_image():
            try:
                # Resize image slightly for GUI preview (doubled size)
                w, h = pil_img.size
                try:
                    resample = Image.Resampling.LANCZOS
                except AttributeError:
                    resample = Image.ANTIALIAS
                resized = pil_img.resize((w * 2, h * 2), resample)
                self.tk_img = ImageTk.PhotoImage(resized)
                self.captcha_label.configure(image=self.tk_img, text="")
            except Exception as e:
                self.captcha_label.configure(text=f"Error displaying image: {e}", image="")
        self.root.after(0, update_image)
        
    def start_scrape(self):
        if self.ctrl.is_running:
            return
            
        self.ctrl.search_term = self.search_entry.get()
        self.ctrl.court = self.court_combo.get()
        self.ctrl.from_date = self.from_entry.get()
        self.ctrl.to_date = self.to_entry.get()
        self.ctrl.output_dir = self.dir_entry.get()
        
        try:
            self.ctrl.count = int(self.count_spin.get())
        except ValueError:
            messagebox.showerror("Error", "Max judgments count must be a number.")
            return
            
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.captcha_label.configure(image="", text="Establishing session and downloading captcha...")
        
        self.run_btn.configure(state="disabled", text="Running...")
        self.search_entry.configure(state="disabled")
        self.court_combo.configure(state="disabled")
        self.from_entry.configure(state="disabled")
        self.to_entry.configure(state="disabled")
        self.browse_btn.configure(state="disabled")
        
        started = self.ctrl.run_scraper(on_complete=self.on_scrape_complete)
        if not started:
            self.on_scrape_complete()
            
    def on_scrape_complete(self):
        def reset_ui():
            self.run_btn.configure(state="normal", text="Start Scraper")
            self.search_entry.configure(state="normal")
            self.court_combo.configure(state="normal")
            self.from_entry.configure(state="normal")
            self.to_entry.configure(state="normal")
            self.browse_btn.configure(state="normal")
            
            if self.ctrl.error_message:
                messagebox.showerror("Validation Error", self.ctrl.error_message)
        self.root.after(0, reset_ui)
        
    def run(self):
        self.root.mainloop()

def run_gui():
    app = GuiApp()
    app.run()
