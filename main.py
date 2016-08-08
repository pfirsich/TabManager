import datetime
import json
import os
import io
from PIL import Image, ImageTk
import base64
import webbrowser
import concurrent.futures
import requests

profileName = None
profileDir = "{APPDATA}\\Mozilla\\Firefox\\Profiles"

profileDir = profileDir.format(APPDATA=os.environ['APPDATA'])
dirItems = list(os.listdir(profileDir))
if len(dirItems) == 1:
    profileName = dirItems[0]

if profileName == None:
    quit("It seems like you have multiple profiles. Please adjust 'profileName' at the beginning of main.py")

# TODO:
# Support profiles without tree style tabs

class TreeItemBase(object):
    idCounter = 0
    idItemMap = {}

    def __init__(self):
        self.id = TreeItemBase.idCounter
        TreeItemBase.idCounter += 1
        self.title = None
        self.children = []
        self.annotation = None
        self.parent = None
        self.collapsed = False
        self.parentId = None

        TreeItemBase.idItemMap[self.id] = self

    def getName(self):
        return "o" + str(self.id)

    def getLabel(self):
        if self.annotation != None:
            return self.title + " --- # " + self.annotation
        else:
            return self.title

    def reparent(self, newParent):
        if self.parent != None:
            self.parent.children.remove(self)
        newParent.children.append(self)
        self.parentId = newParent.id
        self.parent = newParent

    def changeId(self, newId):
        TreeItemBase.idItemMap.pop(self.id)
        self.id = newId
        TreeItemBase.idItemMap[self.id] = self
        if self.id >= TreeItemBase.idCounter:
            TreeItemBase.idCounter = self.id + 1

    def findParents(self):
        if self.parentId != None:
            self.parent = TreeItemBase.getById(self.parentId)
        for child in self.children:
            child.findParents()

    def totalChildrenCount(self):
        count = 0
        for child in self.children:
            count += 1 + child.totalChildrenCount()
        return count

    def toJSON(self):
        dct = self.__dict__.copy()
        dct.pop("parent")
        return dct

    @staticmethod
    def getById(iid):
        return TreeItemBase.idItemMap[iid]

    @staticmethod
    def getByName(name):
        return TreeItemBase.idItemMap[int(name[1:])]

class Tab(TreeItemBase):
    tabCounter = 0

    def __init__(self, url, title, image):
        TreeItemBase.__init__(self)
        self.title = title
        self.url = url
        self.image = image
        self.tstId = None
        self.tstParent = None

    def __repr__(self):
        return "<Tab: id={}, title={}, url={}>".format(self.id, self.title, self.url)

    def toJSON(self):
        dct = TreeItemBase.toJSON(self)
        dct.pop("tstId")
        dct.pop("tstParent")
        return dct

class Window(TreeItemBase):
    def __init__(self):
        TreeItemBase.__init__(self)

    def setTitle(self, windowIndex):
        self.title = "Window #{0}, {1} Tabs - {2}".format(windowIndex + 1, self.totalChildrenCount(), datetime.datetime.now().strftime("%Y.%m.%d %H:%M:%S"))

    def __repr__(self):
        return "<Window: id = {}, title = {}>".format(self.id, self.title)

    def toJSON(self):
        dct = TreeItemBase.toJSON(self)
        return dct

def JSONSerializer(obj):
    if hasattr(obj, "toJSON"):
        ret = obj.toJSON()
        ret["__" + obj.__class__.__name__ + "__"] = True
        return ret
    else:
        quit("Cannot serialize object")

def JSONDeserializer(dct):
    if "__Tab__" in dct or "__Window__" in dct:
        if "__Tab__" in dct:
            ret = Tab(dct["url"], dct["title"], dct["image"])
        elif "__Window__" in dct:
            ret = Window()
            ret.title = dct["title"]
        else:
            quit("DANGER DANGER!")

        ret.changeId(dct["id"])
        ret.parentId = dct["parentId"]
        ret.annotation = dct["annotation"]
        ret.collapsed = dct["collapsed"]
        ret.children = JSONDeserializer(dct["children"])
        return ret
    else:
        return dct

windows = []
treestyleTabIdMap = {}

def mergeTabs():
    sessionFile = os.path.join(profileDir, profileName, "sessionstore-backups/recovery.js")
    with open(sessionFile, encoding = "utf-8") as inFile:
        ffData = json.load(inFile)
        for windowIndex, window in enumerate(ffData["windows"]):
            win = Window()

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
                    tabObj.reparent(parent)
                else:
                    tabObj.reparent(win)

            win.setTitle(windowIndex)
            windows.append(win)

def loadTabs():
    try:
        with open("tabs.json", "r", encoding = "utf-8") as inFile:
            global windows
            windows = json.load(inFile, object_hook = JSONDeserializer)
        for window in windows:
            window.findParents()
    except FileNotFoundError as e:
        print("tabs.json not found!")

def saveTabs():
    with open("tabs.json", "w", encoding = "utf-8") as outFile:
        json.dump(windows, outFile, default = JSONSerializer, indent=4)

def openTabTree(obj):
    if hasattr(obj, "url"):
        webbrowser.open(obj.url)
    for child in obj.children:
        openTabTree(child)

################################################## GUI

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox, simpledialog
from tkinter.constants import NSEW

class Application(ttk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.master = master
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
        obj = TreeItemBase.getByName(item)
        obj.collapsed = False

    def closeItem(self, event):
        item = self.treeView.selection()[0]
        obj = TreeItemBase.getByName(item)
        obj.collapsed = True

    def cutTab(self):
        selected = self.treeView.selection()
        if len(selected) > 0:
            item = selected[0]

            if isinstance(TreeItemBase.getByName(item), Tab):
                self.tabClipboard = item
            else:
                self.tabClipboard = None

    def insertTab(self):
        selected = self.treeView.selection()

        if len(selected) > 0:
            item = selected[0]

            if self.tabClipboard != None and item != self.tabClipboard:
                toInsert = TreeItemBase.getByName(self.tabClipboard)
                if isinstance(toInsert, Tab):
                    self.treeView.move(self.tabClipboard, item, "end")

                    if toInsert.parent == None:
                        print(toInsert)
                    insertInto = TreeItemBase.getByName(item)
                    toInsert.reparent(insertInto)
                else:
                    print("Windows cannot be inserted!")

    def copyURL(self):
        selected = self.treeView.selection()
        if len(selected) > 0:
            item = selected[0]

            tab = TreeItemBase.getByName(item)
            if hasattr(tab, "url"):
                self.master.clipboard_clear()
                self.master.clipboard_append(tab.url)

    def printTree(self, item):
        print(item)
        for child in self.treeView.get_children(item):
            self.printTree(child)

    def deleteTab(self):
        if len(self.treeView.selection()) > 0:
            if messagebox.askyesno("Delete?", "Are you sure you want to delete the selected tab trees?"):
                for item in self.treeView.selection():
                    obj = TreeItemBase.getByName(item)
                    if isinstance(obj, Window):
                        windows.remove(obj)
                    elif isinstance(obj, Tab):
                        obj.parent.children.remove(obj)
                    else:
                        print(":'(")
                self.treeView.delete(*self.treeView.selection())

    def keyHandler(self, event):
        #print("key", event.char, event.keysym)
        if event.char == "#":
            self.annotateTab()
        elif event.keysym == "Delete":
            self.deleteTab()
        elif event.keysym == "Return":
            self.openTab(None)

    def onQuit(self):
        if messagebox.askyesno("Save?", "Save before quitting?"):
            saveTabs()
        self.master.destroy()

    def addChildren(self, element, rootItem):
        for child in element.children:
            tkImg = Favicon.getByName(child.image).getTKImage()
            item = self.treeView.insert(rootItem, "end", child.getName(), text=child.getLabel(), open=not child.collapsed, image=tkImg)
            self.addChildren(child, item)

    def fillTree(self):
        self.treeView.delete(*self.treeView.get_children())
        for window in windows:
            windowItem = self.treeView.insert("", "end", window.getName(), text=window.getLabel(), open=not window.collapsed, image=windowTKImage, tags=('window',))
            self.addChildren(window, windowItem)

    def saveTabs(self):
        saveTabs()

    def updateFavicons(self, root=None):
        #if root==None: print("update")
        for item in self.treeView.get_children(root):
            obj = TreeItemBase.getByName(item)
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
                    obj = TreeItemBase.getByName(item)
                    obj.annotation = annotation
                    self.treeView.item(item, text=obj.getLabel())
            self.treeView.focus_set()
            self.treeView.focus()

    def openTab(self, event):
        title, message = "Open multiple tabs?", "You are about to open {} tabs. Sure?"

        selection = self.treeView.selection()
        if len(selection) > 0:
            if len(selection) == 1:
                obj = TreeItemBase.getByName(selection[0])
                if len(obj.children) > 0:
                    tabCount = obj.totalChildrenCount()
                    if hasattr(obj, "url"): tabCount += 1 # not a window
                    if messagebox.askyesno(title, message.format(tabCount)):
                        openTabTree(obj)
                else:
                    webbrowser.open(obj.url)
            else:
                if messagebox.askyesno(title, message.format(len(selection))):
                    for item in selection:
                        obj = TreeItemBase.getByName(item)
                        if hasattr(obj, "url"):
                            webbrowser.open(obj.url)

        return "break" # Don't propagate this event - don't open/close the tree view item

    def mergeTabs(self):
        mergeTabs()
        self.fillTree()

def downloadImage(url):
    try:
        r = requests.get(url)
        r.raise_for_status()
        if len(r.content) > 0: # It's surprising how many sites serve favicon files with 0 bytes
            img = Image.open(io.BytesIO(r.content))
            img.thumbnail((16, 16))
        else:
            return whiteImage
    except requests.exceptions.HTTPError as e:
        if r.status_code == 404 or r.status_code >= 500: # actually favicons 404 a lot
            return whiteImage
        else:
            print(url, " - exception: ", e)
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

app = Application(master=root)
root.protocol("WM_DELETE_WINDOW", app.onQuit)
root.after(1000, app.updateFavicons)

app.mainloop()
