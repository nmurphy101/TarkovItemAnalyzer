# Tarkov_Item_Analyzer
Tarkov Item Analyzer (TIA) allows you to know the price, and other informatino, of items you pick up on-the-fly!


# Build to Executible
auto-py-to-exe

pyinstaller --noconfirm --onefile --windowed --clean --add-data "C:/program_projects/Tarkov_Item_Analyzer/pkg;pkg/" --add-data "C:/program_projects/Tarkov_Item_Analyzer/tessdata;tessdata/" --add-data "C:/program_projects/Tarkov_Item_Analyzer/compare_img.png;." --add-data "C:/program_projects/Tarkov_Item_Analyzer/LICENSE;." --hidden-import "pynput" --exclude-module "pytest" --hidden-import "time" --hidden-import "sys" --hidden-import "re" --hidden-import "resource" --hidden-import "termios" --hidden-import "pyimod03_importers" --hidden-import "multiprocessing.Manager" --hidden-import "multiprocessing.Lock" --hidden-import "multiprocessing.Process" --hidden-import "multiprocessing.Queue" --hidden-import "multiprocessing.cpu_count" --hidden-import "multiprocessing.Pool" --hidden-import "tornado" --hidden-import "itertools" --paths "C:\Windows\System32\downlevel" --hidden-import "pynput._util" --hidden-import "pynput.keyboard"  "C:/program_projects/Tarkov_Item_Analyzer/main.py"