"""
gui.py

Janela nativa (Tkinter) mostrando, ao vivo, o status de display affinity
de todas as janelas visiveis do sistema. Nao depende do servidor FastAPI
nem de navegador -- usa o AffinityMonitor diretamente.

Requisitos: so a stdlib (tkinter ja vem com o Python no Windows).

Rodar:
    python gui.py

Empacotar como .exe:
    pyinstaller --onefile --windowed --name AffinityDetector gui.py
"""

import csv
import json
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from affinity_core import AffinityMonitor

REFRESH_MS = 1000  # intervalo de atualizacao da tabela quando monitorando


class AffinityGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.monitor = AffinityMonitor(poll_interval=1.0)
        self.running = False
        self._refresh_job = None

        root.title("Display Affinity Detector")
        root.geometry("920x520")
        root.configure(bg="#1e1e1e")
        root.minsize(700, 380)

        self._build_toolbar()
        self._build_status_bar()
        self._build_table()

        # comeca monitorando automaticamente ao abrir
        self.start_monitoring()

    # ---------------------------------------------------------------
    # Construcao da UI
    # ---------------------------------------------------------------

    def _build_toolbar(self):
        toolbar = tk.Frame(self.root, bg="#1e1e1e")
        toolbar.pack(fill="x", padx=10, pady=(10, 0))

        self.toggle_btn = tk.Button(
            toolbar, text="Parar monitoramento", command=self.toggle_monitoring,
            bg="#c0392b", fg="#ffffff", activebackground="#e74c3c",
            font=("Segoe UI", 10, "bold"), relief="flat", padx=12, pady=6,
            cursor="hand2"
        )
        self.toggle_btn.pack(side="left")

        export_btn = tk.Button(
            toolbar, text="Exportar snapshot", command=self.export_snapshot,
            bg="#2d2d30", fg="#dcdcdc", activebackground="#3e3e42",
            font=("Segoe UI", 10), relief="flat", padx=12, pady=6,
            cursor="hand2"
        )
        export_btn.pack(side="left", padx=(8, 0))

        self.led = tk.Canvas(toolbar, width=14, height=14, bg="#1e1e1e", highlightthickness=0)
        self.led_dot = self.led.create_oval(2, 2, 12, 12, fill="#2ecc71", outline="")
        self.led.pack(side="right", padx=(0, 4))
        tk.Label(
            toolbar, text="monitorando", bg="#1e1e1e", fg="#888888",
            font=("Segoe UI", 9)
        ).pack(side="right")

    def _build_status_bar(self):
        self.status_var = tk.StringVar(value="Iniciando monitoramento...")
        status_label = tk.Label(
            self.root, textvariable=self.status_var,
            bg="#1e1e1e", fg="#cccccc", anchor="w",
            font=("Segoe UI", 10)
        )
        status_label.pack(fill="x", padx=10, pady=(8, 0))

    def _build_table(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background="#252526", fieldbackground="#252526",
            foreground="#dcdcdc", rowheight=26, font=("Segoe UI", 10)
        )
        style.configure(
            "Treeview.Heading",
            background="#333333", foreground="#ffffff",
            font=("Segoe UI", 10, "bold")
        )
        style.map("Treeview", background=[("selected", "#094771")])

        columns = ("titulo", "pid", "affinity", "protegida")
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings")
        self.tree.heading("titulo", text="Janela")
        self.tree.heading("pid", text="PID")
        self.tree.heading("affinity", text="Affinity")
        self.tree.heading("protegida", text="Status")

        self.tree.column("titulo", width=440, anchor="w")
        self.tree.column("pid", width=80, anchor="center")
        self.tree.column("affinity", width=220, anchor="w")
        self.tree.column("protegida", width=140, anchor="center")

        self.tree.tag_configure("protegida", background="#4a1414", foreground="#ff8080")
        self.tree.tag_configure("normal", background="#252526", foreground="#dcdcdc")

        self.tree.pack(fill="both", expand=True, padx=10, pady=10)

    # ---------------------------------------------------------------
    # Controle de monitoramento
    # ---------------------------------------------------------------

    def start_monitoring(self):
        if self.running:
            return
        self.monitor.start()
        self.running = True
        self.toggle_btn.config(text="Parar monitoramento", bg="#c0392b", activebackground="#e74c3c")
        self.led.itemconfig(self.led_dot, fill="#2ecc71")
        self._schedule_refresh()

    def stop_monitoring(self):
        if not self.running:
            return
        self.monitor.stop()
        self.running = False
        self.toggle_btn.config(text="Iniciar monitoramento", bg="#2e7d32", activebackground="#388e3c")
        self.led.itemconfig(self.led_dot, fill="#666666")
        self.status_var.set("Monitoramento pausado. Tabela mostra o ultimo estado capturado.")
        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
            self._refresh_job = None

    def toggle_monitoring(self):
        if self.running:
            self.stop_monitoring()
        else:
            self.start_monitoring()

    # ---------------------------------------------------------------
    # Atualizacao da tabela
    # ---------------------------------------------------------------

    def _schedule_refresh(self):
        self._refresh()
        if self.running:
            self._refresh_job = self.root.after(REFRESH_MS, self._schedule_refresh)

    def _refresh(self):
        windows = self.monitor.snapshot()
        protected_count = sum(1 for w in windows if w["protected"])

        self.tree.delete(*self.tree.get_children())
        windows.sort(key=lambda w: (not w["protected"], w["title"].lower()))

        for w in windows:
            tag = "protegida" if w["protected"] else "normal"
            status = "PROTEGIDA" if w["protected"] else "livre"
            self.tree.insert(
                "", "end",
                values=(w["title"], w["pid"], w["affinity_name"], status),
                tags=(tag,)
            )

        self.status_var.set(
            f"{len(windows)} janela(s) monitorada(s)  |  "
            f"{protected_count} protegida(s) contra captura"
        )

    # ---------------------------------------------------------------
    # Exportar
    # ---------------------------------------------------------------

    def export_snapshot(self):
        windows = self.monitor.snapshot()
        if not windows:
            messagebox.showinfo("Exportar", "Nenhuma janela capturada ainda.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("JSON", "*.json")],
            initialfile=f"affinity_snapshot_{int(time.time())}"
        )
        if not path:
            return

        try:
            if path.lower().endswith(".json"):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(windows, f, indent=2, ensure_ascii=False)
            else:
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=list(windows[0].keys()))
                    writer.writeheader()
                    writer.writerows(windows)
            messagebox.showinfo("Exportar", f"Snapshot salvo em:\n{path}")
        except Exception as e:
            messagebox.showerror("Erro ao exportar", str(e))

    # ---------------------------------------------------------------

    def on_close(self):
        if self.running:
            self.monitor.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = AffinityGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
