"""Small Tk forms for the Jukebox menu.

Runs as a separate process (the editor's own python.exe) so Tk never touches the editor
process. Prints the result as JSON on stdout; prints nothing if cancelled.

    jukebox_dialog.py create '<json: {"existing": [...], "author": "..."}>'
    jukebox_dialog.py choose '<json: {"title": "...", "items": [...]}>'
"""
import json
import re
import sys
import tkinter as tk
from tkinter import messagebox, ttk

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def _window(title):
    root = tk.Tk()
    root.title(title)
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.after(50, lambda: (root.lift(), root.focus_force()))
    return root


def _center(root):
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    root.geometry("+{}+{}".format((root.winfo_screenwidth() - w) // 2, (root.winfo_screenheight() - h) // 3))


def create(opts):
    existing = {n.lower() for n in opts.get("existing", [])}
    root = _window("Create Jukebox Mod")
    frm = ttk.Frame(root, padding=16)
    frm.grid()
    ttk.Label(frm, text="Creates a new mod that adds your own heist music to the jukebox.",
              wraplength=380).grid(column=0, row=0, columnspan=2, sticky="w", pady=(0, 12))

    fields = [("Mod name", "name", "", "Letters, numbers and _ only (no spaces)"),
              ("Author", "author", opts.get("author", ""), ""),
              ("Description", "description", "Custom heist music", ""),
              ("Version", "version", "1.0.0", "")]
    vars_ = {}
    r = 1
    for label, key, default, hint in fields:
        ttk.Label(frm, text=label).grid(column=0, row=r, sticky="w", padx=(0, 8), pady=3)
        v = tk.StringVar(value=default)
        e = ttk.Entry(frm, textvariable=v, width=42)
        e.grid(column=1, row=r, sticky="we", pady=3)
        if key == "name":
            e.focus_set()
        vars_[key] = v
        r += 1
        if hint:
            ttk.Label(frm, text=hint, foreground="#777").grid(column=1, row=r, sticky="w")
            r += 1

    result = {}

    def ok(*_):
        name = vars_["name"].get().strip()
        if not NAME_RE.match(name):
            messagebox.showerror("Create Jukebox Mod", "The mod name must start with a letter and use only "
                                 "letters, numbers and _ (no spaces).", parent=root)
            return
        if name.lower() in existing:
            messagebox.showerror("Create Jukebox Mod", "A mod called '{}' already exists.".format(name), parent=root)
            return
        result.update({k: v.get().strip() for k, v in vars_.items()})
        root.destroy()

    btns = ttk.Frame(frm)
    btns.grid(column=0, row=r, columnspan=2, sticky="e", pady=(14, 0))
    ttk.Button(btns, text="Cancel", command=root.destroy).grid(column=0, row=0, padx=4)
    ttk.Button(btns, text="Create Mod", command=ok).grid(column=1, row=0)
    root.bind("<Return>", ok)
    root.bind("<Escape>", lambda *_: root.destroy())
    _center(root)
    root.mainloop()
    return result or None


def choose(opts):
    items = opts.get("items", [])
    root = _window(opts.get("title", "Choose"))
    frm = ttk.Frame(root, padding=16)
    frm.grid()
    ttk.Label(frm, text=opts.get("prompt", "Choose a mod:")).grid(column=0, row=0, sticky="w", pady=(0, 6))
    lb = tk.Listbox(frm, height=min(12, max(4, len(items))), width=40, activestyle="dotbox")
    for it in items:
        lb.insert("end", it)
    lb.grid(column=0, row=1, sticky="we")
    if items:
        lb.selection_set(0)
    lb.focus_set()
    result = {}

    def ok(*_):
        sel = lb.curselection()
        if sel:
            result["choice"] = items[sel[0]]
            root.destroy()

    lb.bind("<Double-Button-1>", ok)
    btns = ttk.Frame(frm)
    btns.grid(column=0, row=2, sticky="e", pady=(12, 0))
    ttk.Button(btns, text="Cancel", command=root.destroy).grid(column=0, row=0, padx=4)
    ttk.Button(btns, text="OK", command=ok).grid(column=1, row=0)
    root.bind("<Return>", ok)
    root.bind("<Escape>", lambda *_: root.destroy())
    _center(root)
    root.mainloop()
    return result or None


if __name__ == "__main__":
    mode, opts = sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    res = {"create": create, "choose": choose}[mode](opts)
    if res:
        sys.stdout.write(json.dumps(res))
