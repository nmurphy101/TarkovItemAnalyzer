#!/usr/bin/env python3

'''
    Tarkov Item Price Analyzer
    ~~~~~~~~~~

    Grabbing the item name from Tarkov and displaying price information
    with an overlay on the go.

    :copyright: (c) 2021 by Nicholas Murphy.
    :license: GPLv2, see LICENSE for more details.
'''


import os
import threading
import logging
import sys
import time
import string
import struct
import re
import requests
import pytesseract
import cv2
import tempfile
import urllib
import numpy as np
import queue as q
import keyboard
from multiprocessing import Pool, cpu_count, Queue, Process, Manager, Lock
from ctypes import windll, Structure, c_long, byref
from PIL import ImageGrab, Image, ImageFilter, ImageEnhance
from tkinter import messagebox, Toplevel, Label, Tk, Button, Text, INSERT, Frame
from bs4 import BeautifulSoup
from scipy import misc, cluster
# pylint: disable=no-name-in-module, method-hidden
from win32gui import GetWindowText, GetForegroundWindow
# pylint: enable=no-name-in-module
pytesseract.pytesseract.tesseract_cmd = r"D:\Program Files\Tesseract-OCR\tesseract.exe"


class ProcessManager(threading.Thread):
    '''
    ProcessManager
    ~~~~~~~~~~

    Manages the workers and adds events to the queue for the workers to consume.
    Listens for keyboard events and screenshots to find item names.
    Communicates with the GUI via a queue.
    Recieves instructions from the GUI via a different queue.
    '''
    def __init__(self, gui_queue, command_queue):
        super(ProcessManager, self).__init__()
        self.daemon = True
        self.setDaemon(True)
        self.need_quit = False
        # Setup the queues for the workers
        self.process_queue = Queue()
        self.command_queue = command_queue
        self.gui_queue = gui_queue
        self.position_list = []
        self.num_workers = 3
        self.position_record = []
        self.lock = Lock()
        self.img = None
        self.listen = True
        self.listen_lock = False

    def run(self):
        # Make the workers and start them up
        for _ in range(self.num_workers):
            Worker(self.process_queue, self.lock).start()

        # Take the screenshot for the item name (in inventory/stash)
        # The imageGrab needs to happen here or sooner else it won't happen quick enough
        while True:
            self.img = ImageGrab.grab()
            if not self.listen:
                break
            keyboard.on_press_key(key="f", callback=self.on_release)
            time.sleep(.1)
            self.listen_lock = False

        # # Listener Loop
        # with pkeyboard.Listener(on_press=lambda var:self.on_press(var)) as listener:
        #     listener.join()

    def Close(self):
        print("\nStopping")
        # Sentinel objects to allow clean shutdown: 1 per worker.
        for _ in range(self.num_workers):
            self.process_queue.put(None)
        self.listen = False
        threading.Thread.join(self, 3)

    def on_test(self):
        pass

    def on_press(self, e):
        keyboard.on_release_key(key="f", callback=self.on_release)

    def on_release(self, e):
        if self.listen_lock == False:
            self.listen_lock = True
            print("Got Listen Lock / released f")
            # Check if tarkov is the focused window before doing anything else
            active_process = GetWindowText(GetForegroundWindow())
            if active_process != "" and active_process == "EscapeFromTarkov":
                # Get the mouse position
                pos = queryMouse_position()

                # Generate a unique uuid for this instance
                # id = uuid.uuid4()

                # Figure out what this instance window popup should be located
                display_info_init = {
                    "x": 0,
                    "y": 0,
                    "w": 210, # width for the Tk root
                    "h": 120, # height for the Tk root
                    # "id": id,
                }

                # Add this next instance to the process pool and run it with a pool worker
                self.process_queue.put(MessageFunc(self.img, pos, display_info_init, self.gui_queue))

            else:
                logging.warning("target process is not active")
        else:
            pass


class Worker(Process):
    '''
    Worker
    ~~~~~~~~~~

    Does stuff it's told to do in the queue.
    '''
    def __init__(self, queue, lock):
        super(Worker, self).__init__()
        self.queue = queue
        self.lock = lock

    def run(self):
        # Worker Loop
        for process in iter(self.queue.get, None):
            process.run(self.lock)


class MessageFunc():
    '''
    MessageFunc
    ~~~~~~~~~~

    Gets a tarkov item name when a loose item in a match is picked up or when
    the item name box popup appears when mouse hovering the item in inventory/stash,
    and popups the item's market price and item quest information if it exists.
    '''
    def __init__(self, img, mouse_pos, display_info_init, gui_queue):
        self.need_quit = False
        self.img = img
        self.mouse_pos = mouse_pos
        self.display_info_init = display_info_init
        self.gui_queue = gui_queue
        self.debug_mode = 1

    def mse(self, imageA, imageB):
        '''
        The 'Mean Squared Error' between the two images is the
        sum of the squared difference between the two images;
        NOTE: the two images must have the same dimension
        '''
        err = np.sum((imageA.astype("float") - imageB.astype("float")) ** 2)
        err /= float(imageA.shape[0] * imageA.shape[1])

        # return the MSE, the lower the error, the more "similar"
        # the two images are
        return err

    def popup_error(self, lock, err_msg):
        # Make the popup string message
        popupStr = (f"{err_msg}")

        # Get the multiprocess lock and update the gui window
        lock.acquire()
        self.gui_queue.put([popupStr, self.display_info_init])
        # app.pop_always_on_top(popupStr, display_info)
        lock.release()

    def run(self, lock):
        while not self.need_quit:
            # Enhance the image
            # enhancer = ImageEnhance.Sharpness(img)
            # img = enhancer.enhance(.75)

            # Temp files for the images to be worked with
            temp_name0 = "temp_" + next(tempfile._get_candidate_names())+".png"
            temp_name1 = "temp_" + next(tempfile._get_candidate_names())+".png"
            temp_name2 = "temp_" + next(tempfile._get_candidate_names())+".png"

            # Determine if in inventory/stash or game(picking up loose item)
            # Get the "eyewear" inventory text  in the inventory screen as a determinate
            # search_area0 = (35, 15, 195, 55)
            # search_area0 = (617, 375, 711, 395)
            search_area0 = (598, 421, 692, 441)
            check_img = self.img.crop(search_area0)
            check_img.save(temp_name0, dpi=(5000, 5000))
            # Read in the images to compair
            check_img = cv2.imread(temp_name0)
            try:
                os.remove(temp_name0)
            except Exception as e:
                pass
            compare_img = cv2.imread("compare_img.png")

            if self.debug_mode >= 2:
                print("Showing eyewear inventory text expected image")
                cv2.imshow("image", compare_img)
                cv2.waitKey(0)
                print("Showing eyewear inventory text captured image")
                cv2.imshow("image", check_img)
                cv2.waitKey(0)

            # Select to check for the item name
            diff_num = self.mse(check_img, compare_img)
            inventory = None
            if self.debug_mode >= 1:
                print("Diff: ", diff_num)
            if diff_num < 2000:
                if self.debug_mode:
                    print("inventory")
                # Search areas for the inventory/stash item
                search_area1 = (self.mouse_pos["x"]-16, self.mouse_pos["y"]-42, self.mouse_pos["x"]+420, self.mouse_pos["y"]-10)
                search_area2 = (self.mouse_pos["x"]-400, self.mouse_pos["y"]-65, self.mouse_pos["x"]+420, self.mouse_pos["y"]-10)
                inventory = True
            else:
                if self.debug_mode >= 1:
                    print("Loose")
                width, height = self.img.size
                # Search areas for loose items in a match
                search_area1 = ((width/2)-39, (height/2)+42, (width/2)+40, (height/2)+57)
                search_area2 = ((width/2)-32, (height/2)+42, (width/2)+32, (height/2)+57)
                inventory = False

            # Save the cropped screen image
            self.img.crop(search_area1).save(temp_name1, dpi=(500, 500))
            # Save the cropped screen image
            self.img.crop(search_area2).save(temp_name2, dpi=(500, 500))

            page = None
            mainTryAttempt = 1
            mainTryLimit = 2
            found = False
            try:
                while not found:
                    if self.debug_mode >= 1:
                        print("Found?? ", found, mainTryAttempt, ">", mainTryLimit)

                    if mainTryAttempt > mainTryLimit:
                        self.need_quit = True
                        break

                    # Run tesseract on the image
                    if mainTryAttempt == 1:
                        image1 = cv2.imread(temp_name1)
                        image2 = cv2.imread(temp_name2)
                        try:
                            os.remove(temp_name1)
                        except Exception as exception:
                            pass
                        try:
                            os.remove(temp_name2)
                        except Exception as exception:
                            pass
                        image = cv2.resize(image1, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

                    if mainTryAttempt == 2:
                        image = cv2.resize(image2, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

                    if inventory:
                        print("In inventory contour corrector")
                        gray = cv2.cvtColor(image ,cv2.COLOR_BGR2GRAY)
                        edged = cv2.Canny(image, 10, 250)

                        if self.debug_mode >= 2:
                            cv2.imshow("gray", gray)
                            cv2.imshow("edged", edged)
                            cv2.waitKey(0)

                        (cnts, _) = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                        idx = 0
                        imagesList = []
                        areaList = []
                        i = 0
                        for c in cnts:
                            ## For testing draw the contours
                            peri = cv2.arcLength(c, True)
                            approx = cv2.approxPolyDP(c, 0.03 * peri, True)
                            cv2.drawContours(image, [approx], -1, (0, 255, 0), 2)

                            # Crop the image to the contour
                            x, y, w, h = cv2.boundingRect(c)
                            # if w>130 and h<175 and h>95:
                            if w > 66 and w < 1212 and h > 66 and h < 168:
                                idx += 1
                                new_img = image[y+13:y+h-11,x+11:x+w-11]
                                imagesList.append(new_img)
                                height, width, z = np.array(new_img).shape
                                area = height * width
                                areaList.append(area)
                                if self.debug_mode >= 3:
                                    cv2.imshow("slice_img"+str(i), new_img)
                                i += 1

                        if self.debug_mode >= 2:
                            print("Contours? ", len(areaList) == 0)
                            cv2.imshow("image", image)
                            cv2.waitKey(0)

                        # Check that it's a good image grab that has contour areas
                        if len(areaList) == 0:
                            if self.debug_mode >= 1:
                                print("No captures found")
                                print(" -  - " * 8)
                            mainTryAttempt = mainTryAttempt + 1
                            self.popup_error(lock, "Error, please try again")
                            self.need_quit = True
                            break

                        # inbuilt function to find the position of second maximum sized cropped image
                        secondMaxPos = areaList.index(secondMax(areaList))
                        # inbuilt function to find the position of maximum
                        maxPos = areaList.index(max(areaList))
                        # Get the chosen image
                        final_img = imagesList[maxPos]
                        image = final_img

                    else:
                        print("In raid")

                    if self.debug_mode >= 2:
                            cv2.imshow("final_image", image)
                            cv2.waitKey(0)

                    # THRESH_TRUNC works for the container items
                    retval, threshold = cv2.threshold(image, 80, 255, cv2.THRESH_BINARY_INV)

                    if self.debug_mode >= 3:
                        img = Image.fromarray(threshold, "RGB")
                        img.show()
                        cv2.waitKey(0)  

                    # Run the parser
                    # text = pytesseract.image_to_string(threshold, lang="eng", config="--PSM 7 --oem 0")
                    text = pytesseract.image_to_string(threshold, lang="eng", config="--psm 6")

                    # Display for testing
                    if self.debug_mode >= 1:
                        print("{{{ ", text, "}}}")

                    # Check that words were discovered
                    lineList = text.strip().split("\n")

                    if self.debug_mode >= 1:
                        print(lineList, lineList[len(lineList)-1])

                    wordlist = str.split(text.strip())
                    if len(wordlist) == 0:
                        if self.debug_mode >= 1:
                            print("Unexpected error:", "No Words Found")
                        mainTryAttempt = mainTryAttempt + 1
                        self.popup_error(lock, "Error, please try again")
                        self.need_quit = True
                        break

                    elif len(wordlist) == 1:
                        if len(wordlist[0]) <= 2:
                            if self.debug_mode >= 1:
                                print("Unexpected error:", "No Words Found")
                            mainTryAttempt = mainTryAttempt + 1
                            self.popup_error(lock, "Error, please try again")
                            self.need_quit = True
                            break

                        if wordlist[0] == "Body":
                            if self.debug_mode >= 1:
                                print("inspected a body")
                            self.popup_error(lock, "Error, please try again")
                            self.need_quit = True
                            break

                    if self.debug_mode >= 1:
                        print("WORDS 1: ", wordlist)

                    newWordList = []
                    for word in wordlist:
                        if word == ".":
                            if self.debug_mode >= 1:
                                print("'"+word+"'", "removed via 0")
                                
                        elif len(word) == 1:
                            if self.debug_mode >= 1:
                                print("'"+word+"'", "removed via 3")

                        elif not re.match(r"^[-\(\)/.,\"\'a-zA-Z0-9_]*$", word):
                            if (
                                not re.match(r"^[-\(\)/.,\"\'a-zA-Z0-9_]*$", word.strip("[-'’”\"`.@_!#$%^&*<>?/\}{~:]"))
                                and not re.match(r"[A-Za-z0-9]+(-|—|’|”)[A-Za-z0-9]+", word.strip("[-'’”\".`@_!#$%^&*<>?/\}{~:]"))
                            ):
                                if self.debug_mode >= 1:
                                    print("'"+word+"'", "removed via 1")

                            else:
                                if self.debug_mode >= 1:
                                    print("'"+word.strip("[-'”\".`@_!#$%^&*<>?/\}{~:]")+"'", "kept")
                                newWordList.append(word.strip("[-'”\".`@_!#$%^&*<>?/\}{~:]"))

                        elif re.match(r'^[_\W]+$', word):
                            if self.debug_mode >= 1:
                                print("'"+word+"'", "removed via 2")

                        else:
                            if self.debug_mode >= 1:
                                print("'"+word+"'", "kept")
                            newWordList.append(word)
                    
                    if self.debug_mode >= 1:
                        print("WORDS2: ", newWordList)

                    if len(newWordList) == 0:
                        if self.debug_mode >= 1:
                            print("Unexpected error:", "Couldn't get words to search")
                        mainTryAttempt = mainTryAttempt + 1
                        self.popup_error(lock, "Error, please try again")
                        self.need_quit = True
                        break

                    corrected_text = " ".join(newWordList)

                    # Display for testing
                    if self.debug_mode >= 1:
                        print(corrected_text)

                    # Get the true item name by double checking it with the gamepedia page  (this doesn't line up anymore, cuz tarkov market urls are the bane of my existance)
                    rep = {" ": "+", "$": "", "/": "_", r"[\/\\\n|_]*": "_", "muzzle": "muzzlebrake", "brake": "", "7.6239": "7.62x39",
                        "5.5645": "5.56x45", "MPS": "MP5", "MP3": "MP5", "Flash hider": "Flashhider", "]": ")", "[": "(", "sung": "sunglasses",
                        "X/L":"X_L", "Tactlcal": "Tactical", "AK-103-762x39": "", "l-f": "l_f",  "away": "", "MK2": "Mk.2", '"Klassika"': "Klassika",
                        "^['^a-zA-Z_]*$": "%E2%80%98", "RUG": "RDG", "AT-2": "AI-2", "®": "", "§": "5", "__": "_", "___": "", "xX": "X", "SORND": "50RND",
                        "Bastion dust cover for AK": "Bastion_dust_cover_for_%D0%B0%D0%BA", "PDC dust cover for AK-74": "PDC_dust_cover_for_%D0%B0%D0%BA-74",
                        "XLORUNO-VM": "KORUND-VM", "SURVIZ": "SURV12", "TOR": "Vector 9x19", "SPLIN": "SPLINT", "DSCRX": "D3CRX", "SSO": "SSD",
                        "((": "(", "))": ")"}
                    rep = dict((re.escape(k), v) for k, v in rep.items())
                    pattern = re.compile("|".join(rep.keys()))
                    search_text = pattern.sub(lambda m: rep[re.escape(m.group(0))], corrected_text).replace("__", "_").lstrip("()").strip("_-.,")
                    corrected_text = get_full_item_name(search_text, "wiki")
                    true_name = corrected_text
                    
                    if self.debug_mode >= 1:
                        print(search_text, " to correct ", corrected_text)

                    if corrected_text == None:
                        if self.debug_mode >= 1:
                            print("Unexpected error:", "Couldn't convert short to full")
                        mainTryAttempt = mainTryAttempt + 1
                        self.popup_error(lock, "Error, please try again")
                        self.need_quit = True
                        break

                    # corrected_text = get_full_item_name(corrected_text, "market")

                    # Regex replacement for building the item name for the URL
                    rep = {" ": "_", "(alu)": ""} # define desired replacements here

                    # use these lines to do the replacement
                    rep = dict((re.escape(k), v) for k, v in rep.items())
                    pattern = re.compile("|".join(rep.keys()))
                    corrected_text = pattern.sub(lambda m: rep[re.escape(m.group(0))], corrected_text).replace("__", "_").lstrip("()").strip("_-.,").replace("/", "_").replace("_Version", "")

                    # Display for testing
                    if self.debug_mode >= 1:
                        print(corrected_text)

                    # Further clean up to get rid of rogue "_i" or "i_" that made it past the filters
                    # if corrected_text.endswith("_i"):
                    #     corrected_text = corrected_text[:-2]
                    # if corrected_text.startswith("_i"):
                    #     corrected_text = corrected_text[:2]

                    if self.debug_mode >= 1:
                        print("-----TEST-----", corrected_text)

                    # scrape google for the tarkov-market.com/item/Item_name_here url
                    URL = get_item_url(corrected_text, "market")
                    if not "https://tarkov-market.com/item/" in URL:
                        self.popup_error(lock, "Error, please try again")
                        self.need_quit = True
                        break

                    tryCounter = 1
                    tryLimit = 4
                    page = None
                    page2 = None
                    while tryCounter <= tryLimit:
                        try:
                            if self.debug_mode >= 1:
                                print("Try: ", tryCounter, " ", URL)
                            page = requests.get(URL)

                            if page.status_code != 200:
                                raise Exception("Error Code: ", page.status_code)

                            else:
                                break

                        except:
                            if tryCounter == 1:
                                URL = URL_org

                            elif tryCounter == 2:
                                URL = "https://tarkov-market.com/item/"+corrected_text.lower().capitalize()

                            elif tryCounter == 3:
                                words_list = corrected_text.lower().split("_")
                                corrected_text = f"{words_list[0].capitalize()}_{'_'.join(map(str.upper, words_list[1:]))}"
                                URL = "https://tarkov-market.com/item/"+corrected_text

                            tryCounter = tryCounter + 1
                            self.popup_error(lock, "Error, please try again")
                            self.need_quit = True
                            break

                    if tryCounter > tryLimit:
                        if self.debug_mode >= 1:
                            print("Unexpected error:", "No Page Found")

                        mainTryAttempt = mainTryAttempt + 1
                        self.popup_error(lock, "Error, please try again")
                        self.need_quit = True
                        break

                    if page is None or page.status_code != 200:
                        if self.debug_mode >= 1:
                            print("Unable to find tarkov-market page")
                            print("="*80)

                        self.popup_error(lock, "Error, please try again")
                        self.need_quit = True
                        break

                    # Scrape the gamepedia item webpage for more details
                    try:
                        URL2 = "https://escapefromtarkov.gamepedia.com/"+true_name
                        page2 = requests.get(URL2)

                        if page2.status_code != 200:
                            raise Exception("Error Code: ", page2.status_code)

                        else:
                            print("Request Gamepedia 200")

                    except Exception as e:
                        if self.debug_mode >= 1:
                            print("Unexpected error:", "No Page Found for Gamepedia")

                    if page2 is None or page2.status_code != 200:
                        if self.debug_mode >= 1:
                            print("Unable to find gamepedia page")
                            print("="*80)

                        self.popup_error(lock, "Error, please try again")
                        self.need_quit = True
                        break

                    # Break the loop as we've found the item information
                    if self.debug_mode >= 1:
                        print("Found! Breaking")

                    found = True

                if page is None or page.status_code != 200:
                    mainTryAttempt = mainTryAttempt + 1
                    self.popup_error(lock, "Error, please try again")
                    continue
                
                if self.debug_mode >= 1:
                    print(page, page.status_code, mainTryAttempt)
                    print("Getting Item Information...")

                # Parse scraped tarkov-market page
                tm_soup = BeautifulSoup(page.content, "html.parser")
                # Parse scraped gamepedia page
                gp_soup = BeautifulSoup(page2.content, "html.parser")

                # Get all the price values and quest information
                # print("Full html: ", tm_soup)
                itemLastLowSoldPrice = tm_soup.findAll("div", {"class": "big bold alt"})[0].get_text()
                try:
                    item24hrAvgPrice = tm_soup.findAll("span", {"class": "bold alt"})[0].get_text()

                except IndexError:
                    item24hrAvgPrice = "NA"

                try:
                    traderName = tm_soup.findAll("div", {"class": "bold plus"})[6].parent.findAll("div", text=re.compile("[a-zA-Z]"))[1].get_text()
                    itemTraderPrice = tm_soup.findAll("div", {"class": "bold plus"})[6].parent.findAll("span", text=re.compile("[0-9]"))[0].get_text()
                
                except IndexError:
                    try:
                        traderName = tm_soup.findAll("div", {"class": "bold plus"})[5].parent.findAll("div", text=re.compile("[a-zA-Z]"))[1].get_text()
                        itemTraderPrice = tm_soup.findAll("div", {"class": "bold plus"})[5].parent.findAll("span", text=re.compile("[0-9]"))[0].get_text()
                    
                    except IndexError:
                        traderName = tm_soup.findAll("div", {"class": "bold plus"})[2].parent.findAll("div", text=re.compile("[a-zA-Z]"))[1].get_text()
                        itemTraderPrice = tm_soup.findAll("div", {"class": "bold plus"})[2].parent.findAll("span", text=re.compile("[0-9]"))[0].get_text()

                questsListText = []
                quests = ""
                questchecker = gp_soup.findAll("span", {"id": "Quests"})
                if len(questchecker) == 1:
                    lists = gp_soup.find("div", {"class": "mw-parser-output"}).findAll("ul")
                    for child in lists:
                        if child.find("font", {"color": "red"}):
                            for item in child.findChildren():
                                if item.getText()[0].isdigit():
                                    questsListText.append(item.getText().strip())

                    quests = "\n".join(questsListText)

                else:
                    quests = "Not Quest Item"

                if self.debug_mode >= 1:
                    print("PARSED INFO: ", itemLastLowSoldPrice, item24hrAvgPrice, traderName, itemTraderPrice, "\n", quests)
                    # Print to seperate diferent runs
                    print("="*80)

                # Popup display information/position dictionary
                display_info = {
                    "itemName": true_name,
                    "itemLastLowSoldPrice": itemLastLowSoldPrice,
                    "item24hrAvgPrice": item24hrAvgPrice,
                    "traderName": traderName,
                    "itemTraderPrice": itemTraderPrice,
                    "quests": quests,
                    }
                display_info.update(self.display_info_init)

                # Make the popup string message
                popupStr = ("{}\n\nLast lowest price: {}\n           24hr Avg: {}\n {}: {}\n\n{}".format(
                    display_info["itemName"], display_info["itemLastLowSoldPrice"],
                    display_info["item24hrAvgPrice"], display_info["traderName"].strip(),
                    display_info["itemTraderPrice"].strip(), display_info["quests"]
                ))

                # Get the multiprocess lock and update the gui window
                lock.acquire()
                self.gui_queue.put([popupStr, display_info])
                # app.pop_always_on_top(popupStr, display_info)
                lock.release()

                # Stop the runloop for this process
                self.need_quit = True

            except Exception as error:
                if self.debug_mode >= 1:
                    print("An Unknown Error Occured: ", error)

                self.popup_error(lock, "Error, please try again")


class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]


def get_full_item_name(search_text: str, site: str):
    if search_text == "":
        return None
    # Make a gamepedia search on the shorthand name
    try:
        if site == "market":
            search_url = f'https://www.google.com/search?&q=tarkov+market+{urllib.parse.quote_plus(search_text)}'
        else:
            search_url = f'https://www.google.com/search?&q=tarkov+wiki+{urllib.parse.quote_plus(search_text)}'
        page = requests.get(search_url)
        if page.status_code != 200:
            raise Exception("Error Code: ", page.status_code)
        else:
            print("Search Good")
    except Exception as exception:
        print("Unexpected error:", f"Couldn't get fullname from {site} search: ", exception)

    # Parse scraped gamepedia search and make search on the found item page
    soup = BeautifulSoup(page.content, 'html.parser')
    print(search_url)
    h3_list = soup.select('h3')
    print(h3_list)
    if len(h3_list) != 0:
        h3_text = h3_list[0].get_text().split(" - ")[0]
        print(h3_text)
        return remove_prefix(h3_text, "https://escapefromtarkov.gamepedia.com/")
    else:
        return None

def get_item_url(search_text: str, site: str):
    # Make a gamepedia search on the shorthand name
    try:
        if site == "market":
            search_url = "https://www.google.com/search?&q=tarkov+market+"+urllib.parse.quote_plus(search_text)
        elif site == "wiki":
            search_url = "https://www.google.com/search?&q=tarkov+wiki+"+urllib.parse.quote_plus(search_text)
        page = requests.get(search_url)
        if page.status_code != 200:
            raise Exception("Error Code: ", page.status_code)
        else:
            print("Search Good")
    except Exception as exception:
        print("Unexpected error:", f"Couldn't get fullname from {site} search: ", exception)

    # Parse scraped gamepedia search and make search on the found item page
    soup = BeautifulSoup(page.content, 'html.parser')
    print(type(soup))
    print(search_url)
    search_results = soup.findAll("div", {"class": "egMi0 kCrYT"})[0]
    print("THE SEARCH DIV", len(search_results), search_results)
    a_list = search_results.findAll("a", href=True)
    print(a_list)
    if len(a_list) != 0:
        a_text = a_list[0]["href"]
        if site in a_text:
            print(a_text)
            return f"https://google.com{a_text}"
        else:
            a_text = a_list[2]["href"]
            print(a_text)
            return f"https://google.com{a_text}"
    else:
        return None

def queryMouse_position():
    pt = POINT()
    windll.user32.GetCursorPos(byref(pt))
    return {"x": pt.x, "y": pt.y}


def remove_prefix(text, prefix):
    return text[text.startswith(prefix) and len(prefix):]


def secondMax(list1):
    if len(list1) <= 1:
        return list1[0]
    mx = max(list1[0], list1[1])
    secondmax = min(list1[0], list1[1])
    n = len(list1)
    for i in range(2, n):
        if list1[i] > mx:
            secondmax = mx
            mx = list1[i]
        elif list1[i] > secondmax and \
            mx != list1[i]:
            secondmax = list1[i]
    return secondmax
