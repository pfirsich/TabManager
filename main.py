import datetime
import json
import os
import io
from PIL import Image, ImageTk
import base64
import webbrowser
import concurrent.futures
import requests

profileDir = "C:\\Users\\Joel\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\6efcy1z3.default"

# TODO:
# ~

class Tab(object):
    def __init__(self, url, title, image):
        self.url = url
        self.title = title
        self.image = image
        self.children = []
        self.annotation = None
        self.collapsed = False
        self.tstId = None
        self.tstParent = None
        self.parent = None

    def __repr__(self):
        return "<Tab: {0}, {1} - tstId: {2}, parent: {3}> - children: {4}".format(self.title, self.url, self.tstId, self.tstParent, self.children)

    def toJSON(self):
        dct = self.__dict__.copy()
        dct.pop("parent")
        return dct

class Window(object):
    def __init__(self, windowIndex=None, tabs=None):
        self.annotation = None
        self.collapsed = False
        self.title = ""
        self.children = None
        if windowIndex != None and tabs != None:
            self.set(windowIndex, tabs)

    def set(self, windowIndex, tabs):
        self.title = "Window #{0}, {1} Tabs - {2}".format(windowIndex + 1, len(tabs), datetime.datetime.now().strftime("%Y.%m.%d %H:%M:%S"))
        self.children = tabs

    def __repr__(self):
        return "<Window: title = {0}> - tabs: {1}".format(self.title, self.children)

    def toJSON(self):
        return self.__dict__

def JSONSerializer(obj):
    if hasattr(obj, "toJSON"):
        ret = obj.toJSON()
        ret["__" + obj.__class__.__name__ + "__"] = True
        return ret
    else:
        quit("fuck you")

def JSONDeserializer(dct):
    if "__Tab__" in dct:
        ret = Tab(dct["url"], dct["title"], dct["image"])
        ret.children = JSONDeserializer(dct["children"])
        ret.collapsed = dct["collapsed"]
        ret.tstId = dct["tstId"]
        ret.tstParent = dct["tstParent"]
        ret.annotation = dct["annotation"]
        return ret
    elif "__Window__" in dct:
        ret = Window(0, JSONDeserializer(dct["children"]))
        ret.title = dct["title"]
        ret.annotation = dct["annotation"]
        ret.collapsed = dct["collapsed"]
        return ret
    else:
        return dct

windows = []
treestyleTabIdMap = {}

def mergeTabs():
    with open(os.path.join(profileDir, "sessionstore-backups/recovery.js"), encoding = "utf-8") as inFile:
        ffData = json.load(inFile)
        for windowIndex, window in enumerate(ffData["windows"]):
            win = Window()

            tabList = []
            for tabIndex, tab in enumerate(window["tabs"]):
                entry = tab["entries"][tab["index"] - 1]
                if "title" not in entry:
                    entry["title"] = entry["url"]
                tabObj = Tab(entry["url"], entry["title"], tab["image"])
                tabObj.collapsed = tab["extData"].get("treestyletab-subtree-collapsed", "false") == "true"
                tabObj.tstId = tab["extData"]["treestyletab-id"]
                tabObj.tstParent = tab["extData"].get("treestyletab-parent", None)
                treestyleTabIdMap[tabObj.tstId] = tabObj

                if tabObj.tstParent != None:
                    parent = treestyleTabIdMap[tabObj.tstParent]
                    parent.children.append(tabObj)
                    tabObj.parent = parent
                else:
                    tabList.append(tabObj)
                    tabObj.parent = win

            win.set(windowIndex, tabList)
            windows.append(win)

def loadTabs():
    try:
        with open("tabs.json", "r", encoding = "utf-8") as inFile:
            global windows
            windows = json.load(inFile, object_hook = JSONDeserializer)
    except FileNotFoundError as e:
        print("tabs.json not found!")

def saveTabs():
    with open("tabs.json", "w", encoding = "utf-8") as outFile:
        json.dump(windows, outFile, default = JSONSerializer)

def printSingleTab(tab, depth = 0):
    prefix = ""
    if len(tab.children) > 0:
        if tab.collapsed:
            prefix = "+ "
        else:
            prefix = "- "
    print("    "*depth + prefix + tab.title.encode("utf-8").decode("cp850"))
    for child in tab.children:
        printSingleTab(child, depth + 1)

def printTabs():
    for window in windows:
        print("---- " + window.title)
        for tab in window.children:
            printSingleTab(tab)

def openTabTree(tab):
    webbrowser.open(tab.url)
    for child in tab.children:
        openTabTree(child)

################################################## GUI

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox, simpledialog
from tkinter.constants import NSEW

objNameMap = {}
objNameCounter = 0
def getObjName(obj):
    global objNameCounter
    name = "o" + str(objNameCounter)
    objNameCounter += 1
    objNameMap[name] = obj
    return name

def getObjLabel(obj):
    if obj.annotation != None:
        return obj.title + " --- # " + obj.annotation
    else:
        return obj.title

class Application(ttk.Frame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.grid(sticky=NSEW)
        self.createWidgets()
        self.tabClipboard = None

        if len(windows) == 0:
            messagebox.showwarning("File not found", "tabs.json could not be loaded!")
        else:
            self.fillTree()

    def popup(self, event):
        self.menu.post(event.x_root, event.y_root)

    # http://infohost.nmt.edu/tcc/help/pubs/tkinter/web/ttk-Treeview.html
    def createWidgets(self):
        self.buttonFrame = ttk.Frame(self)
        self.buttonFrame.grid(row=0, sticky=NSEW)
        self.buttonFrame.rowconfigure(0, weight=1)
        self.buttonFrame.columnconfigure(0, weight=1)

        self.mergeTabsButton = ttk.Button(self.buttonFrame, text="Merge", command=self.mergeTabs)
        self.mergeTabsButton.grid(row=0, column=0, sticky=tk.NE)

        self.annotateTabsButton = ttk.Button(self.buttonFrame, text="Annotate", command=self.annotateTab)
        self.annotateTabsButton.grid(row=0, column=1, sticky=tk.NE)

        self.deleteTabButton = ttk.Button(self.buttonFrame, text="Delete", command=self.deleteTab)
        self.deleteTabButton.grid(row=0, column=2, sticky=tk.NE)

        self.saveButton = ttk.Button(self.buttonFrame, text="Save", command=self.saveTabs)
        self.saveButton.grid(row=0, column=3, sticky=tk.NE)

        self.quitButton = ttk.Button(self.buttonFrame, text="Quit", command=self.onQuit)
        self.quitButton.grid(row=0, column=4, sticky=tk.NE)

        self.treeView = ttk.Treeview(self)
        self.treeView.grid(row=1, sticky=NSEW)
        self.treeView.bind("<Double-1>", self.openTab)
        self.treeView.bind("#", self.keyHandler)
        self.treeView.bind("<Key>", self.keyHandler)
        self.treeView.bind("<Button-3>", self.popup)
        self.treeView.bind("<<TreeviewOpen>>", self.openItem)
        self.treeView.bind("<<TreeviewClose>>", self.closeItem)
        self.treeView.tag_configure('window', background='grey')
        self.treeView.tag_configure('window', foreground='white')

        self.treeScroll = ttk.Scrollbar(self)
        self.treeScroll.grid(row=1, column=1, sticky=NSEW)
        self.treeScroll.config(command=self.treeView.yview)
        self.treeView.configure(yscroll=self.treeScroll.set)

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Copy URL", command=self.copyURL)
        self.menu.add_command(label="Cut", command=self.cutTab)
        self.menu.add_command(label="Insert", command=self.insertTab)

    def openItem(self, event):
        item = self.treeView.selection()[0]
        obj = objNameMap[item]
        obj.collapsed = False

    def closeItem(self, event):
        item = self.treeView.selection()[0]
        obj = objNameMap[item]
        obj.collapsed = True

    def cutTab(self):
        selected = self.treeView.selection()
        if len(selected) > 0:
            item = selected[0]

            if item in objNameMap and isinstance(objNameMap[item], Tab):
                self.tabClipboard = item
            else:
                self.tabClipboard = None

    def insertTab(self):
        selected = self.treeView.selection()

        if len(selected) > 0:
            item = selected[0]

            if self.tabClipboard != None and item != self.tabClipboard:
                self.treeView.move(self.tabClipboard, item, "end")

                toInsert = objNameMap[self.tabClipboard]
                if toInsert.parent == None:
                    print(toInsert)
                toInsert.parent.children.remove(toInsert)
                insertInto = objNameMap[item]
                insertInto.children.append(toInsert)

    def copyURL(self):
        selected = self.treeView.selection()
        if len(selected) > 0:
            item = selected[0]

            if item in objNameMap:
                tab = objNameMap[item]
                if hasattr(tab, "url"):
                    self.parent.clipboard_clear()
                    self.parent.clipboard_append(tab.url)
            else:
                print("Unkown tab id (possibly window): ", item)

    def deleteTab(self):
        if len(self.treeView.selection()) > 0:
            if messagebox.askyesno("Delete?", "Are you sure you want to delete the selected tab trees?"):
                for item in self.treeView.selection():
                    obj = objNameMap[item]
                    if isinstance(obj, Window):
                        windows.remove(obj)
                    elif isinstance(obj, Tab):
                        obj.parent.children.remove(obj)
                    else:
                        print(":'(")
                self.treeView.delete(self.treeView.selection())

    def keyHandler(self, event):
        #print("key", event.char, event.keysym)
        if event.char == "#":
            self.annotateTab()
        elif event.keysym == "Delete":
            self.deleteTab()

    def onQuit(self):
        if messagebox.askyesno("Save?", "Save before quitting?"):
            saveTabs()
        self.parent.destroy()

    def addChildren(self, element, rootItem):
        for child in element.children:
            tkImg = Favicon.getByName(child.image).getTKImage()
            item = self.treeView.insert(rootItem, "end", getObjName(child), text=getObjLabel(child), open=not child.collapsed, image=tkImg)
            self.addChildren(child, item)

    def fillTree(self):
        self.treeView.delete(*self.treeView.get_children())
        for window in windows:
            windowItem = self.treeView.insert("", "end", getObjName(window), text=getObjLabel(window), open=not window.collapsed, image=windowTKImage, tags=('window',))
            self.addChildren(window, windowItem)

    def saveTabs(self):
        saveTabs()

    def updateFavicons(self, root=None):
        #if root==None: print("update")
        for item in self.treeView.get_children(root):
            obj = objNameMap[item]
            if hasattr(obj, "image"):
                tkImg = Favicon.getByName(obj.image).getTKImage()
                self.treeView.item(item, image=tkImg)
            self.updateFavicons(item)

        if root == None:
            self.after(1000, self.updateFavicons)

    def annotateTab(self):
        if len(self.treeView.selection()) > 0:
            annotation = simpledialog.askstring("Annotate tab", "Annotation")
            if annotation != None:
                for item in self.treeView.selection():
                    if item in objNameMap:
                        obj = objNameMap[item]
                        obj.annotation = annotation
                        self.treeView.item(item, text=getObjLabel(obj))
                    else:
                        print("Unkown tab id (possibly window): ", item)
            self.treeView.focus_set()
            self.treeView.focus()

    def openTab(self, event):
        item = self.treeView.identify('item', event.x, event.y)

        if item in objNameMap:
            tab = objNameMap[item]
            if len(tab.children) > 0:
                if messagebox.askyesno("Open multiple tabs?", "You are about to open more than one tab. Sure?"):
                    openTabTree(tab)
            else:
                webbrowser.open(tab.url)
        else:
            print("Unkown tab id (possibly window): ", item)
        return "break" # Don't propagate this event - don't open/close the tree view item

    def mergeTabs(self):
        mergeTabs()
        self.fillTree()

def downloadImage(url):
    try:
        r = requests.get(url)
        img = Image.open(io.BytesIO(r.content))
        img.thumbnail((16, 16))
    except BaseException as e:
        print(url, " - exception: ", e)
        return None
    return img

class Favicon(object):
    nameMap = {}
    threadPoolExecutor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

    def __init__(self, name):
        self.name = name
        self.imageObject = None
        self.tkImage = None
        self.downloading = False

        if self.name != None:
            if name.startswith("http"):
                self.imageObject = loadingImage
                self.tkImage = loadingTKImage
                self.iconFuture = Favicon.threadPoolExecutor.submit(downloadImage, self.name)
                self.downloading = True
            elif name.startswith("data:image/png;base64"):
                f = io.BytesIO(base64.b64decode(name[22:]))
                self.imageObject = Image.open(f).convert(mode="RGB")
                self.imageObject.thumbnail((16, 16))
            else:
                self.imageObject = whiteImage
                self.tkImage = whiteTKImage
        else:
            self.imageObject = whiteImage
            self.tkImage = whiteTKImage

    def getTKImage(self):
        if self.tkImage == None:
            if self.imageObject != None:
                self.tkImage = ImageTk.PhotoImage(self.imageObject)
        if self.downloading and self.iconFuture.done():
            img = self.iconFuture.result()
            if img:
                self.imageObject = img
                self.tkImage = ImageTk.PhotoImage(self.imageObject)
            self.downloading = False
        return self.tkImage

    def __repr__(self):
        return "<Favicon: name={}, imageObject={}, tkImage={}>".format(self.name, self.imageObject, self.tkImage)

    @staticmethod
    def getByName(name):
        if name in Favicon.nameMap:
            return Favicon.nameMap[name]
        else:
            fav = Favicon(name)
            Favicon.nameMap[name] = fav
            return fav

loadTabs()

root = tk.Tk()
root.state('zoomed') # maximized
root.title("TabManager")

whiteImage = Image.new(mode="RGB", size=(16, 16), color=(255, 255, 255))
whiteTKImage = ImageTk.PhotoImage(whiteImage)

loadingImage = Image.open("load.png")
loadingImage.thumbnail((16, 16))
loadingTKImage = ImageTk.PhotoImage(loadingImage)

windowImage = Image.open("window.png")
windowImage.thumbnail((16, 16))
windowTKImage = ImageTk.PhotoImage(windowImage)

root.grid_columnconfigure(0, weight=1)
root.grid_rowconfigure(0, weight=1)

app = Application(parent=root)
root.protocol("WM_DELETE_WINDOW", app.onQuit)
root.after(1000, app.updateFavicons)

app.mainloop()
