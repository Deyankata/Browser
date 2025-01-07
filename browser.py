import socket
import ssl
import os
import time
import gzip
import tkinter
import sys
import tkinter.font
import urllib.parse 

class URL:
    cache = {}

    def __init__(self, url):
        if not is_valid_url(url):
            self.scheme = "about"
            return
        
        # Data scheme for inline HTML support
        if url[:4] == "data":
            self.scheme, self.html_content = url.split(":", 1)
            assert "text/html" in self.html_content
            return

        self.scheme, url = url.split("://", 1)

        # Handle the view-source:http://... syntax so that the browser can print the HTML content
        if "view-source" in self.scheme:
            self.view_source = True
            self.scheme = self.scheme.split(":", 1)[1]
        else:
            self.view_source = False

        assert self.scheme in ["http", "https", "file"]

        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443
        elif self.scheme == "file":
            self.file_path = url
            return

        if "/" not in url:
            url = url + "/"
        self.host, url = url.split("/", 1)

        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

        self.path = "/" + url
    
    def request(self, payload=None, max_redirects=5):
        # Check if the url is malformed
        if self.scheme == "about":
            return "about:blank"
        
        # Check if the URL is cached and still valid
        if self.scheme in ["http", "https"]:
            cache_key = f"{self.scheme}://{self.host}{self.path}"
        else:
            cache_key = ''    
        
        if cache_key in self.cache:
            content, expiration = self.cache[cache_key]
            if time.time() < expiration:
                return content
            
        if self.scheme == "file":
            if os.path.exists(self.file_path):
                with open(self.file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                return content
            else:
                raise FileNotFoundError(f"The file at {self.file_path} does not exist.")
        
        if self.scheme == "data":
            comma_index = self.html_content.find(",")
            if comma_index == -1:
                raise ValueError("Invalid data URL format.")
            content = self.html_content[comma_index + 1:]
            return content
        
        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        
        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)
        
        s.connect((self.host, self.port))

        method = "POST" if payload else "GET"
        request = "{} {} HTTP/1.0\r\n".format(method, self.path)
        if payload:
            length = len(payload.encode("utf-8"))
            request += "Content-Length: {}\r\n".format(length)

        request = f"GET {self.path} HTTP/1.1\r\n"
        request += f"Host: {self.host}\r\n"
        request += "Accept-Encoding: gzip\r\n"
        #request += "Connection: close\r\n"
        request += "User-Agent: Martin\r\n"
        request += "\r\n"

        if payload: request += payload

        try:
            s.send(request.encode("utf-8"))

            response = s.makefile("rb", encoding="utf-8", newline="\r\n")
            statusline = response.readline().decode("utf-8")
            version, status, explanation = statusline.split(" ", 2)

            response_headers = {}
            while True:
                line = response.readline().decode("utf-8")
                if line == "\r\n": break
                header, value = line.split(":", 1)
                response_headers[header.casefold()] = value.strip()
            
            # Check for Transfer-Encoding
            transfer_encoding = response_headers.get("transfer-encoding", "")
            content = b""
            if transfer_encoding == "chunked":
                while True:
                    chunk_size_line = response.readline().strip()
                    if not chunk_size_line:
                        break # No more chunks
                    chunk_size = int(chunk_size_line, 16)
                    if chunk_size == 0:
                        break # Last chunk
                    chunk = response.read(chunk_size)
                    content += chunk
                    # Read the trailing CRLF after the chunk
                    response.readline()
            else:
                content_length = int(response_headers.get("content-length", 0))
                content = response.read(content_length)
            
            # Handle compression
            content_encoding = response_headers.get("content-encoding", "")
            if content_encoding == "gzip":
                content = gzip.decompress(content).decode("utf-8")

            # Handle redirection logic
            if 300 <= int(status) <= 400:
                if max_redirects <= 0:
                    raise Exception("Too many redirects")
                
                new_url = response_headers.get("location")
                if new_url:
                    new_url = urllib.parse.urljoin(f"{self.scheme}://{self.host}", new_url)
                    redirected_url = URL(new_url)
                    return redirected_url.request(max_redirects=max_redirects-1)           

            # Check the Cache-Control header for caching directives
            cache_control = response_headers.get("cache_control", "").lower()
            if "no-store" in cache_control:
                # Do not cache this response
                pass
            elif "max-age" in cache_control:
                max_age = int(cache_control.split('max-age=')[-1].split(",")[0])
                expiration = time.time() + max_age
                self.cache[cache_key] = (content, expiration)
            else:
                # Other cache-control derivatives: do not cache
                pass

            if self.view_source:
                content = content.replace("<", "&lt;")
                content = content.replace(">", "&gt;")

            return content
        except OSError as e:
            print(f"Socket error: {e}")
            s.close()
            return None

    # Function that converts a relative url into a full url
    def resolve(self, url):
        if "://" in url: return URL(url)
        if not url.startswith("/"):
            dir, _ = self.path.rsplit("/", 1)
            while url.startswith("../"):
                _, url = url.split("/",1)
                if "/" in dir:
                    dir, _ = dir.rsplit("/", 1)
            url = dir + "/" + url
        if url.startswith("//"):
            return URL(self.scheme + ":" + url)
        else:
            return URL(self.scheme + "://" + self.host + ":" + str(self.port) + url)

    def __str__(self):
        port_part = ":" + str(self.port)
        if self.scheme == "https" and self.port == 443:
            port_part = ""
        if self.scheme == "http" and self.port == 80:
            port_part = ""
        return self.scheme + "://" + self.host + port_part + self.path

def is_valid_url(url):
        try:
            result = urllib.parse.urlparse(url)
            return all([result.scheme, result.netloc]) or url == "about:blank"
        except ValueError:
            return False

def add_headers(request, headers: dict):
    assert "Host" in request

    for header in headers.keys():
        request += f"{header}: {headers[header]}\r\n"

    return request




class Text:
    def __init__(self, text, parent):
        self.text = text
        self.children = []  # Added for consistency, text node never have children
        self.parent = parent

    def __repr__(self):
        return repr(self.text)

class Element:
    def __init__(self, tag, attributes, parent):
        self.tag = tag
        self.attributes = attributes
        self.children = []
        self.parent = parent
        self.is_focused = False
    
    def __repr__(self):
        return "<" + self.tag + ">"

class Rect:
    def __init__(self, left, top, right, bottom):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom
    
    def containsPoint(self, x, y):
        return x >= self.left and x < self.right \
            and y >= self.top and y < self.bottom

class Chrome:
    def __init__(self, browser):
        self.browser = browser
        self.font = get_font(15, "normal", "roman")
        self.font_height = self.font.metrics("linespace")
        self.padding = 5
        self.tabbar_top = 0
        self.tabbar_bottom = self.font_height + 2*self.padding
        self.urlbar_top = self.tabbar_bottom
        self.urlbar_bottom = self.urlbar_top + self.font_height + 2*self.padding
        self.bottom = self.urlbar_bottom
        self.focus = None
        self.address_bar = ""
        
        # New tab button 
        plus_width = self.font.measure("+") + 2*self.padding
        self.newtab_rect = Rect(
            self.padding, self.padding,
            self.padding + plus_width,
            self.padding + self.font_height
        )

        # Back button
        back_width = self.font.measure("<") + 2*self.padding
        self.back_rect = Rect(
            self.padding,
            self.urlbar_top + self.padding,
            self.padding + back_width,
            self.urlbar_bottom - self.padding
        )

        # address bar
        self.address_rect = Rect(
            self.back_rect.top + self.padding,
            self.urlbar_top + self.padding,
            WIDTH - self.padding,
            self.urlbar_bottom - self.padding
        )
    
    def tab_rect(self, i):
        tabs_start = self.newtab_rect.right + self.padding
        tab_width = self.font.measure("Tab X") + 2*self.padding
        return Rect(
            tabs_start + tab_width * i, self.tabbar_top,
            tabs_start + tab_width * (i+1), self.tabbar_bottom
        )
    
    def blur(self):
        self.focus = None
    
    def click(self, x, y):
        self.focus = None
        if self.newtab_rect.containsPoint(x, y):
            self.browser.new_tab((URL("https://browser.engineering/")))
        elif self.back_rect.containsPoint(x, y):
            self.browser.active_tab.go_back()
        elif self.address_rect.containsPoint(x, y):
            self.focus = "address bar"
            self.address_bar = ""
        else:
            for i, tab in enumerate(self.browser.tabs):
                if self.tab_rect(i).containsPoint(x, y):
                    self.browser.active_tab = tab
                    break
    
    def keypress(self, char):
        if self.focus == "address bar":
            self.address_bar += char
            return True
        return False
    
    def enter(self):
        if self.focus == "address bar":
            self.browser.active_tab.load(URL(self.address_bar))
            self.focus = None

    def backspace(self):
        if self.focus == "address bar" and len(self.address_bar) > 0:
            self.address_bar = self.address_bar[:-1]  # Create a new string by cutting the last letter of the old one

    def paint(self):
        cmds = []

        # Draw white bar behind tabs that they always stay "ontop"
        cmds.append(DrawRect(
            Rect(0, 0, WIDTH, self.bottom),
            "white"
        ))
        cmds.append(DrawLine(
            0, self.bottom, WIDTH,
            self.bottom, "black", 1
        ))

        cmds.append(DrawOutline(self.newtab_rect, "black", 1))
        cmds.append(DrawText(
            self.newtab_rect.left + self.padding,
            self.newtab_rect.top,
            "+", self.font, "black"
        ))

        # Draw tabs
        for i, tab in enumerate(self.browser.tabs):
            bounds = self.tab_rect(i)
            cmds.append(DrawLine(
                bounds.left, 0, bounds.left, bounds.bottom,
                "black", 1
            ))
            cmds.append(DrawLine(
                bounds.right, 0, bounds.right, bounds.bottom,
                "black", 1
            ))
            cmds.append(DrawText(
                bounds.left + self.padding, bounds.top + self.padding,
                "Tab {}".format(i), self.font, "black"
            ))

            # Identify active tab
            if tab == self.browser.active_tab:
                cmds.append(DrawLine(
                    0, bounds.bottom, bounds.left, bounds.bottom,
                    "black", 1
                ))
                cmds.append(DrawLine(
                    bounds.right, bounds.bottom, WIDTH, bounds.bottom,
                    "black", 1
                ))
        
        # Draw back button
        cmds.append(DrawOutline(self.back_rect, "black", 1))
        cmds.append(DrawText(
            self.back_rect.left + self.padding,
            self.back_rect.top,
            "<", self.font, "black"
        ))

        # Draw address bar
        cmds.append(DrawOutline(self.address_rect, "black", 1))
        if self.focus == "address bar":
            cmds.append(DrawText(
                self.address_rect.left + self.padding,
                self.address_rect.top,
                self.address_bar, self.font, "black"
            ))

            # Draw cursor
            w = self.font.measure(self.address_bar)
            cmds.append(DrawLine(
                self.address_rect.left + self.padding + w,
                self.address_rect.top,
                self.address_rect.left + self.padding + w,
                self.address_rect.bottom,
                "red", 1
            ))
        else:
            url = str(self.browser.active_tab.url)
            cmds.append(DrawText(
                self.address_rect.left + self.padding,
                self.address_rect.top,
                url, self.font, "black"
        ))
            
        return cmds

class Browser:
    def __init__(self):
        self.tabs = []
        self.active_tab = None        
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window,
            width=WIDTH,
            height=HEIGHT,
            bg="white",
        )
        self.url = None
        self.chrome = Chrome(self)

        self.canvas.pack(fill="both", expand=True)
        self.window.bind("<Configure>", self.on_resize)

        # Scrolling

        self.window.bind("<Down>", self.handle_down)
        self.window.bind("<Up>", self.handle_up)

        # Bind the mouse scroll events on different systems
        if sys.platform.startswith("win"):
            self.window.bind("<MouseWheel>", self.handle_mouse_scroll)
        elif sys.platform == "darwin":
            self.window.bind("<MouseWheel>", self.handle_mouse_scroll)
        else:
            self.window.bind("<Button-4>", self.handle_mouse_scroll_linux)
            self.window.bind("<Button-5>", self.handle_mouse_scroll_linux)
    
        self.window.bind("<Button-1>", self.handle_click)
        self.window.bind("<Key>", self.handle_key)
        self.window.bind("<Return>", self.handle_enter)
        self.window.bind("<BackSpace>", self.handle_backspace)
        self.window.bind("<Button-2>", self.handle_click)

    def new_tab(self, url):
        new_tab = Tab(HEIGHT - self.chrome.bottom)
        new_tab.load(url)
        self.active_tab = new_tab
        self.tabs.append(new_tab)
        self.draw()

    def handle_down(self, e):
        self.active_tab.scrolldown()
        self.draw()
    
    def handle_up(self, e):
        self.active_tab.scrollup()
        self.draw()
    
    def handle_mouse_scroll(self, e):
        self.active_tab.on_mouse_scroll(e)
        self.draw()
    
    def on_resize(self, e):
        global WIDTH, HEIGHT
        WIDTH, HEIGHT = e.width, e.height
        self.active_tab.document = DocumentLayout(self.active_tab.nodes)
        self.active_tab.document.layout()
        self.active_tab.display_list = []
        paint_tree(self.active_tab.document, self.active_tab.display_list)
        self.draw()

    def handle_click(self, e):
        if e.y < self.chrome.bottom:
            self.focus = None
            self.chrome.click(e.x, e.y)
        else:
            self.focus = "content"
            self.chrome.blur()
            tab_y = e.y - self.chrome.bottom
            if e.num == 1:    # Left click
                self.active_tab.click(e.x, tab_y, mid_click=False)
            elif e.num == 2:  # Middle click
                self.new_tab(self.active_tab.click(e.x, tab_y, mid_click=True)) 
        self.draw()
    
    def handle_key(self, e):
        if len(e.char) == 0: return
        if not (0x20 <= ord(e.char) < 0x7f): return
        if self.chrome.keypress(e.char):
            self.draw()
        elif self.focus == "content":
            self.active_tab.keypress(e.char)
            self.draw()
    
    def handle_enter(self, e):
        self.chrome.enter()
        self.draw()

    def handle_backspace(self, e):
        self.chrome.backspace()
        self.draw()
    
    def draw(self):
        self.canvas.delete("all")
        self.active_tab.draw(self.canvas, self.chrome.bottom)
        for cmd in self.chrome.paint():
            cmd.execute(0, self.canvas)

WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
SCROLL_HEIGHT = 100

class Tab:  
    def __init__(self, tab_height):
        self.url = None
        self.display_list = []
        self.nodes = []
        self.scroll = 0
        self.tab_height = tab_height
        self.history = []
        self.focus = None

    def draw_scrollbar(self, canvas, tab_offset):
        # Get last element of display list to get the content height
        y = self.display_list[-1].bottom

        # If the whole content fits onscreen
        if y < HEIGHT:
            self.url = None
            return

        # Calculate the size of the scrollbar
        content_height = y
        viewport_height = HEIGHT
        scrollbar_height = SCROLL_HEIGHT
        thumb_size = max(((viewport_height / content_height) * scrollbar_height), 20)

        # Calculate the scrollbar position
        scroll_fraction = self.scroll / (content_height - viewport_height)
        thumb_position = scroll_fraction * (viewport_height - thumb_size)

        canvas.create_rectangle(WIDTH - 5, thumb_position + tab_offset, WIDTH, thumb_position + thumb_size + tab_offset, fill='blue')

    def render(self):
        style(self.nodes, sorted(self.rules, key=cascade_priority))
        self.document = DocumentLayout(self.nodes)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)

    def keypress(self, char):
        if self.focus:
            self.focus.attributes["value"] += char
            self.render()

    def click(self, x, y, mid_click=False):
        self.focus = None

        # Account for scrolling
        y += self.scroll

        objs = [obj for obj in tree_to_list(self.document, [])
                if obj.x <= x < obj.x + obj.width
                and obj.y <= y < obj.y + obj.height]
        if not objs: return
        
        elt = objs[-1].node
        while elt:
            if isinstance(elt, Text):
                pass
            elif elt.tag == "a" and "href" in elt.attributes:
                url = self.url.resolve(elt.attributes["href"])
                if mid_click:   # If middle click is pressed, return url to Browser, to open a new tab
                    return url
                else:
                    return self.load(url)
            elif elt.tag == "input":
                elt.attributes["value"] = ""
                if self.focus:
                    self.focus.is_focused = False
                self.focus = elt
                elt.is_focused = True
                return self.redner()
            elif elt.tag == "button":
                while elt:
                    if elt.tag == "form" and "action" in elt.attributes:
                        return self.submit_form(elt)
            elt = elt.parent

    def submit_form(self, elt):
        inputs = [node for node in tree_to_list(elt, []) 
                  if isinstance(node, Element) 
                  and node.tag == "input"
                  and "name" in node.attributes]
        
        body = ""
        for input in inputs:
            name = input.attributes["name"]
            value = input.attributes.get("value", "")
            name = urllib.parse.quote(name)
            value = urllib.parse.quote(value)
            body += "&" + name + "=" + value
        body = body[1:]

        url = self.url.resolve(elt.attributes["action"])
        self.load(url, body)

    def on_mouse_scroll(self, e):
        if e.delta > 0:
            self.scrollup()
        else:
            self.scrolldown()
    
    def on_mouse_scroll_linux(self, e):
        if e.num == 4:
            self.scrollup()
        elif e.num == 5:
            self.scrolldown()

    def scrolldown(self):
        max_y = max(self.document.height + 2*VSTEP - self.tab_height, 0)
        self.scroll = min(self.scroll + SCROLL_HEIGHT, max_y)
                    
    def scrollup(self):
        if self.scroll != 0:
            self.scroll -= SCROLL_STEP

    def draw(self, canvas, offset):
        canvas.delete("all")
        self.draw_scrollbar(canvas, offset)
        for cmd in self.display_list:
            if cmd.rect.top > self.scroll + self.tab_height: continue
            if cmd.rect.bottom < self.scroll: continue
            cmd.execute(self.scroll - offset, canvas)

    def go_back(self):
        if len(self.history) > 1:
            self.history.pop()
            back = self.history.pop()
            self.load(back)

    def load(self, url, payload=None):
        # Get website body
        self.history.append(url)
        self.url = url
        body = url.request(payload)
        if body == "about:blank":
            self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT, bg="white")
            self.canvas.pack(fill=tkinter.BOTH, expand=True)
        
        # Parse html tree
        self.nodes = HTMLParser(body).parse()
        
        # Apply styles
        self.rules = DEFAULT_STYLE_SHEET.copy()
        links = [node.attributes["href"]
                 for node in tree_to_list(self.nodes, [])
                 if isinstance(node, Element)
                 and node.tag == "link"
                 and node.attributes.get("rel") == "stylesheet"
                 and "href" in node.attributes]
        for link in links:
            style_url = url.resolve(link)
            try:
                body = style_url.request()
            except:
                continue
            self.rules.extend(CSSParser(body).parse())

        # Layout nodes and print
        self.render()


class HTMLParser:
    SELF_CLOSING_TAGS = [
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr"
    ]

    HEAD_TAGS = [
        "base", "basefont", "bgsound", "noscript",
        "link", "meta", "title", "style", "script",
    ]
    
    def __init__(self, body):
        self.body = body
        self.unfinished = []
    
    def parse(self):
        text = ""
        in_tag = False
        in_comment = False

        i = 0
        while i < len(self.body):
            if self.body[i] == "<":
                # Check if it's a comment
                if self.body[i: i+4] == "<!--":
                    i += 4  # Skip comment's opening sequence
                    in_comment = True
                    continue

                in_tag = True
                if text: self.add_text(text)
                text = ""
                i += 1
            elif self.body[i:i+3] == "-->" and in_comment:
                in_comment = False
                i += 3
                continue
            elif self.body[i] == ">" and not in_comment:
                in_tag = False
                self.add_tag(text)
                text = ""
                i += 1
            elif self.body[i] == "&" and not in_tag and not in_comment:  # Check if the next sequence is an entity (&lt; or &gt;)
                if is_entity(self.body[i:i+4]):
                    if self.body[i+1] =="l":
                        text += "<"
                    else:
                        text += ">"
                    i += 4   # Skip entity by incrementing index
                else:
                    text += "&"
                    i += 1
            elif not in_comment:
                text += self.body[i]
                i += 1
            else:
                if i == len(self.body)-1 and in_comment:
                    raise Exception("Non-closed comment")
                i+=1

        if not in_tag and text:
            self.add_text(text)
            i += 1
        
        return self.finish()
    
    def add_text(self, text):
        if text.isspace(): return
        self.implicit_tags(None)
        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)
    
    def add_tag(self, tag):
        tag, attributes = self.get_attributes(tag)
        if tag.startswith("!"): return
        self.implicit_tags(tag)

        if tag.startswith("/"):
            if len(self.unfinished) == 1: return   # no unfinished node can be added to very last tag
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        elif tag in self.SELF_CLOSING_TAGS:
            parent = self.unfinished[-1]
            node = Element(tag, attributes, parent)
            parent.children.append(node)
        else:
            parent = self.unfinished[-1] if self.unfinished else None  # very first tag doesn't have a parent
            node = Element(tag, attributes, parent)
            self.unfinished.append(node)
    
    def finish(self):
        if not self.unfinished:
            self.implicit_tags(None)

        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        return self.unfinished.pop()
    
    def get_attributes(self, text):
        parts = text.split()
        tag = parts[0].casefold()
        attributes = {}
        for attrpair in parts[1:]:
            if "=" in attrpair:
                key, value = attrpair.split("=", 1)
                if len(value) > 2 and value[0] in ["'", "\""]:
                    value = value[1:-1]   # remove quotes around attribute
                attributes[key.casefold()] = value
            else:
                attributes[attrpair.casefold()] = ""
        return tag, attributes

    def implicit_tags(self, tag):
        while True:
            open_tags = [node.tag for node in self.unfinished]
            if open_tags == [] and tag != "html":
                self.add_tag("html")
            elif open_tags == ["html"] \
                and tag not in ["head", "body", "/html"]:
                if tag in self.HEAD_TAGS:
                    self.add_tag("head")
                else:
                    self.add_tag("body")
            elif open_tags == ["html", "head"] and \
                tag not in ["/head"] + self.HEAD_TAGS:
                self.add_tag("/head")
            else:
                break


FONTS = {}
SUPERSCRIPT_OFFSET = 5

BLOCK_ELEMENTS = [
        "html", "body", "article", "section", "nav", "aside", "h1", "h2", "h3", "h4", "h5", "h6", 
        "hgroup", "header", "footer", "address", "p", "hr", "pre", "blockquote", "ol", "ul", "menu",
        "li", "dl", "dt", "dd", "figure", "figcaption", "main", "div", "table", "form", "fieldset",
        "legend", "details", "summary"
    ]
class BlockLayout:
    def __init__(self, node, parent, previous, canvas_width):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []
        self.x = None
        self.y = None
        self.width = None
        self.height = None
        self.canvas_width = canvas_width
        self.weight = "normal"
        self.style = "roman"
        self.size = 12
        self.center_next_text = False # Flag for centering text
        self.superscript = False      # Flag for superscript
        self.small_caps = False       # Flag for small caps
        self.small_caps_size = 8
    
    def layout(self):
        self.x = self.parent.x
        self.width = self.parent.width

        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y
        
        mode = self.layout_mode()
        if mode == "block":
            previous = None
            for child in self.node.children:
                next = BlockLayout(child, self, previous, WIDTH)
                self.children.append(next)
                previous = next
        else:
            self.new_line()
            self.recurse(self.node)

        for child in self.children:
            child.layout()
        
        self.height = sum([child.height for child in self.children])

    def layout_mode(self):
        if isinstance(self.node, Text):
            return "inline"
        elif any([isinstance(child, Element) and \
                  child.tag in BLOCK_ELEMENTS for child in self.node.children]):
            return "block"
        elif self.node.children:
            return "inline"
        elif self.node.children or self.node.tag == "input":
            return "inline"
        else:
            return "block"

    def input(self, node):
        w = INPUT_WIDTH_PX
        if self.cursor_x + w > self.width:
            self.new_line()
        line = self.children[-1]
        previous_word = line.children[-1] if line.children else None
        input = InputLayout(node, line, previous_word)
        line.children.append(input)

        weight = node.style["font-weight"]
        style = node.style["font-style"]
        if style == "normal": style = "roman"
        size = int((float(node.style["font-size"][:-2])) * .75)
        font = get_font(size, weight, style)

        self.cursor_x += w + font.measure(" ")

    def recurse(self, node):
        if isinstance(node, Text):
            if self.center_next_text:
                self.center_text(node.text)     # Center this token's text
                self.center_next_text = False  # Reset the flag
            else:
                for word in node.text.split():
                    self.word(node, word)
        else:
            if node.tag == "br":
                self.new_line()
            elif node.tag == "input" or node.tag == "button":
                self.input(node)
            for child in node.children:
                self.recurse(child)
                
    def word(self, node, word):
        weight = node.style["font-weight"]
        style = node.style["font-style"]
        if style == "normal": style = "roman"
        size = int(float(node.style["font-size"][:-2]) * .75)
        font = get_font(size, weight, style)
        w = font.measure(word)

        if self.small_caps: 
            word, font = self.apply_small_caps(word, font)

        if self.cursor_x + w > self.width:
            if check_hyphen(word):
                self.hyphen_word(word, font)
                return
            else:
                self.new_line()
                
        # If the word contains hyphen encodings, remove them when hyphenation is not necessary
        if check_hyphen(word):
            word_hypen_slit = word.split("\N{SOFT HYPHEN}")
            word = "".join(word_hypen_slit)

        line = self.children[-1]
        previous_word = line.children[-1] if line.children else None
        text = TextLayout(node, word, line, previous_word)
        line.children.append(text)
        self.cursor_x += w + font.measure(" ")

    def self_rect(self):
        return Rect(self.x, self.y,
                    self.x + self.width, self.y + self.height)

    def new_line(self):
        self.cursor_x = 0
        last_line = self.children[-1] if self.children else None
        new_line = LineLayout(self.node, self, last_line)
        self.children.append(new_line)

    def should_paint(self):
        return isinstance(self.node, Text) or (self.node.tag != "input" and self.node.tag != "button")

    def flush(self): pass
        
    def paint(self):
        cmds = []
        
        bgcolor = self.node.style.get("background-color", "transparent")

        if bgcolor != "transparent":
            rect = DrawRect(self.self_rect(), bgcolor)
            cmds.append(rect)

        return cmds

    def center_text(self, text):
        font = get_font(self.size, self.weight, self.style)
        text_width = font.measure(text)
        self.cursor_x = (self.canvas_width - text_width) // 2
        self.line.append((self.cursor_x, text, self.superscript, font))
        self.new_line()  # Finish the centered text line
    
    def hyphen_word(self, word, font):
        # Split the word into parts by soft hyphen positions
        word_parts = word.split("\N{SOFT HYPHEN}")
        best_split_index = None
        best_fit_size = float('inf') 

        # Try breaking at each soft hyphen
        for i in range(1, len(word_parts) + 1):
            first_part = "".join(word_parts[:i]) + "-" 
            first_part_size = font.measure(first_part)
            
            # If this fits and is the closest to max_width, use it
            if first_part_size + self.cursor_x + HSTEP <= WIDTH and WIDTH - (first_part_size + self.cursor_x + HSTEP) < best_fit_size:
                best_split_index = i
                best_fit_size = WIDTH - (first_part_size + self.cursor_x + HSTEP)

        # If no valid split was found, use the longest possible
        if best_split_index is None:
            best_split_index = 1  # Fallback to the first split
        
        # Get the parts of the word based on the best split
        first_part = "".join(word_parts[:best_split_index]) + "-"
        second_part = "".join(word_parts[best_split_index:])

        # Update cursor and draw first part
        self.line.append((self.cursor_x, first_part, self.superscript, font))
        first_part_size = font.measure(first_part)
        self.cursor_x += first_part_size
        
        self.new_line()

        # Draw the second part on the new line
        self.line.append((self.cursor_x, second_part, self.superscript, font))

    def  apply_small_caps(self, word, font):
        if word.islower():
            small_caps_font = get_font(self.small_caps_size, "bold", self.style)
            word = word.upper()
            return word, small_caps_font
        else:
            return word, font

INPUT_WIDTH_PX = 200

class InputLayout:
    def __init__(self, node, parent, previous):
        self.node = node
        self.children = []
        self.parent = parent
        self.previous = previous
    
    def layout(self):
        weight = self.node.style["font-weight"]
        style = self.node.style["font-style"]
        if style == "normal": style = "roman"
        size = int(float(self.node.style["font-size"][:-2]) * .75)
        self.font = get_font(size, weight, style)

        self.width = INPUT_WIDTH_PX

        if self.previous:
            space = self.previous.font.measure(" ")
            self.x =self.previous.x + space + self.previous.width
        else:
            self.x = self.parent.x
        
        self.height = self.font.metrics("linespace")
    
    def should_paint(self):
        return True

    def paint(self):
        cmds = []
        bgcolor = self.node.style.get("background-color", "transparent")

        if bgcolor != "transparent":
            rect = DrawRect(self.self_rect(), bgcolor)
            cmds.appned(rect)
        
        if self.node.tag == "input":
            text = self.node.attributes.get("value", "")
        elif self.node.tag == "button":
            if len(self.node.children) == 1 and isinstance(self.node.children[0], Text):
                text = self.node.children[0].text
            else:
                print("Ignoring HTML contents inside button")
                text = ""
        
        color = self.node.style["color"]
        cmds.append(DrawText(self.x, self.y, text, self.font, color))
        
        if self.node.is_focused:
            cx = self.x + self.font.measure(text)
            cmds.append(DrawLine(cx, self.y, cx, self.y + self.height, "black", 1))

        return cmds

class LineLayout:
    def __init__(self, node, parent, previous):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []
        self.x = None
        self.y = None
        self.width = None
        self.height = None
    
    def layout(self):
        self.width = self.parent.width
        self.x = self.parent.x

        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        for word in self.children:
            word.layout()
        
        max_ascent = max([word.font.metrics("ascent") for word in self.children])
        baseline = self.y + 1.25 * max_ascent
        for word in self.children:
            word.y = baseline - word.font.metrics("ascent")
        max_descent = max([word.font.metrics("descent") for word in self.children])

        self.height = 1.25 * (max_ascent + max_descent)
    
    def should_paint(self):
        return True

    def paint(self):
        return []

class TextLayout:
    def __init__(self, node, word, parent, previous):
        self.node = node
        self.word = word
        self.children = []
        self.parent = parent
        self.previous = previous
        self.x = None
        self.y = None
        self.width = None
        self.height = None
        self.font = None
    
    def layout(self):
        weight = self.node.style["font-weight"]
        style = self.node.style["font-style"]
        if style == "normal": style = "roman"
        size = int(float(self.node.style["font-size"][:-2]) * .75)
        self.font = get_font(size, weight, style)

        self.width = self.font.measure(self.word)

        if self.previous:
            space = self.previous.font.measure(" ")
            self.x = self.previous.x + space + self.previous.width
        else:
            self.x = self.parent.x
        
        self.height = self.font.metrics("linespace")

    def should_paint(self):
        return True

    def paint(self):
        color = self.node.style["color"]
        return [DrawText(self.x, self.y, self.word, self.font, color)]

class DocumentLayout:
    def __init__(self, node):
        self.node = node
        self.parent = None
        self.children = []
        self.x = None
        self.y = None
        self.width = None
        self.height = None
    
    def layout(self):
        child = BlockLayout(self.node, self, None, WIDTH)
        self.children.append(child)
        self.width = WIDTH - 2*HSTEP
        self.x = HSTEP
        self.y = VSTEP
        child.layout()
        self.height = child.height
        
    def should_paint(self):
        return True

    def paint(self):
        return []

class CSSParser:
    def __init__(self, s):
        self.s = s
        self.i = 0
    
    # Increment index past every whitespace character
    def whitespace(self):
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    # Increment index through any word character and store parsed data
    # from where the function started to where it move
    def word(self):
        start = self.i
        while self.i < len(self.s):
            if self.s[self.i].isalnum() or self.s[self.i] in "#-.%":
                self.i += 1
            else:
                break
        if not (self.i > start):
            raise Exception("index i hasn't advanced")
        return self.s[start:self.i]

    # Increment index through a literal (e.g. ':')
    def literal(self, literal):
        if not (self.i < len(self.s) and self.s[self.i] == literal):
            raise Exception("Not a literal")
        self.i += 1
    
    # Parse property-value pair
    def pair(self):
        prop = self.word()
        self.whitespace()
        self.literal(':')
        self.whitespace()
        val = self.word()
        return prop.casefold(), val
    
    # Parse sequences (e.g. 'style' attributes are a sequence of property-value pairs)
    def body(self):
        pairs = {}
        while self.i < len(self.s) and self.s[self.i] != "}":
            try:
                prop, val = self.pair()
                pairs[prop.casefold()] = val
                self.whitespace()
                self.literal(';')
                self.whitespace()
            except Exception:
                why = self.ignore_until([';', "}"])
                if why == ";":
                    self.literal(";")
                    self.whitespace()
                else:
                    break

        return pairs

    # Ignore at a character from a given character set 
    # in order to ignore certain property-value pairs
    def ignore_until(self, chars): 
        while self.i < len(self.s):
            if self.s[self.i] in chars:
                return self.s[self.i]
            else:
                self.i += 1
        return None
    
    # Function to parse selectors
    def selector(self):
        out = TagSelector(self.word().casefold())
        self.whitespace()
        while self.i < len(self.s) and self.s[self.i] != "{":
            tag = self.word()
            descendant = TagSelector(tag.casefold())
            out = DescendantSelector(out, descendant)
            self.whitespace()
        return out

    # Parse a sequence of selectors and block (a CSS file)
    def parse(self):
        rules = []
        while self.i < len(self.s):
            try:
                self.whitespace()
                selector = self.selector()
                self.literal("{")
                self.whitespace()
                body = self.body()
                self.literal("}")
                rules.append((selector, body))
            except Exception:
                why = self.ignore_until(["}"])
                if why == "}":
                    self.literal("}")
                    self.whitespace()
                else:
                    break
        return rules

class TagSelector:
    def __init__(self, tag):
        self.tag = tag
        self.priority = 1

    # Tests whether the selector matches an element
    def matches(self, node):
        return isinstance(node, Element) and self.tag == node.tag
    
class DescendantSelector:
    def __init__(self, ancestor, descendant):
        self.ancestor = ancestor
        self.descendant = descendant
        self.priority = ancestor.priority + descendant.priority
    
    def matches(self, node):
        if not self.descendant.matches(node): return False
        while node.parent:
            if self.ancestor.matches(node.parent): return True
            node = node.parent
        return False

class DrawText:
    def __init__(self, x1, y1, text, font, color):
        self.rect = Rect(x1, y1,
                    x1 + font.measure(text), y1 + font.metrics("linespace"))
        self.text = text
        self.font = font
        self.bottom = y1 + font.metrics("linespace")
        self.color = color

    def execute(self, scroll, canvas):
        canvas.create_text(
            self.rect.left, self.rect.top - scroll,
            text=self.text,
            font=self.font,
            anchor='nw',
            fill=self.color
        )

class DrawRect:
    def __init__(self, rect, color):
        self.rect = rect 
        self.color = color
    
    def execute(self, scroll, canvas):
        canvas.create_rectangle(
            self.rect.left, self.rect.top - scroll,
            self.rect.right, self.rect.bottom - scroll,
            width=0,
            fill=self.color
        )

class DrawOutline:
    def __init__(self, rect, color, thickness):
        self.rect = rect
        self.color = color
        self.thickness = thickness
    
    def execute(self, scroll, canvas):
        canvas.create_rectangle(
            self.rect.left, self.rect.top - scroll,
            self.rect.right, self.rect.bottom - scroll,
            width=self.thickness,
            outline=self.color
        )

class DrawLine:
    def __init__(self, x1, y1, x2, y2, color, thickness):
        self.rect = Rect(x1, y1, x2, y2)
        self.color = color
        self.thickness = thickness
    
    def execute(self, scroll, canvas):
        canvas.create_line(
            self.rect.left, self.rect.top - scroll,
            self.rect.right, self.rect.bottom - scroll,
            fill=self.color, width=self.thickness
        )

DEFAULT_STYLE_SHEET = CSSParser(open("browser.css").read()).parse()

INHERITED_PROPERTIES = {
    "font-size": "16px",
    "font-style": "normal",
    "font-weight": "normal",
    "color": "black",
}

def get_font(size, weight, style):
    key = (size, weight, style)
    if key not in FONTS:
        font = tkinter.font.Font(size=size, weight=weight, slant=style)
        label = tkinter.Label(font=font)
        FONTS[key] = (font, label)
    return FONTS[key][0]

# Function that saves the parsed style attribute in the node's style field
def style(node, rules):
    node.style = {}
    
    for property, default_value in INHERITED_PROPERTIES.items():
        if node.parent:
            node.style[property] = node.parent.style[property]
        else:
            node.style[property] = default_value
    
    for selector, body in rules:
        if not selector.matches(node): continue
        for property, value in body.items():
            node.style[property] = value

    if isinstance(node, Element) and "style" in node.attributes:
        pairs = CSSParser(node.attributes["style"]).body()
        for property, value in pairs.items():
            node.style[property] = value
    if node.style["font-size"].endswith("%"):
        if node.parent:
            parent_font_size = node.parent.style["font-style"]
        else:
            parent_font_size = INHERITED_PROPERTIES["font-size"]
        node_pct = float(node.style["font-size"][:-1]) / 100
        parent_px = float(parent_font_size[:-2])
        node.style["font-size"] = str(node_pct * parent_px) + "px"
    for child in node.children:
        style(child, rules)

def paint_tree(layout_object, display_list):
    if layout_object.should_paint():
        display_list.extend(layout_object.paint())

    for child in layout_object.children:
        paint_tree(child, display_list)

def print_tree(node, indent=0):
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent + 2)

def cascade_priority(rule):
    selector, body = rule
    return selector.priority

# Function that turns a tree into a list of trees
def tree_to_list(tree, list):
    list.append(tree)
    for child in tree.children:
        tree_to_list(child, list)
    return list

def is_entity(text):
    return text == "&lt;" or text == "&gt;"

def check_hyphen(word):
    return "\N{SOFT HYPHEN}" in word

if __name__ == "__main__":
    import sys
    Browser().new_tab(URL(sys.argv[1]))
    tkinter.mainloop()

# if __name__ == "__main__":
#     import sys
#     Browser().new_tab(URL("https://browser.engineering/styles.html"))
#     tkinter.mainloop()

# Test URL's

# data:text/html,Hello world! &lt;div&gt;
# http://example.org/
# https://browser.engineering/examples/example1-simple.html
# file://D:/Martin/Projects/Browser/example.txt
# view-source:http://example.org/
# http://browser.engineering/redirect
# https://browser.engineering/examples/example3-sizes.html
# https://browser.engineering/html.html
# https://browser.engineering/

# Journey to the West
# https://browser.engineering/examples/xiyouji.html

