#!/usr/bin/env python3

'''
    Tarkov Item Price Analyzer - Gui App
    ~~~~~~~~~~

    Tkinter GUI main application for the program.

    :copyright: (c) 2021 by Nicholas Murphy.
    :license: GPLv2, see LICENSE for more details.
'''


import threading
from datetime import datetime as time
from datetime import timedelta 
import queue as q
import tkinter as Tk
from tkinter import messagebox, Toplevel, Text, INSERT, Button, Label, TclError
import psutil
from pubsub import pub
from .TIPA import ProcessManager


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
        self.menu_frame.pack()
        self.menu_frame.grid()
        # Main body content
        self.body_frame = Tk.Frame(self.root)
        self.body_frame.grid()
        self.widgets = []

        # Initilize buttons
        self.settings_btn = Button(self.menu_frame, text="Settings",
                                   command=lambda SettingsMenu=SettingsMenu:
                                   self.open_frame(SettingsMenu))
        self.settings_btn.pack(expand=1, fill='both')

        # Pub messaging
        pub.subscribe(self.listener, "otherFrameClosed")

    def on_close(self):
        '''
        dialogue to make sure user wants to quit and sends message into the command queue to 
        quit the app, then destroy the root gui app
        '''
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            # Tell the connected program doing background work to quit
            self.cmd_queue.put("quit")
            # Quit the gui app
            self.root.destroy()

    def listener(self):
        '''
        pubsub listener - opens main frame when otherFrame closes
        '''
        self.lock_frame(False)
        # self.show()

    def hide(self):
        '''
        hides main frame
        '''
        self.root.withdraw()

    def lock_frame(self, enable):
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

    def open_frame(self, sub_frame_class):
        '''
        opens other frame and hides main frame
        '''
        self.lock_frame(True)
        # self.hide()
        _ = sub_frame_class()

    def show(self):
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
        # self.withdraw()

        # create the button
        close_btn = Tk.Button(self, text="Close", command=self.on_close)
        close_btn.pack()

    def on_close(self):
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
    def __init__(self, parent, gui_queue, cmd_queue, title):
        super(GUI, self).__init__(parent, cmd_queue, title)
        self.alive_time = 6000
        self.since_last_popup = time.now()
        self.gui_queue = gui_queue
        self.p_manager = ProcessManager(self.gui_queue, self.cmd_queue)
        self.popup_widget = Toplevel()
        self.popup_widget.withdraw()
        #Buttons
        self.start_btn = Button(self.menu_frame, text="Start",
                                command=self.start_process_manager)
        self.start_btn.pack(expand=1, fill='both')
        self.stop_btn = Button(self.menu_frame, text="Stop",
                               command=self.stop_process_manager)
        self.stop_btn.pack(expand=1, fill='both')
        self.stop_btn.config(state="disabled")

    def queue_loop(self):
        '''
        starts the thread for poping a message
        '''
        thread = threading.Thread(target=self.popup)
        thread.start()
        self.check_status(thread)

    def check_status(self, thread):
        '''
        shows main frame
        '''
        if thread.is_alive():
            self.menu_frame.after(200, lambda thread=thread: self.check_status(thread))
        else:
            self.menu_frame.after(500, self.queue_loop)

    def start_process_manager(self):
        '''
        starts the TIPA manager thread if tarkov is running
        '''
        if "EscapeFromTarkov.exe" in (p.name() for p in psutil.process_iter()):
            if not self.p_manager.is_alive():
                # Activate main process manager thread
                self.p_manager.start()
                self.menu_frame.after(100, self.queue_loop)
            #
            self.settings_btn.config(state="disabled")
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
        else:
            label = Label(self.menu_frame, text="ExcapeFromTarkov is not running")
            label.pack()
            # logging.warning('EscapeFromTarkov is not running')
    def stop_process_manager(self):
        '''
        stops the TIPA manager process, and ready's a new manager thread
        '''
        if self.p_manager.is_alive():
            # Close main process manager thread
            self.p_manager.Close()
            # Create a new process manager thread waiting to be started
            self.p_manager = ProcessManager(self.gui_queue, self.cmd_queue)
            self.settings_btn.config(state="normal")
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
        else:
            label = Label(self.body_frame, text="Analyzer already stopped")
            label.pack()
            # logging.warning('EscapeFromTarkov is not running')

    def pop_always_on_top(self):
        '''
        pops a message overlay on the screen if one exists in the queue
        '''
        #
        try:
            item = self.gui_queue.get(timeout=1)
        except q.Empty:
            item = None

        if item:
            msg = item[0]
            display_info = item[1]
            print("GUI: ", msg)

            widget = Toplevel()
            # widget.wm_attributes('-alpha', 0.75)

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
            # widget.after(6000, widget.destroy())
            # widget.after(self.alive_time, lambda: widget.withdraw())
            # widgets.append(widget)
            print("--Displayed--")

    def popup(self):
        '''
        pops a message overlay on the screen if one exists in the queue
        '''
        if time.now() > self.since_last_popup + timedelta(0, self.alive_time/1000):
            #
            try:
                item = self.gui_queue.get(timeout=1)
            except q.Empty:
                item = None
        else:
            item = None

        if item:
            msg = item[0]
            display_info = item[1]
            print("GUI: ", msg)

            self.popup_widget.geometry('+%d+%d' % (0, 0))

            self.popup_widget.attributes('-topmost', True)
            self.popup_widget.overrideredirect(True)

            label = Label(self.popup_widget, text=str("\n"+msg))
            label.pack(fill='x')

            self.popup_widget.update()
            self.popup_widget.deiconify()

            self.popup_widget.after(self.alive_time, lambda: self.popup_widget.withdraw())
            self.popup_widget.after(self.alive_time, lambda: label.destroy())
            
            self.since_last_popup = time.now()

            print("--Displayed--")


class SettingsMenu(OtherFrame):
    '''
    SettingsMenu
    ~~~~~~~~~~

    Gui frame for selecting settings.
    '''
    TITLE = "Settings"
    def __init__(self):
        super(SettingsMenu, self).__init__(SettingsMenu.TITLE)
