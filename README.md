# Status
[![CodeFactor](https://www.codefactor.io/repository/github/nmurphy101/tarkovitemanalyzer/badge)](https://www.codefactor.io/repository/github/nmurphy101/tarkovitemanalyzer) ![Release](https://github.com/nmurphy101/tarkovitemanalyzer/actions/workflows/build.yml/badge.svg?branch=main) ![Build](https://github.com/nmurphy101/tarkovitemanalyzer/actions/workflows/python-app.yml/badge.svg)

# Tarkov_Item_Analyzer
Tarkov Item Analyzer (TIA) allows you to know the price, and other information, of items you pick up on-the-fly!

# How to run

Follow the install_instructions.txt foor development

Else just use a current release:
install tesseract via one of the installers in the installers directory.
Run tarkov
Run the tarkov_item_analyzer.exe
With the app open press "stop" open the settings and set the path to tesseract.exe on your computer and press "save"
close the settings and press "start"
Start playing Tarkov as normal
press the "stop" button to stop the analyzer from watching for the "f" inspect button press

# How to use

Make sure you're in borderless mode for tarkov, fullscreen will get you tabbed out by this app.

When in an inventory screen (Stash or match) hover your mouse over an item and wait for the black box with the item name to appear
Press "f" to get the item information (the result takes ~2-3sec to appear in upper left corner)
If nothing happens or an error message appears try again.
If it continues to fail let me know that item doesn't work and can't be found.

When picking up a loose item in a match with "f" (the default interact/pickup button keybinding)
it'll give you the item information (this takes 2-3sec)

The main app will also display a history of the most recent 5 items you've analyzed.

# Limitations
- Not all items will work as I haven't tested for every one of them.
- The "loose item" item information might be innacurate as tarkov uses shorthand names for loose items
  (ie pst gzh vs pst gzh for two different calibers), so use inventory screen to get more accurate information.
