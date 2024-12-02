#!/usr/bin/env python3

'''
    Tarkov Item Price Analyzer - Gui App
    ~~~~~~~~~~

    Tkinter GUI main application for the program.

    :copyright: (c) 2021 by Nicholas Murphy.
    :license: GPLv2, see LICENSE for more details.
'''

import json
import os
import queue as q
import threading
from collections import deque
from datetime import datetime as time, timedelta

import psutil
import pytesseract
import tkinter as Tk
from pubsub import pub
from tkinter import Button, Label, messagebox, OptionMenu, StringVar, TclError, Toplevel, N, S, E, W

from .TIPA import ProcessManager
from logger_config import logger


if os.path.exists("settings.json"):
    with open("settings.json") as settings_file:
        settings = json.load(settings_file)
        pytesseract.pytesseract.tesseract_cmd = settings.get("tesseract_path", r"D:\Program Files\Tesseract-OCR\tesseract.exe")


class App:
    '''
    App
    ~~~~~~~~~~

    Gui for the Application.
    '''
    def __init__(self, parent, cmd_queue, title):
        self.cmd_queue = cmd_queue
        # Root app
        self.root = parent
        self.root.title(title)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        # Menu bar
        self.menu_frame = Tk.Frame(self.root)
        self.menu_frame.grid(row=0, column=0, pady=2, sticky=W+E+N)
        # Main body content
        self.body_frame = Tk.Frame(self.root)
        self.body_frame.grid(row=1, column=0, pady=2)
        self.body_frame.columnconfigure(0, weight=1)
        self.body_frame.rowconfigure(1, weight=1)

        # Initilize buttons
        self.settings_btn = Button(self.menu_frame, text="Settings",
                                   command=lambda SettingsMenu=SettingsMenu:
                                   self.open_frame(SettingsMenu))
        self.settings_btn.grid(row=0, column=0)

        # Pub messaging
        pub.subscribe(self.listener, "otherFrameClosed")

    def on_close(self) -> None:
        '''
        dialogue to make sure user wants to quit and sends message into the command queue to 
        quit the app, then destroy the root gui app
        '''
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            # Tell the connected program doing background work to quit
            self.cmd_queue.put("quit")
            # Quit the gui app
            self.root.destroy()

    def listener(self) -> None:
        '''
        pubsub listener - opens main frame when otherFrame closes
        '''
        self.lock_frame(False)

    def hide(self) -> None:
        '''
        hides main frame
        '''
        self.root.withdraw()

    def lock_frame(self, enable) -> None:
        '''
        locks or unlocks the main frame
        '''
        if enable:
            state_str = "disable"
        else:
            state_str = "active"
        for child in self.menu_frame.winfo_children():
            try:
                child.configure(state=state_str)
            except TclError:
                pass

    def open_frame(self, sub_frame_class) -> None:
        '''
        opens other frame and hides main frame
        '''
        self.lock_frame(True)
        _ = sub_frame_class()

    def show(self) -> None:
        '''
        shows main frame
        '''
        self.root.update()
        self.root.deiconify()


class OtherFrame(Tk.Toplevel):
    '''
    OtherFrame
    ~~~~~~~~~~

    extra menu.
    '''
    def __init__(self, title):
        super(OtherFrame, self).__init__()
        self.geometry("400x300")
        self.title(title)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        # Menu bar
        self.menu_frame = Tk.Frame(self)
        self.menu_frame.grid(row=0, column=0, pady=2, sticky=W+E+N)

        # create the button
        self.close_btn = Tk.Button(self, text="Close", command=self.on_close)
        self.close_btn.grid(row=1, column=0, sticky=W+E+N)

    def on_close(self) -> None:
        '''
        closes the frame and sends a message to the main frame
        '''
        self.destroy()
        pub.sendMessage("otherFrameClosed")


class GUI(App):
    '''
    GUI
    ~~~~~~~~~~

    main gui app.
    '''
    
    MAX_HISTORY_ITEMS = 5

    def __init__(self, parent, gui_queue, cmd_queue, title):
        super(GUI, self).__init__(parent, cmd_queue, title)
        # Base Settings
        parent.minsize(300, 90)
        parent.maxsize(1000, 800)
        self.alive_time = 6000
        self.since_last_popup = time.now()
        self.gui_queue = gui_queue
        self.p_manager = ProcessManager(self.gui_queue, self.cmd_queue)
        self.popup_widget = Toplevel()
        self.popup_widget.withdraw()

        # Buttons
        self.start_btn = Button(self.menu_frame, text="Start",
                                command=self.start_process_manager)
        self.start_btn.grid(row=0, column=1, sticky=W+N)
        self.stop_btn = Button(self.menu_frame, text="Stop",
                               command=self.stop_process_manager)
        self.stop_btn.grid(row=0, column=2, sticky=W+N)
        self.start_btn.config(state="disabled")
        self.settings_btn.config(state="disabled")

        # History list content
        self.history_frame = Tk.LabelFrame(self.body_frame, text="Item History", padx=5, pady=5)
        self.history_frame.grid(row=2, column=0, columnspan=5, padx=10, pady=10, sticky=E+W+N+S)
        self.history_items: deque[tuple[Tk.LabelFrame, Label]] = deque(maxlen=self.MAX_HISTORY_ITEMS)
        self.history_frame.rowconfigure(0, weight=1)
        self.history_frame.columnconfigure(0, weight=1)

        pub.subscribe(self.settingsMenulistener, "otherFrameClosed")
        pub.subscribe(self.restartRequiredListener, "RestartRequired")

        self.p_manager.start()
        self.menu_frame.after(100, self.queue_loop)

    def queue_loop(self) -> None:
        '''
        starts the thread for poping a message
        '''
        thread = threading.Thread(target=self.popup)
        thread.start()
        self.check_status(thread)

    def check_status(self, thread) -> None:
        '''
        shows main frame
        '''
        if thread.is_alive():
            self.menu_frame.after(200, lambda thread=thread: self.check_status(thread))
        else:
            self.menu_frame.after(500, self.queue_loop)

    def settingsMenulistener(self) -> None:
        '''
        listener for the settings menu
        '''
        self.start_btn.config(state="normal")
        self.settings_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def restartRequiredListener(self) -> None:
        '''
        listener for the restart required message
        '''
        label = Label(self.body_frame, text="tesseract_path has been changed, please restart the application")
        label.grid(row=0, column=0, pady=2)
        self.body_frame.update()
        self.start_btn.config(state="disabled")
        self.settings_btn.config(state="disabled")
        self.stop_btn.config(state="disabled")

    def start_process_manager(self) -> None:
        '''
        starts the TIPA manager thread if tarkov is running
        '''
        if self.is_tarkov_running():
            self.p_manager.resumeEvent.set()
            self.settings_btn.config(state="disabled")
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
        else:
            label = Label(self.body_frame, text="EscapeFromTarkov.exe is not running")
            label.grid(row=0, column=0, pady=2)
            self.body_frame.after(self.alive_time-100, lambda: label.destroy())
            self.body_frame.update()

    def stop_process_manager(self) -> None:
        '''
        stops the TIPA manager process, and ready's a new manager thread
        '''
        if self.p_manager.is_alive():
            self.p_manager.listen = False
            self.settings_btn.config(state="normal")
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
        else:
            label = Label(self.body_frame, text="Analyzer is not running")
            label.grid(row=0, column=0, pady=2)
            self.body_frame.after(self.alive_time-100, lambda: label.destroy())
            self.body_frame.update()

    def popup(self) -> None:
        '''
        Pops a message overlay on the screen if one exists in the queue.
        '''
        if time.now() > self.since_last_popup + timedelta(seconds=self.alive_time / 1000):
            try:
                message_item = self.gui_queue.get(timeout=1)
            except q.Empty:
                message_item = None
        else:
            message_item = None

        if message_item and "ERROR" not in message_item[0]:
            logger.debug(f"item: {message_item}")
            self.add_to_history(message_item)

            msg = message_item[0]
            logger.debug(f"Popping up message: {msg}")

            self.popup_widget.geometry('+0+0')
            self.popup_widget.attributes('-topmost', True)
            self.popup_widget.overrideredirect(True)

            label = Label(self.popup_widget, text=f"\n{msg}")
            label.grid(row=0, column=0, pady=2)

            self.popup_widget.update()
            self.popup_widget.deiconify()

            self.popup_widget.after(self.alive_time, self.popup_widget.withdraw)
            self.popup_widget.after(self.alive_time - 100, label.destroy)

            self.since_last_popup = time.now()

            logger.debug("--Displayed popup--")
        
        elif message_item and "ERROR" in message_item[0]:
            label = Label(self.body_frame, text=message_item[0])
            label.grid(row=0, column=0, pady=2)
            self.body_frame.after(self.alive_time-100, lambda: label.destroy())
            self.body_frame.update()

    def add_to_history(self, message_item) -> None:
        '''
        adds a message to the main apps window that doesn't expire like the popup
        '''
        msg = message_item[0]
        logger.debug(f"Adding to history: {msg}")

        # Clear previous history items
        for item_frame, label in self.history_items:
            item_frame.forget()
            label.forget()

        # Create new history item
        item_frame = Tk.LabelFrame(self.history_frame, text="", padx=2, pady=2)
        label = Label(item_frame, text=str("\n"+msg))
        self.history_items.appendleft((item_frame, label))

        # Update the history display
        for idx, (item_frame, label) in enumerate(self.history_items):
            item_frame.grid(row=idx, column=0, sticky=E+W)
            label.grid(row=0, column=0)

        logger.debug("--Updated History--")

    def is_tarkov_running(self) -> bool:
        try:
            return any(
                p.name().lower() == "escapefromtarkov.exe"
                for p in psutil.process_iter(['name'])
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            logger.warning("Failed to properly check if Tarkov is running")
            return False


class SettingsMenu(OtherFrame):
    '''
    SettingsMenu
    ~~~~~~~~~~

    Gui frame for selecting settings.
    '''
    TITLE = "Settings"
    def __init__(self):
        super(SettingsMenu, self).__init__(SettingsMenu.TITLE)

        self.restart_required = False

        # Menu bar
        self.menu_frame = Tk.Frame(self)
        self.menu_frame.grid(row=0, column=0, pady=2, sticky=W+E+N)

        # Create the button
        self.close_btn = Tk.Button(self, text="Close", command=self.on_close)
        self.close_btn.grid(row=1, column=0, sticky=W+E+N)

        # Create a label and text box for the Tesseract path
        self.tesseract_label = Tk.Label(self, text="Tesseract Path:")
        self.tesseract_label.grid(row=2, column=0, sticky=W)
        self.tesseract_path_entry = Tk.Entry(self, width=50)
        self.tesseract_path_entry.grid(row=2, column=1, sticky=W+E)

        # Create a label and dropdown for the debug level
        self.debug_level_label = Tk.Label(self, text="Debug Level:")
        self.debug_level_label.grid(row=3, column=0, sticky=W)
        self.debug_level_var = StringVar(self)
        self.debug_level_var.set("INFO")  # Default value
        self.debug_level_options = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        self.debug_level_menu = OptionMenu(self, self.debug_level_var, *self.debug_level_options)
        self.debug_level_menu.grid(row=3, column=1, sticky=W+E)

        # Load settings from the JSON file
        self.load_settings()

        # Create a save button
        self.save_btn = Tk.Button(self, text="Save", command=self.save_settings)
        self.save_btn.grid(row=4, column=0, columnspan=2, sticky=W+E+N)

    def update_settings(self, settings) -> None:
        # Update the settings from the text box
        pytesseract.pytesseract.tesseract_cmd = settings.get("tesseract_path", r"D:\Program Files\Tesseract-OCR\tesseract.exe")
        logger.setLevel(settings.get("debug_level", "INFO"))

    def load_settings(self) -> None:
        # Check if the settings file exists
        if os.path.exists("settings.json"):
            with open("settings.json") as settings_file:
                settings = json.load(settings_file)
                tesseract_path = settings.get("tesseract_path", "")
                self.tesseract_path_entry.insert(0, tesseract_path)
                debug_level = settings.get("debug_level", "INFO")
                self.debug_level_var.set(debug_level)

        self.update_settings(settings)

    def save_settings(self) -> None:
        # Get the form values
        tesseract_path = self.tesseract_path_entry.get()
        debug_level = self.debug_level_var.get()

        # Create a dictionary to hold the settings
        settings = {
            "tesseract_path": tesseract_path,
            "debug_level": debug_level,
        }

        # Load the settings from the JSON file
        if os.path.exists("settings.json"):
            with open("settings.json", "r") as settings_file:
                old_settings = json.load(settings_file)
                old_tesseract_path = old_settings.get("tesseract_path", "")
        else:
            old_tesseract_path = ""

        # Save the updated settings to the JSON file
        with open("settings.json", "w") as settings_file:
            json.dump(settings, settings_file, indent=4)

        self.update_settings(settings)

        # Optionally, show a message box to confirm the save
        if tesseract_path != old_tesseract_path:
            messagebox.showinfo("Settings", "Settings saved successfully!\nPlease restart the application to apply the changes.")
            self.restart_required = True
        else:
            messagebox.showinfo("Settings", "Settings saved successfully!")

    def on_close(self) -> None:
        super().on_close()
        if self.restart_required:
            pub.sendMessage("RestartRequired")
