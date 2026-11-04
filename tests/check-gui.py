#!/usr/bin/env python3
"""Exercise real Tk buttons and the original guest; run with xvfb-run -a."""
import importlib.util
import json
from pathlib import Path
import time
import tkinter as tk

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('a7m3_camera', ROOT/'scripts/camera.py')
camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)
real_tk = tk.Tk
original = set((ROOT/'output').glob('*'))
state = {'step': 0, 'started': time.monotonic(), 'error': None, 'run': None}


def create():
    root = real_tk()
    def tick():
        try:
            runs = set((ROOT/'output').glob('*'))-original
            if runs:
                state['run'] = sorted(runs)[-1]
            buttons = {item.cget('text'): item
                for frame in root.winfo_children() if isinstance(frame, tk.Frame)
                for item in frame.winfo_children() if isinstance(item, tk.Button)}
            step, run = state['step'], state['run']
            if time.monotonic()-state['started'] > 180:
                raise TimeoutError('GUI verification timed out')
            if step == 0 and run and (run/'main.png').exists() and buttons.get('MENU') and buttons['MENU'].cget('state') == 'normal':
                assert root.winfo_width() >= 640 and root.winfo_height() >= 480
                buttons['MENU'].invoke()
                state['step'] = 1
            elif step == 1 and run and list(run.glob('menu-*.png')) and buttons['确认'].cget('state') == 'normal':
                buttons['确认'].invoke()
                state['step'] = 2
            elif step == 2 and run and list(run.glob('enter-*.png')) and buttons['返回'].cget('state') == 'normal':
                buttons['返回'].invoke()
                state['step'] = 3
            elif step == 3 and run and list(run.glob('back-*.png')) and buttons['MENU'].cget('state') == 'normal':
                state['step'] = 4
                root.tk.call(root.protocol('WM_DELETE_WINDOW'))
                return
        except Exception as error:
            state['error'] = str(error)
            root.tk.call(root.protocol('WM_DELETE_WINDOW'))
            return
        root.after(200, tick)
    root.after(200, tick)
    return root


tk.Tk = create
camera.window()
report = {'passed': state['step'] == 4 and not state['error'],
    'actions': ['native main', 'MENU button', 'ENTER button', 'Back button', 'WM_DELETE_WINDOW'],
    'run': str(state['run']), 'error': state['error']}
path = ROOT/'evidence/gui-validation.json'
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
assert report['passed']
