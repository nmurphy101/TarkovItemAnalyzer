#!/usr/bin/env python3

"""
    Tarkov Item Price Analyzer - Gui App
    ~~~~~~~~~~

    Tkinter GUI main application for the program.

    :copyright: (c) 2021 by Nicholas Murphy.
    :license: GPLv2, see LICENSE for more details.
"""

import threading
import psutil
import queue as q
import tkinter as Tk
from tkinter import messagebox, Toplevel, Text, INSERT, Button, Label, TclError
from pubsub import pub
from .TIPA import ProcessManager

class App:
    """
    App
    ~~~~~~~~~~

    Gui for the Application.
    """
    def __init__(self, parent, cmd_queue, title):
        self.cmd_queue = cmd_queue
        self.root = parent
        self.root.title(title)
        self.root.protocol("WM_DELETE_WINDOW", self.onClose)
        # Menu bar
        self.menuFrame = Tk.Frame(self.root)
        self.menuFrame.pack()
        self.menuFrame.grid()
        # Main body content
        self.bodyFrame = Tk.Frame(self.root)
        self.bodyFrame.grid()
        self.widgets = []
        

        self.settings_btn = Button(self.menuFrame, text="Settings",
                              command=lambda SettingsMenu=SettingsMenu:
                              self.openFrame(SettingsMenu))
        self.settings_btn.pack(expand=1, fill='both')

        pub.subscribe(self.listener, "otherFrameClosed")

    def onClose(self):
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            # Tell the connected program doing background work to quit
            self.cmd_queue.put("quit")
            # Quit the gui app
            self.root.destroy()

    def listener(self):
        """
        pubsub listener - opens main frame when otherFrame closes
        """
        self.lockFrame(False)
        # self.show()

    def hide(self):
        """
        hides main frame
        """
        self.root.withdraw()

    def lockFrame(self, enable):
        """
        locks or unlocks the main frame
        """
        if enable:
            state_str = "disable"
        else:
            state_str = "active"
        for child in self.menuFrame.winfo_children():
            try:
                child.configure(state=state_str)
            except TclError as e:
                pass

    def openFrame(self, sub_frame_class):
        """
        opens other frame and hides main frame
        """
        self.lockFrame(True)
        # self.hide()
        _ = sub_frame_class()

    def show(self):
        """
        shows main frame
        """
        self.root.update()
        self.root.deiconify()

class OtherFrame(Tk.Toplevel):
    """
    OtherFrame
    ~~~~~~~~~~

    extra menu.
    """
    def __init__(self, title):
        super(OtherFrame, self).__init__()
        self.geometry("400x300")
        self.title(title)
        self.protocol("WM_DELETE_WINDOW", self.onClose)
        # self.withdraw()

        # create the button
        close_btn = Tk.Button(self, text="Close", command=self.onClose)
        close_btn.pack()

    def onClose(self):
        """
        closes the frame and sends a message to the main frame
        """
        self.destroy()
        pub.sendMessage("otherFrameClosed")

class GUI(App):
    def __init__(self, parent, gui_queue, cmd_queue, title):
        super(GUI, self).__init__(parent, cmd_queue, title)
        self.alive_time = 6000
        self.gui_queue = gui_queue
        self.p_Manager = ProcessManager(self.gui_queue, self.cmd_queue)
        #Buttons
        self.start_btn = Button(self.menuFrame, text="Start",
                              command=self.startProcessManager)
        self.start_btn.pack(expand=1, fill='both')
        self.stop_btn = Button(self.menuFrame, text="Stop",
                              command=self.stopProcessManager)
        self.stop_btn.pack(expand=1, fill='both')
        self.stop_btn.config(state="disabled")

    def queueLoop(self):
        thread = threading.Thread(target=self.popAlwaysOnTop)
        thread.start()
        self.checkStatus(thread)

    def checkStatus(self, thread):
        if thread.is_alive():
            self.menuFrame.after(200, lambda thread=thread: self.checkStatus(thread))
        else:
            self.menuFrame.after(500, self.queueLoop)
    
    def startProcessManager(self):
        if "EscapeFromTarkov.exe" in (p.name() for p in psutil.process_iter()):
            if not self.p_Manager.is_alive():
                # Activate main process manager thread
                self.p_Manager.start()
                self.menuFrame.after(100, self.queueLoop)
            #
            self.settings_btn.config(state="disabled")
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
        else:
            label = Label(self.menuFrame, text="ExcapeFromTarkov is not running")
            label.pack()
            # logging.warning('EscapeFromTarkov is not running')
    def stopProcessManager(self):
        if self.p_Manager.is_alive():
            # Close main process manager thread
            self.p_Manager.Close()
            # Create a new process manager thread waiting to be started
            self.p_Manager = ProcessManager(self.gui_queue, self.cmd_queue)
            self.settings_btn.config(state="normal")
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
        else:
            label = Label(self.bodyFrame, text="Analyzer already stopped")
            label.pack()
            # logging.warning('EscapeFromTarkov is not running')

    def popAlwaysOnTop(self):
        #
        try:
            item = self.gui_queue.get(timeout=1)
        except q.Empty:
            item = None
        
        if item:
            msg = item[0]
            display_info = item[1]

            widget = Toplevel()
            widget.wm_attributes('-alpha', 0.75)
            
            display_info_keys = display_info.keys()
            # If width and height isn't included let tkinter decide
            if "w" in display_info_keys and "h" in display_info_keys:
                widget.geometry(('%dx%d+%d+%d' % (display_info["w"], display_info["h"], 
                                                display_info["x"], display_info["y"])))
            else:
                widget.geometry(('+%d+%d' % (display_info["x"], display_info["y"])))
            # Overlay widget settings
            widget.attributes('-topmost', True)
            widget.overrideredirect(True)
            # Overlay message settings
            msg_text = Text(widget, font=("Ariel", 12))
            msg_text.insert(INSERT, str("\n"+msg))
            msg_text.pack(expand=1, fill='both')
            # Create a Button
            # btn = Button(widget, text = 'Skip', bd = '5', command = widget.destroy)  
            # # Set the position of button on the bottom of window.    
            # btn.pack(expand=1, fill='none')
            # Add to the window grid 
            widget.grid_propagate(0)
            widget.after(6000, widget.destroy())
            # widget.after(self.alive_time, lambda: widget.withdraw())
            # widgets.append(widget)

class SettingsMenu(OtherFrame):
    """
    SettingsMenu
    ~~~~~~~~~~

    Gui frame for selecting settings.
    """
    TITLE = "Settings"
    def __init__(self):
        super(SettingsMenu, self).__init__(SettingsMenu.TITLE)
