#!/usr/bin/env python3

"""
    Tarkov Item Price Analyzer
    ~~~~~~~~~~

    Grabbing the item name from Tarkov and displaying price information
    with an overlay on the go.

    :copyright: (c) 2021 by Nicholas Murphy.
    :license: GPLv2, see LICENSE for more details.
"""

import os
import threading
import logging
import sys
import time
import string
import binascii
import struct
import re
import requests
import pytesseract
import cv2
import tempfile
import uuid
import urllib
import numpy as np
import queue as q
import keyboard
import pynput.keyboard as pkeyboard
from multiprocessing import Pool, cpu_count, Queue, Process, Manager, Lock
from ctypes import windll, Structure, c_long, byref
from PIL import ImageGrab, Image, ImageFilter, ImageEnhance
from tkinter import messagebox, Toplevel, Label, Tk, Button, Text, INSERT, Frame
from bs4 import BeautifulSoup
from scipy import misc, cluster
# pylint: disable=no-name-in-module, method-hidden
from win32gui import GetWindowText, GetForegroundWindow
# pylint: enable=no-name-in-module

class ProcessManager(threading.Thread):
    """
    ProcessManager
    ~~~~~~~~~~

    Manages the workers and adds events to the queue for the workers to consume.
    Listens for keyboard events and screenshots to find item names.
    Communicates with the GUI via a queue.
    Recieves instructions from the GUI via a different queue.
    """
    def __init__(self, gui_queue, command_queue):
        super(ProcessManager, self).__init__()
        self.daemon = True
        self.need_quit = False
        # Setup the queues for the workers
        self.process_queue = Queue()
        self.command_queue = command_queue
        self.gui_queue = gui_queue
        self.position_list = []
        self.num_workers = 1
        self.position_record = []
        self.lock = Lock()
        self.img = None
        self.listen = True

    def run(self):
        # Make the workers and start them up
        for _ in range(self.num_workers):
            Worker(self.process_queue, self.lock).start()

        # Take the screenshot for the item name (in inventory/stash) 
        # This needs to happen here or sooner else it won't happen quick enough
        while True:
            if not self.listen:
                break
            if keyboard.on_release("f"):
                self.img = ImageGrab.grab()
                self.on_release()

        # Listener Loop
        # with pkeyboard.Listener(on_press=self.on_press) as listener:
        #     listener.join()

    def Close(self):
        # Sentinel objects to allow clean shutdown: 1 per worker.
        for _ in range(self.num_workers):
            self.process_queue.put(None)
        self.listen = False

    def on_release(self):
        # Check if tarkov is the focused window before doing anything else
        active_process = GetWindowText(GetForegroundWindow())
        if active_process != "" and active_process == "EscapeFromTarkov":
            # Get the mouse position
            pos = queryMousePosition()

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
            logging.warning('target process is not active')

class Worker(Process):
    """
    Worker
    ~~~~~~~~~~

    Does stuff it's told to do in the queue.
    """
    def __init__(self, queue, lock):
        super(Worker, self).__init__()
        self.queue = queue
        self.lock = lock

    def run(self):
        # Worker Loop
        for process in iter(self.queue.get, None):
            process.run(self.lock)

class MessageFunc():
    """
    MessageFunc
    ~~~~~~~~~~

    Gets a tarkov item name when a loose item in a match is picked up or when
    the item name box popup appears when mouse hovering the item in inventory/stash,
    and popups the item's market price and item quest information if it exists.
    """
    def __init__(self, img, mousePos, display_info_init, gui_queue):
        self.need_quit = False
        self.img = img
        self.mousePos = mousePos
        self.display_info_init = display_info_init
        self.gui_queue = gui_queue

    def mse(self, imageA, imageB):
        # the 'Mean Squared Error' between the two images is the
        # sum of the squared difference between the two images;
        # NOTE: the two images must have the same dimension
        err = np.sum((imageA.astype("float") - imageB.astype("float")) ** 2)
        err /= float(imageA.shape[0] * imageA.shape[1])

        # return the MSE, the lower the error, the more "similar"
        # the two images are
        return err

    def getFullItemName(self, search_text):
        #M Make a gamepedia search on the shorthand name
        try:
            search_url = "https://www.google.com/search?&q=site%3Aescapefromtarkov.gamepedia.com+"+urllib.parse.quote_plus(search_text)
            page = requests.get(search_url)
            if page.status_code != 200:
                raise Exception("Error Code: ", page.status_code)
            else:
                print("Search Good")
        except Exception as e:
            print("Unexpected error:", "Couldn't get fullname from gamepedia search")

        # Parse scraped gamepedia search and make search on the found item page
        soup = BeautifulSoup(page.content, 'html.parser')
        print(search_url)
        h3_list = soup.select('h3', {"class": "LC20lb DKV0Md"})
        print(h3_list)
        h3_text = h3_list[0].get_text().split(" - ")[0]
        print(h3_text)
        return remove_prefix(h3_text, "https://escapefromtarkov.gamepedia.com/")

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
            # Get the "overview" button in the inventory screen as a determinate
            search_area0 = (40, 12, 200, 50)
            check_img = self.img.crop(search_area0)
            check_img.save(temp_name0, dpi=(500, 500))
            # Read in the images to compair
            check_img = cv2.imread(temp_name0)
            try: 
                os.remove(temp_name0)
            except Exception as e:
                pass
            compare_img = cv2.imread("compare_img.png")

            # Select to check for the item name 
            diff_num = self.mse(check_img, compare_img)
            inventory = None
            print("Diff: ", diff_num)
            if diff_num < 370:
                print("inventory")
                # Search areas for the inventory/stash item
                search_area1 = (self.mousePos["x"]-16, self.mousePos["y"]-42, self.mousePos["x"]+420, self.mousePos["y"]-10)
                search_area2 = (self.mousePos["x"]-400, self.mousePos["y"]-65, self.mousePos["x"]+420, self.mousePos["y"]-10)
                inventory = True
            else:
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
            while not found:
                # print("Found?? ", found, mainTryAttempt, ">", mainTryLimit)
                if mainTryAttempt > mainTryLimit:
                    self.need_quit = True
                    break

                # Run tesseract on the image
                if mainTryAttempt == 1:
                    image1 = cv2.imread(temp_name1)
                    image2 = cv2.imread(temp_name2)
                    try: 
                        os.remove(temp_name1)
                    except Exception as e:
                         pass
                    try: 
                        os.remove(temp_name2)
                    except Exception as e:
                         pass
                    image = cv2.resize(image1, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
                if mainTryAttempt == 2:
                    image = cv2.resize(image2, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

                if inventory:
                    gray = cv2.cvtColor(image ,cv2.COLOR_BGR2GRAY)
                    # cv2.imshow("gray", gray)
                    edged = cv2.Canny(image, 10, 250)
                    # cv2.imshow("edged", edged)
                    # cv2.waitKey(0)
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
                        if w>66 and w<1212 and h>66 and h<168:
                            idx += 1 
                            new_img = image[y+13:y+h-11,x+11:x+w-11]
                            imagesList.append(new_img)
                            height, width, z = np.array(new_img).shape
                            area = height * width
                            areaList.append(area)
                            # cv2.imshow("slice_img"+str(i), new_img)
                            i += 1
                    # print("Contours? ", len(areaList) == 0)
                    # cv2.imshow("image", image)
                    # cv2.waitKey(0)

                    # Check that it's a good image grab that has contour areas
                    if len(areaList) == 0:
                        print("No captures found")
                        print(" -  - " * 8)
                        mainTryAttempt = mainTryAttempt + 1
                        continue

                    # inbuilt function to find the position of second maximum sized cropped image
                    secondMaxPos = areaList.index(secondMax(areaList))
                    # inbuilt function to find the position of maximum
                    maxPos = areaList.index(max(areaList)) 
                    # Get the chosen image
                    final_img = imagesList[maxPos]
                    image = final_img
                    # cv2.imshow("final_image", image) 
                    # cv2.waitKey(0)

                # THRESH_TRUNC works for the container items
                retval, threshold = cv2.threshold(image, 80, 255, cv2.THRESH_BINARY_INV)
                # img = Image.fromarray(threshold, 'RGB')
                # img.show()

                # Run the parser
                # text = pytesseract.image_to_string(threshold, lang='eng', config='--PSM 7 --OEM 0')
                text = pytesseract.image_to_string(threshold, lang='eng', config='--OEM 0')

                # Display for testing
                print("{{{ ", text, "}}}")
                
                # Check that words were discovered
                # lineList = text.strip().split("\n")
                # print(lineList, lineList[len(lineList)-1])
                wordlist = str.split(text.strip())
                if len(wordlist) == 0:
                    print("Unexpected error:", "No Words Found")
                    mainTryAttempt = mainTryAttempt + 1
                    continue
                elif len(wordlist) == 1:
                    if len(wordlist[0]) <= 2:
                        print("Unexpected error:", "No Words Found")
                        mainTryAttempt = mainTryAttempt + 1
                        continue

                print("WORDS1: ", wordlist)
                newWordList = []
                for word in wordlist:
                    if word == ".":
                        print("'"+word+"'", "removed")
                    elif not re.match(r"^[-\(\)/.,\"\'a-zA-Z0-9_]*$", word):
                        if not re.match(r"^[-\(\)/.,\"\'a-zA-Z0-9_]*$", word.strip("[@_!#$%^&*<>?/\}{~:]")):
                            print("'"+word+"'", "removed")
                        else:
                            print("'"+word+"'", "kept")
                            newWordList.append(word)
                    elif re.match(r'^[_\W]+$', word):
                        print("'"+word+"'", "removed")
                    else:
                        print("'"+word+"'", "kept")
                        newWordList.append(word)
                print("WORDS2: ", newWordList)

                corrected_text = " ".join(newWordList)

                # Display for testing
                print(corrected_text)

                # Get the true item name by double checking it with the gamepedia page
                rep = {" ": "+"}
                rep = dict((re.escape(k), v) for k, v in rep.items())
                pattern = re.compile("|".join(rep.keys()))
                search_text = pattern.sub(lambda m: rep[re.escape(m.group(0))], corrected_text).replace("__", "_").lstrip("()").strip("_-.,")
                corrected_text = self.getFullItemName(search_text)
                true_name = corrected_text
                print(search_text, " to correct ", corrected_text)

                if corrected_text == None:
                    print("Unexpected error:", "Couldn't convert short to full")
                    mainTryAttempt = mainTryAttempt + 1
                    continue

                
                # Regex replacement for building the item name for the URL
                rep = {" ": "_", "$": "", "/": "_", r"[\/\\\n|_]*": "_", "muzzle": "muzzlebrake", "brake": "", "7.6239": "7.62x39",
                    "5.5645": "5.56x45", "MPS": "MP5", "Flash hider": "Flashhider", "]": ")", "[": "(", "sung": "sunglasses",
                    "asses": "", "Tactlcal": "Tactical", "AK-103-762x39": "", "l-f": "l_f",  "away": "", "MK2": "Mk.2", '"Klassika"': "Klassika",
                    "^['^a-zA-Z_]*$": "%E2%80%98", "AT-2": "AI-2", "®": "", "§": "5", "__": "_", "___": "", "xX": "X",
                    "Bastion dust cover for AK": "Bastion_dust_cover_for_%D0%B0%D0%BA", "PDC dust cover for AK-74": "PDC_dust_cover_for_%D0%B0%D0%BA-74",
                    "DSCRX": "D3CRX", "((": "(", "))": ")"} # define desired replacements here
                
                # use these lines to do the replacement
                rep = dict((re.escape(k), v) for k, v in rep.items())
                pattern = re.compile("|".join(rep.keys()))
                corrected_text = pattern.sub(lambda m: rep[re.escape(m.group(0))], corrected_text).replace("__", "_").lstrip("()").strip("_-.,")
                
                # Display for testing
                print(corrected_text)

                # cv2.imshow('thresh', threshold)
                
                # Further clean up to get rid of rogue '_i' or 'i_' that made it past the filters
                # if corrected_text.endswith("_i"):
                #     corrected_text = corrected_text[:-2]
                # if corrected_text.startswith("_i"):
                #     corrected_text = corrected_text[:2]            

                # scrape tarkov-market.com/item/Item_name_here
                URL_org = 'https://tarkov-market.com/item/'+corrected_text
                URL = URL_org.lower()
                tryCounter = 1
                tryLimit = 2
                page = None
                page2 = None
                while tryCounter <= tryLimit:
                    try:
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
                            URL = 'https://tarkov-market.com/item/'+corrected_text.lower().capitalize()
                        tryCounter = tryCounter + 1
                        continue
                if tryCounter > tryLimit:
                    print("Unexpected error:", "No Page Found")
                    mainTryAttempt = mainTryAttempt + 1
                    continue

                if page is None or page.status_code != 200:
                    print("Unable to find tarkov-market page")
                    print("="*80)
                    continue
                
                # Scrape the gamepedia item webpage for more details
                try:
                    URL2 = 'https://escapefromtarkov.gamepedia.com/'+true_name
                    page2 = requests.get(URL2)
                    if page2.status_code != 200:
                        raise Exception("Error Code: ", page2.status_code)
                    else:
                        print("REQUEST2 GOOD")
                except Exception as e:
                    print("Unexpected error:", "No Page Found for Gamepedia")

                if page2 is None or page2.status_code != 200:
                    print("Unable to find gamepedia page")
                    print("="*80)
                    continue

                # Break the loop as we've found the item information
                found = True

            if page.status_code != 200:
                mainTryAttempt = mainTryAttempt + 1
                continue

            # Parse scraped tarkov-market page
            tm_soup = BeautifulSoup(page.content, 'html.parser')
            # Parse scraped gamepedia page
            gp_soup = BeautifulSoup(page.content, 'html.parser')

            # Get all the price values and quest information
            itemLastLowSoldPrice = tm_soup.find("div", {"class": "price last"}).text
            item24hrAvgPrice = tm_soup.findAll("div", {"class": "price-row"})[0].findChildren()[0].get_text()
            traderName = tm_soup.findAll("div", {"class": "desc"})[2].parent.find("div", {"class": "title"}).find("a").get_text()
            itemTraderPrice = tm_soup.findAll("div", {"class": "desc"})[2].parent.find("div", {"class": "price"}).get_text()
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

            print("PARSED INFO: ", itemLastLowSoldPrice, item24hrAvgPrice, traderName, itemTraderPrice, "\n", quests)
            # Print to seperate diferent runs
            print("="*80)

            # Popup display information/position dictionary
            display_info = {
                "itemName": corrected_text,
                "itemLastLowSoldPrice": itemLastLowSoldPrice,
                "item24hrAvgPrice": item24hrAvgPrice,
                "traderName": traderName,
                "itemTraderPrice": itemTraderPrice,
                "quests": quests,
                }
            display_info.update(self.display_info_init)

            # Make the popup string message
            popupStr = ('{}\nLast lowest price: {}\n24hr Avg: {}\n{}: {}\n{}'.format(
            display_info["itemName"], display_info["itemLastLowSoldPrice"],
            display_info["item24hrAvgPrice"], display_info["traderName"],
            display_info["itemTraderPrice"], display_info["quests"]
            ))

            # Get the multiprocess lock and update the gui window
            lock.acquire()
            self.gui_queue.put([popupStr, display_info])
            # app.pop_always_on_top(popupStr, display_info)
            lock.release()
            
            # Stop the runloop for this process
            self.need_quit = True

class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]

def queryMousePosition():
    pt = POINT()
    windll.user32.GetCursorPos(byref(pt))
    return { "x": pt.x, "y": pt.y}

def remove_prefix(text, prefix):
    return text[text.startswith(prefix) and len(prefix):]

def secondMax(list1):
    if len(list1) <= 1:
        return list1[0]
    mx=max(list1[0],list1[1]) 
    secondmax=min(list1[0],list1[1]) 
    n =len(list1)
    for i in range(2,n): 
        if list1[i]>mx: 
            secondmax=mx
            mx=list1[i] 
        elif list1[i]>secondmax and \
            mx != list1[i]: 
            secondmax=list1[i]
    return secondmax
