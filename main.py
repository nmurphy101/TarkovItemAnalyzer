#!/usr/bin/env python3

"""
    Tarkov Item Price Analyzer - Main
    ~~~~~~~~~~

    Grabbing the item name from Tarkov and displaying price information
    with an overlay on the go.

    :copyright: (c) 2021 by Nicholas Murphy.
    :license: GPLv2, see LICENSE for more details.
"""


__author__ = "Nicholas Murphy"
__version__ = '0.1.0'

from tkinter import Tk
from multiprocessing import Manager
from multiprocessing import freeze_support
from pkg.gui import GUI

freeze_support()

def main():
    
        # Gui manager and command manager queues'
        manager = Manager()
        gui_queue = manager.Queue()
        manager2 = Manager()
        cmd_queue = manager2.Queue()

        # Start the root app
        root = Tk()
        root.update() # This is the workaround
        root.geometry("300x90")

        # Run the gui
        gui = GUI(root, gui_queue, cmd_queue, "Tarkov Item Analyzer")

        # End of the main app.
        root.mainloop()
        if gui.p_manager.is_alive():
            gui.p_manager.Close()
            gui.p_manager.join()
   

if __name__ == "__main__":
    main()