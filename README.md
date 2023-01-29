# Tarkov_Item_Analyzer
Tarkov Item Analyzer (TIA) allows you to know the price, and other informatino, of items you pick up on-the-fly!

# How to run

Follow the install_instructions.txt

Else if a full release exists (and it isn't broken like the first one is):
Use either the single exe file or the ziped directory or run the "python main.py" command directly
Using admin privileges start the single exe file or the exe file within the unzipped directory.
in 2-6sec the gui will open
press the "start" button while tarkov has already started to have the program watch tarkov
Start playing Tarkov as normal

# How to use

Make sure you're in borderless mode for tarkov, fullscreen will get you tabbed out by this app.

When in an inventory screen (Stash or match) hover your mouse over an item and wait for the black box with the item name to appear
Press "f" to get the item information (the result takes ~2-3sec to appear in upper right corner)
If nothing happens or an error message appears try again.
If it continues to fail let me know that item doesn't work and can't be found.

When picking up a loose item in a match with "f" (the default interact/pickup button keybinding)
it'll give you the item information (this takes 2-3sec)

The main app will also display a history of the most recent 5 items you've analyzed.

# Build to Executible
auto-py-to-exe

pyinstaller --noconfirm --onefile --windowed --clean --add-data "C:/DIR_LOCATION_HERE/Tarkov_Item_Analyzer/pkg;pkg/" --add-data "C:/DIR_LOCATION_HERE/Tarkov_Item_Analyzer/tessdata;tessdata/" --add-data "C:/DIR_LOCATION_HERE/Tarkov_Item_Analyzer/compare_img.png;." --add-data "C:/DIR_LOCATION_HERE/Tarkov_Item_Analyzer/LICENSE;." --hidden-import "pynput" --exclude-module "pytest" --hidden-import "time" --hidden-import "sys" --hidden-import "re" --hidden-import "resource" --hidden-import "termios" --hidden-import "pyimod03_importers" --hidden-import "multiprocessing.Manager" --hidden-import "multiprocessing.Lock" --hidden-import "multiprocessing.Process" --hidden-import "multiprocessing.Queue" --hidden-import "multiprocessing.cpu_count" --hidden-import "multiprocessing.Pool" --hidden-import "tornado" --hidden-import "itertools" --paths "C:\Windows\System32\downlevel" --hidden-import "pynput._util" --hidden-import "pynput.keyboard"  "C:/DIR_LOCATION_HERE/Tarkov_Item_Analyzer/main.py"



# Limitations
- Not all items will work as I haven't tested for every one of them.
- The "loose item" item information might be innacurate as tarkov uses shorthand names for loose items
  (ie pst gzh vs pst gzh for two different calibers), so use inventory screen to get more accurate information.
- In the current release there is a large-ish memory leak when you press the "stop" button then the "start" button. So just don't press "stop"
- In the current release there is a small memory leak when you press "f" checking items for information.
  - For both of these memory leaks I suggest closing the app and opening it again every so often to release the memory.
  - This is caused by the keylogger that watches for button presses (ie the "f" key, it's not necessarily the code here, perhaps the implementation)
- Some spaghetti code here, enjoy if you look through it. Might clean it up more later.
