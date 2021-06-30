# Tarkov_Item_Analyzer
Tarkov Item Analyzer (TIA) allows you to know the price, and other informatino, of items you pick up on-the-fly!

# How to run

Use either the single exe file or the ziped directory or run the "python main.py" command directly
Using admin privileges start the single exe file or the exe file within the unzipped directory.
in 2-6sec the gui will open
press the "start" button to have the program watch tarkov
Start playing Tarkov as normal

Note: Current release isn't updated, though current build is so just run the "python main.py" command directly instead.

# How to use

When in an inventory screen (Stash or match) hover your mouse over an item and wait for the black box with the item name to appear
Press "f" to get the item information (this takes 2-3sec)
If nothing happens try again or let me know that item doesn't work

When picking up a loose item in a match with "f"
it'll give you the item information (this takes 2-3sec)

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
