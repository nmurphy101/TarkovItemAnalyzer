#!/usr/bin/env python3

'''
    Tarkov Item Price Analyzer
    ~~~~~~~~~~

    Grabbing the item name from Tarkov and displaying price information
    with an overlay on the go.

    :copyright: (c) 2021 by Nicholas Murphy.
    :license: GPLv2, see LICENSE for more details.
'''

import atexit
import json
import os
import re
import tempfile
import threading
import time
from urllib.parse import urlencode, urlparse

import cv2
import keyboard
import numpy as np
import pytesseract
import requests
from bs4 import BeautifulSoup
from cv2.typing import MatLike
from ctypes import byref, c_long, Structure, windll
from multiprocessing import Lock, Process, Queue
from multiprocessing.synchronize import Lock as LockType
from PIL import Image, ImageGrab
from requests import HTTPError, RequestException, Response, Timeout
# pylint: disable=no-name-in-module, method-hidden
from win32gui import GetForegroundWindow, GetWindowText
# pylint: enable=no-name-in-module

from logger_config import logger


class ProcessManager(threading.Thread):
    '''
    ProcessManager
    ~~~~~~~~~~

    Manages the workers and adds events to the queue for the workers to consume.
    Listens for keyboard events and screenshots to find item names.
    Communicates with the GUI via a queue.
    Recieves instructions from the GUI via a different queue.
    '''
    def __init__(self, gui_queue: Queue, command_queue: Queue) -> None:
        super().__init__(name="ProcessManagerThread")
        self.daemon = True
        self.need_quit = False
        # Setup the queues for the workers
        self.process_queue = Queue()
        self.command_queue = command_queue
        self.gui_queue = gui_queue
        self.position_list = []
        self.num_workers = 3
        self.workers = []
        self.position_record = []
        self.lock = Lock()
        self.img = None
        self.listen = True
        self.listen_lock = False
        self.resumeEvent = threading.Event()
        # Define display information for the popup window
        self.display_info = {
            "x": 0,
            "y": 0,
            "w": 210,  # width for the Tk root
            "h": 120,  # height for the Tk root
        }

    def run(self) -> None:
        self.need_quit = False
        self.listen = True
        # Make the workers and start them up
        for idx in range(self.num_workers):
            worker = Worker(self.process_queue, self.lock, name=f"Worker-{idx}")
            self.workers.append(worker)
            worker.start()

        self.capture_screenshots()

    def capture_screenshots(self) -> None:
        try:
            with open("_internal/settings.json", "r") as settings_file:
                settings = json.load(settings_file)
                interact_key = settings.get("interact_key", "f")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load settings: {e}")
            interact_key = "f"

        keyboard.on_press_key(key=interact_key, callback=self.on_release)

        # Take the screenshot for the item name (in inventory/stash)
        while not self.need_quit:
            if not self.listen:
                self.resumeEvent.wait()
                self.listen = True

                keyboard.unhook_key(interact_key)
                try:
                    with open("_internal/settings.json", "r") as settings_file:
                        settings = json.load(settings_file)
                        interact_key = settings.get("interact_key", "f")
                    # Re-register the keyboard interact key
                    keyboard.on_press_key(key=interact_key, callback=self.on_release)

                except (FileNotFoundError, json.JSONDecodeError) as e:
                    logger.error(f"Failed to reload settings: {e}")
                    interact_key = "f"
                    keyboard.on_press_key(key=interact_key, callback=self.on_release)

                self.resumeEvent.clear()

            try:
                self.img = ImageGrab.grab()
                time.sleep(0.1)
                self.listen_lock = False
            except ImageGrab.ImageGrabError:
                logger.exception("Error capturing screenshot")
                self.need_quit = True
            except OSError:
                logger.exception("Error accessing screenshot")
                self.need_quit = True

    def quit(self) -> None:
        logger.info("Stopping")
        self.listen = False
        self.need_quit = True
        # Sentinel objects to allow clean shutdown: 1 per worker.
        for _ in range(self.num_workers):
            self.process_queue.put(None)

        # wait for the workers to finish
        for worker in self.workers:
            worker.join()

        # Stop the ProcessManager
        self.join()

    def on_release(self, _) -> None:
        if self.listen_lock or self.need_quit:
            return

        self.listen_lock = True
        logger.debug("Got Listen Lock / released f")

        # Check if Tarkov is the focused window before doing anything else
        active_window = GetWindowText(GetForegroundWindow())
        if active_window != "EscapeFromTarkov":
            logger.warning("Target process is not active")
            self.popup_error(self.lock, "Tarkov is not the active window")
            return

        # Get the mouse position
        mouse_position = queryMouse_position()

        # Define display information for the popup window
        display_info = {
            "x": 0,
            "y": 0,
            "w": 210,  # width for the Tk root
            "h": 120,  # height for the Tk root
        }

        # Add this instance to the process queue and run it with a pool worker
        self.process_queue.put(MessageFunc(self.img, mouse_position, display_info, self.gui_queue))

    def popup_error(self, lock: LockType, err_msg: str) -> None:
        # Make the popup string message
        popup_str = f"ERROR: {err_msg}"

        # Get the multiprocess lock and update the GUI window
        with lock:
            self.gui_queue.put([popup_str, self.display_info])


class Worker(Process):
    '''
    Worker
    ~~~~~~~~~~

    Does stuff it's told to do in the queue.
    '''
    def __init__(self, queue: Queue, lock: LockType, name: str = "WorkerProcess") -> None:
        super().__init__(name=name)
        self.daemon = True
        self.queue = queue
        self.lock = lock

    def run(self) -> None:
        # Worker Loop
        while True:
            process = self.queue.get()
            if process is None:
                break
            process.run(self.lock)


class MessageFunc():
    '''
    MessageFunc
    ~~~~~~~~~~

    Gets a tarkov item name when a loose item in a match is picked up or when
    the item name box popup appears when mouse hovering the item in inventory/stash,
    and popups the item's market price and item quest information if it exists.
    '''

    # Constants for UI coordinates
    INVENTORY_COORDS = {
        'eyewear_text': {
            'x1': 598,
            'y1': 421,
            'x2': 692,
            'y2': 441
        }
    }

    def __init__(self, img: Image, mouse_pos: dict, display_info_init: dict[str, int], gui_queue: Queue):
        self.need_quit = False
        self.img = img
        self.mouse_pos = mouse_pos
        self.display_info_init = display_info_init
        self.gui_queue = gui_queue
        # The debug mode determines what logs and images are shown when running
        logger_levels = {
            10: 3,  # DEBUG
            20: 1,  # INFO
            30: 2,  # WARNING
            40: 2,  # ERROR
            50: 2,  # CRITICAL
        }
        self.debug_mode = logger_levels[logger.level]

    def run(self, lock: LockType) -> None:
        while not self.need_quit:
            # Temp files for the images to be worked with
            temp_files = self.create_temp_files()

            # Determine if in inventory/stash or game(picking up loose item)
            # Get the "eyewear" inventory text  in the inventory screen as a determinate
            check_img = self.img.crop((
                self.INVENTORY_COORDS['eyewear_text']['x1'],
                self.INVENTORY_COORDS['eyewear_text']['y1'],
                self.INVENTORY_COORDS['eyewear_text']['x2'],
                self.INVENTORY_COORDS['eyewear_text']['y2'],
            ))
            check_img.save(temp_files[0], dpi=(5000, 5000))
            check_img = cv2.imread(temp_files[0])
            os.remove(temp_files[0])
            compare_img = cv2.imread("_internal/compare_img.png")

            if self.debug_mode >= 2:
                self.show_image(compare_img, "compare_img", "Showing eyewear inventory text expected image")
                self.show_image(check_img, "check_img", "Showing eyewear inventory text captured image")

            diff_num = self.mse(check_img, compare_img)
            is_inventory = self.determine_inventory(diff_num)

            search_areas = self.get_search_areas(is_inventory)
            # Save the cropped screen image
            self.img.crop(search_areas[0]).save(temp_files[1], dpi=(500, 500))
            # Save the cropped screen image
            self.img.crop(search_areas[1]).save(temp_files[2], dpi=(500, 500))

            page = None
            main_try_attempt = 1
            main_try_limit = 2
            found = False

            try:
                while not found:
                    if self.debug_mode >= 1:
                        logger.info(f"Found?? {found} {main_try_attempt} > {main_try_limit}")

                    if main_try_attempt > main_try_limit:
                        self.need_quit = True
                        break

                    # Run tesseract on the image
                    image = self.process_image(main_try_attempt, temp_files, is_inventory)

                    if image is None:
                        if self.debug_mode >= 1:
                            logger.info("No captures found")
                        self.popup_error(lock, "Error, please try again")
                        main_try_attempt = main_try_attempt + 1
                        self.need_quit = True
                        break

                    text, threshold = self.extract_text(image)

                    if self.debug_mode >= 3:
                        try:
                            img = Image.fromarray(threshold, "RGB")
                            img.show()
                            cv2.waitKey(0)
                        except (ValueError, OSError) as e:
                            logger.error(f"Error displaying threshold image: {e}")

                    elif self.debug_mode >= 1:
                        logger.debug(f"Extracted Text: {text}")

                    wordlist = self.clean_text(text)

                    if not self.validate_wordlist(wordlist):
                        main_try_attempt += 1
                        self.popup_error(lock, "Error, please try again")
                        self.need_quit = True
                        break

                    corrected_text = self.correct_text(wordlist)
                    true_name = self.get_full_item_name(corrected_text, "wiki")

                    if not true_name:
                        main_try_attempt += 1
                        self.popup_error(lock, "Error, please try again")
                        self.need_quit = True
                        break

                    if self.debug_mode >= 1:
                        logger.info(f"{corrected_text} to correct {true_name}")

                    URL = self.get_item_url(corrected_text, "market")
                    page, page2 = self.fetch_pages(URL, true_name, corrected_text)

                    if not page or not page2:
                        main_try_attempt += 1
                        self.popup_error(lock, "Error, please try again")
                        self.need_quit = True
                        break

                    if self.debug_mode >= 1:
                        logger.info("Getting Item Information...")

                    display_info = self.parse_pages(page, page2, true_name)

                    if self.debug_mode >= 1:
                        logger.info(f"PARSED INFO: {display_info["itemLastLowSoldPrice"]}, {display_info["item24hrAvgPrice"]}, {display_info["traderName"]}, {display_info["itemTraderPrice"]}, \n {display_info["quests"]}")

                    # Popup display information/position dictionary
                    display_info.update(self.display_info_init)
                    self.update_gui(lock, display_info)

                    found = True
                    if not found:
                        self.popup_error(lock, "Error, please try again")

                # Stop the runloop for this process
                self.need_quit = True

            except (requests.RequestException, ValueError) as error:
                if self.debug_mode >= 1:
                    logger.exception(f"Failed to process request: {error}")

                self.popup_error(lock, "Error, please try again")
                # Stop the runloop for this process
                self.need_quit = True

    def mse(self, imageA: np.ndarray, imageB: np.ndarray) -> float:
        '''
        The 'Mean Squared Error' between the two images is the
        sum of the squared difference between the two images;
        NOTE: the two images must have the same dimension
        '''
        if imageA.shape != imageB.shape:
            raise ValueError("Input images must have the same dimensions.")

        # Calculate the mean squared error using NumPy's built-in functions and
        # Return the MSE, the lower the error, the more "similar" the two images are.
        return np.mean((imageA.astype("float") - imageB.astype("float")) ** 2)

    def popup_error(self, lock: LockType, err_msg: str) -> None:
        # Make the popup string message
        popup_str = f"ERROR: {err_msg}"

        # Get the multiprocess lock and update the GUI window
        with lock:
            self.gui_queue.put([popup_str, self.display_info_init])

    def create_temp_files(self) -> tuple[str, ...]:
        """Create temporary files with proper cleanup."""
        temp_files = []
        for _ in range(3):
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".png",
                prefix="tia_",  # Add prefix for identification
                mode="w+b"
            ) as temp:
                temp_files.append(temp.name)

        # Register cleanup handler
        atexit.register(lambda: [os.unlink(f) for f in temp_files if os.path.exists(f)])
        return tuple(temp_files)

    def show_image(self, image: MatLike, title: str, message: str, use_waitkey: bool = True) -> None:
        logger.info(message)
        cv2.imshow(title, image)
        if use_waitkey:
            cv2.waitKey(0)

    def determine_inventory(self, diff_num: int) -> bool:
        if self.debug_mode >= 1:
            logger.debug(f"Diff: {diff_num}")
        if diff_num < 2000:
            if self.debug_mode:
                logger.info("Inventory screenshot")
            return True
        if self.debug_mode >= 1:
            logger.info("In raid screenshot")
        return False

    def get_search_areas(self, inventory: bool) -> tuple:
        if inventory:
            return (
                (self.mouse_pos["x"] - 16, self.mouse_pos["y"] - 42, self.mouse_pos["x"] + 420, self.mouse_pos["y"] - 10),
                (self.mouse_pos["x"] - 400, self.mouse_pos["y"] - 65, self.mouse_pos["x"] + 420, self.mouse_pos["y"] - 10),
            )

        width, height = self.img.size
        return (
            ((width / 2) - 39, (height / 2) + 42, (width / 2) + 40, (height / 2) + 57),
            ((width / 2) - 32, (height / 2) + 42, (width / 2) + 32, (height / 2) + 57),
        )

    def extract_text(self, image: MatLike) -> tuple[str, MatLike]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, threshold = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
        return pytesseract.image_to_string(threshold, lang="eng", config="--psm 6"), threshold

    def clean_text(self, text: str) -> list:
        wordlist = text.strip().split()

        if self.debug_mode >= 1:
            logger.info(f"{wordlist} {wordlist[len(wordlist)-1]}")

        new_wordlist = []
        for word in wordlist:
            if len(word) > 1 and re.match(r"^[-\(\)/.,\"\'a-zA-Z0-9_]*$", word):
                new_wordlist.append(word.strip(r"[-'”\".`@_!#$%^&*<>?/\}{~:]"))
        return new_wordlist

    def process_image(self, attempt: int, temp_files: tuple, is_inventory: bool) -> MatLike | None:
        if attempt == 1:
            image1 = cv2.imread(temp_files[1])
            image2 = cv2.imread(temp_files[2])
            os.remove(temp_files[1])
            os.remove(temp_files[2])
            image = cv2.resize(image1, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

        if attempt == 2:
            image = cv2.resize(image2, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

        if is_inventory:
            logger.debug("In inventory contour corrector")
            gray = cv2.cvtColor(image ,cv2.COLOR_BGR2GRAY)
            edged = cv2.Canny(image, 10, 250)

            if self.debug_mode >= 2:
                self.show_image(gray, "gray", "Showing gray image", False)
                self.show_image(edged, "edged", "Showing edged image")

            (cnts, _) = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            idx = 0
            imagesList = []
            areaList = []
            i = 0
            for c in cnts:
                ## For testing draw the contours
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(curve=c, epsilon=0.03 * peri, closed=True)
                cv2.drawContours(image, [approx], -1, (0, 255, 0), 2)

                # Crop the image to the contour
                x, y, w, h = cv2.boundingRect(c)
                # if w>130 and h<175 and h>95:
                if w > 66 and w < 1212 and h > 66 and h < 168:
                    idx += 1
                    new_img = image[y+13:y+h-11,x+11:x+w-11]
                    imagesList.append(new_img)
                    height, width, _ = np.array(new_img).shape
                    area = height * width
                    areaList.append(area)
                    if self.debug_mode >= 3:
                        self.show_image(new_img, f"slice_img{str(i)}", f"Showing slice image {str(i)}")
                    i += 1

            if self.debug_mode >= 2:
                self.show_image(image, "image", "Showing image with contours")
                logger.debug(f"Number of Contours: {len(areaList) == 0}")

            # Check that it's a good image grab that has contour areas
            if len(areaList) == 0:
                return None

            # Largest area that should contain the item name text
            maxPos = areaList.index(max(areaList))

            # Get the chosen image
            final_img = imagesList[maxPos]
            image = final_img

        else:
            logger.debug("In raid, no contour corrector")

        if self.debug_mode >= 2:
            self.show_image(image, "final_image", "Showing final image")

        return image

    def validate_wordlist(self, wordlist: list) -> bool:
        if len(wordlist) == 0 or (len(wordlist) == 1 and len(wordlist[0]) <= 2):
            return False
        return not wordlist[0] == "Body"

    def correct_text(self, wordlist: list) -> str:
        corrected_text = " ".join(wordlist)

        if self.debug_mode >= 1:
            logger.debug(corrected_text)

        rep = {
            " ": "+", "$": "", "/": "_", r"[\/\\\n|_]*": "_", "muzzle": "muzzlebrake", "brake": "", "7.6239": "7.62x39",
            "5.5645": "5.56x45", "MPS": "MP5", "MP3": "MP5", "Flash hider": "Flashhider", "]": ")", "[": "(", "sung": "sunglasses",
            "X/L": "X_L", "Tactlcal": "Tactical", "AK-103-762x39": "", "l-f": "l_f", "away": "", "MK2": "Mk.2", '"Klassika"': "Klassika",
            "^['^a-zA-Z_]*$": "%E2%80%98", "RUG": "RDG", "AT-2": "AI-2", "®": "", "§": "5", "__": "_", "___": "", "xX": "X", "SORND": "50RND",
            "Bastion dust cover for AK": "Bastion_dust_cover_for_%D0%B0%D0%BA", "PDC dust cover for AK-74": "PDC_dust_cover_for_%D0%B0%D0%BA-74",
            "XLORUNO-VM": "KORUND-VM", "SURVIZ": "SURV12", "TOR": "Vector 9x19", "SPLIN": "SPLINT", "DSCRX": "D3CRX", "SSO": "SSD",
            "((": "(", "))": ")",
            # Add additional replacements if necessary
        }
        rep = {re.escape(k): v for k, v in rep.items()}
        pattern = re.compile("|".join(rep.keys()))
        return pattern.sub(lambda m: rep[re.escape(m.group(0))], corrected_text).replace("__", "_").lstrip("()").strip("_-.,").replace("/", "_").replace("_Version", "")

    def construct_search_url(self, site: str, search_text: str) -> str:
        if not search_text:
            return None

        base_urls = {
            'market': 'https://www.google.com/search',
            'wiki': 'https://www.google.com/search'
        }

        if site not in base_urls:
            raise ValueError(f"Invalid site: {site}")

        params = {
            'q': f'tarkov {site} {search_text}',
        }

        return f"{base_urls[site]}?{urlencode(params)}"


    def get_full_item_name(self, search_text: str, site: str) -> str:
        if not search_text:
            return None

        try:
            if site not in ["market", "wiki"]:
                raise ValueError("Invalid site. Choose 'market' or 'wiki'.")

            search_url = self.construct_search_url(site, search_text)
            # Validate URL
            parsed = urlparse(search_url)
            if not all([parsed.scheme, parsed.netloc]):
                raise ValueError("Invalid URL constructed")

            page = requests.get(search_url, timeout=10)
            page.raise_for_status()  # Raises an HTTPError if the status is 4xx, 5xx

            soup = BeautifulSoup(page.content, 'html.parser')
            h3_list = soup.select('h3')

            if h3_list:
                h3_text = h3_list[0].get_text().split(" - ")[0]
                return remove_prefix(h3_text, "https://escapefromtarkov.gamepedia.com/")
            else:
                return None

        except (RequestException, HTTPError) as e:
            logger.exception("Failed to fetch search results: %s", str(e))
            return None
        except Timeout:
            logger.error("Request timed out")
            return None
        except ValueError as e:
            logger.error("Invalid URL or site: %s", str(e))
            return None


    def get_item_url(self, search_text: str, site: str) -> str:
        try:
            if site not in ["market", "wiki"]:
                raise ValueError("Invalid site. Choose 'market' or 'wiki'.")

            search_url = self.construct_search_url(site, search_text)
            page = requests.get(search_url, timeout=10)
            page.raise_for_status()  # Raises an HTTPError if the status is 4xx, 5xx

            soup = BeautifulSoup(page.content, 'html.parser')
            search_results = soup.find("div", {"class": "egMi0 kCrYT"})
            if not search_results:
                raise Exception("No search results found.")

            a_list = search_results.find_all("a", href=True)
            if not a_list:
                raise Exception("No links found in search results.")

            for a in a_list:
                if site in a["href"]:
                    return f"https://google.com{a['href']}"

            return f"https://google.com{a_list[0]['href']}" if a_list else None

        except Exception as e:
            logger.exception(f"Error: Couldn't get item url from {site} search: {e}")
            return None

    def fetch_pages(self, URL: str, true_name: str, corrected_text: str) -> tuple:
        tryCounter = 1
        tryLimit = 3
        page1 = None
        page2 = None
        while tryCounter <= tryLimit:
            try:
                if self.debug_mode >= 1:
                    logger.debug("Tarkov market request Try: ", tryCounter, " ", URL)

                page1 = requests.get(URL, timeout=10)

                if page1.status_code != 200:
                    raise Exception("Error Code: ", page1.status_code)

                else:
                    break

            except requests.RequestException as e:
                if tryCounter == 1:
                    URL = f"https://tarkov-market.com/item/{corrected_text}".lower().capitalize()

                elif tryCounter == 2:
                    words_list = corrected_text.lower().split("_")
                    corrected_text = f"{words_list[0].capitalize()}_{'_'.join(map(str.upper, words_list[1:]))}"
                    URL = f"https://tarkov-market.com/item/{corrected_text}"

                tryCounter = tryCounter + 1

        if tryCounter > tryLimit:
            if self.debug_mode >= 1:
                logger.warning("Try limit reached on tarkov-market page")
            return None, None

        if page1 is None or page1.status_code != 200:
            if self.debug_mode >= 1:
                logger.info("Unable to find tarkov-market page")
            return None, None

        # Scrape the gamepedia item webpage for more item details
        try:
            URL2 = f"https://escapefromtarkov.gamepedia.com/{true_name}"
            page2 = requests.get(URL2, timeout=10)

            if page2.status_code != 200:
                raise Exception("Error Code on gamepedia request: ", page2.status_code)

        except Exception as e:
            if self.debug_mode >= 1:
                logger.exception("Unexpected error: ", e, exc_info=True)

        if page2 is None or page2.status_code != 200:
            if self.debug_mode >= 1:
                logger.info("Unable to find gamepedia page")
            return None, None

        return page1, page2

    def parse_pages(self, page1: Response, page2: Response, true_name: str) -> dict:
        tm_soup = BeautifulSoup(page1.content, "html.parser")
        gp_soup = BeautifulSoup(page2.content, "html.parser")

        item_last_low_sold_price = tm_soup.findAll("div", {"class": "big bold alt"})[0].get_text()
        try:
            item_24hr_avg_price = tm_soup.findAll("span", {"class": "bold alt"})[0].get_text()
        except IndexError:
            item_24hr_avg_price = "NA"

        try:
            trader_name = tm_soup.findAll("div", {"class": "bold plus"})[6].parent.findAll("div", text=re.compile("[a-zA-Z]"))[1].get_text()
            item_trader_price = tm_soup.findAll("div", {"class": "bold plus"})[6].parent.findAll("span", text=re.compile("[0-9]"))[0].get_text()
        except IndexError:
            try:
                trader_name = tm_soup.findAll("div", {"class": "bold plus"})[5].parent.findAll("div", text=re.compile("[a-zA-Z]"))[1].get_text()
                item_trader_price = tm_soup.findAll("div", {"class": "bold plus"})[5].parent.findAll("span", text=re.compile("[0-9]"))[0].get_text()
            except IndexError:
                trader_name = tm_soup.findAll("div", {"class": "bold plus"})[2].parent.findAll("div", text=re.compile("[a-zA-Z]"))[1].get_text()
                item_trader_price = tm_soup.findAll("div", {"class": "bold plus"})[2].parent.findAll("span", text=re.compile("[0-9]"))[0].get_text()

        quests_list_text = []
        quests = ""
        questchecker = gp_soup.findAll("span", {"id": "Quests"})
        if len(questchecker) == 1:
            lists = gp_soup.find("div", {"class": "mw-parser-output"}).findAll("ul")
            for child in lists:
                if child.find("font", {"color": "red"}):
                    for item in child.findChildren():
                        if item.getText()[0].isdigit():
                            quests_list_text.append(item.getText().strip())
            quests = "\n".join(quests_list_text)
        else:
            quests = "Not Quest Item"

        return {
            "itemName": true_name,
            "itemLastLowSoldPrice": item_last_low_sold_price,
            "item24hrAvgPrice": item_24hr_avg_price,
            "traderName": trader_name,
            "itemTraderPrice": item_trader_price,
            "quests": quests,
        }

    def update_gui(self, lock: LockType, display_info: dict[str, str]) -> None:
        popup_str = ("{}\n\nLast lowest price: {}\n           24hr Avg: {}\n {}: {}\n\n{}".format(
            display_info["itemName"], display_info["itemLastLowSoldPrice"],
            display_info["item24hrAvgPrice"], display_info["traderName"].strip(),
            display_info["itemTraderPrice"].strip(), display_info["quests"]
        ))

        with lock:
            self.gui_queue.put([popup_str, display_info])


class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]


def queryMouse_position() -> dict:
    pt = POINT()
    windll.user32.GetCursorPos(byref(pt))
    return {"x": pt.x, "y": pt.y}


def remove_prefix(text: str, prefix: str) -> str:
    if text.startswith(prefix):
        return text[len(prefix):]
    return text
