import socket
import ssl
import os
import time
import gzip
import tkinter
import sys
import tkinter.font
from urllib.parse import urljoin, urlparse

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
    
    def request(self, max_redirects=5):
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
                with open(self.file_path, 'r', encoding='utf8') as file:
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

        request = f"GET {self.path} HTTP/1.1\r\n"
        request += f"Host: {self.host}\r\n"
        request += "Accept-Encoding: gzip\r\n"
        #request += "Connection: close\r\n"
        request += "User-Agent: Martin\r\n"
        request += "\r\n"

        try:
            s.send(request.encode("utf8"))

            response = s.makefile("rb", encoding="utf8", newline="\r\n")
            statusline = response.readline().decode("utf8")
            version, status, explanation = statusline.split(" ", 2)

            response_headers = {}
            while True:
                line = response.readline().decode("utf8")
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
                content = gzip.decompress(content).decode("utf8")

            # Handle redirection logic
            if 300 <= int(status) <= 400:
                if max_redirects <= 0:
                    raise Exception("Too many redirects")
                
                new_url = response_headers.get("location")
                if new_url:
                    new_url = urljoin(f"{self.scheme}://{self.host}", new_url)
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
            print(f"Socke error: {e}")
            s.close()
            return None

def is_valid_url(url):
        try:
            result = urlparse(url)
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
    
    def __repr__(self):
        return "<" + self.tag + ">"

WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
SCROLL_HEIGHT = 100

class Browser:
    
    def __init__(self):
        self.display_list = []
        self.nodes = []
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window,
            width=WIDTH,
            height=HEIGHT
        )

        self.canvas.pack(fill="both", expand=True)
        self.window.bind("<Configure>", self.on_resize)


        # Scrolling

        self.scroll = 0
        self.window.bind("<Down>", self.scrolldown)
        self.window.bind("<Up>", self.scrollup)

        # Bind the mouse scroll events on different systems
        if sys.platform.startswith("win"):
            self.window.bind("<MouseWheel>", self.on_mouse_scroll)
        elif sys.platform == "darwin":
            self.window.bind("<MouseWheel>", self.on_mouse_scroll)
        else:
            self.window.bind("<Button-4>", self.on_mouse_scroll_linux)
            self.window.bind("<Button-5>", self.on_mouse_scroll_linux)
    
    def on_resize(self, e):
        global WIDTH, HEIGHT
        WIDTH, HEIGHT = e.width, e.height
        self.display_list = Layout(self.nodes, WIDTH).display_list
        self.draw()

    def on_mouse_scroll(self, e):
        if e.delta > 0:
            self.scrollup(e)
        else:
            self.scrolldown(e)
    
    def on_mouse_scroll_linux(self, e):
        if e.num == 4:
            self.scrollup(e)
        elif e.num == 5:
            self.scrolldown(e)

    def scrolldown(self, e):
        # Get last display list element in order to get the position at the end of the page
        _, y, _, _ = self.display_list[-1]
        if y - self.scroll > HEIGHT - VSTEP: # Prevents scrolling beyond the last display list element
            self.scroll += SCROLL_STEP
            self.draw()

    def scrollup(self, e):
        if self.scroll != 0:
            self.scroll -= SCROLL_STEP
            self.draw()

    def draw_scrollbar(self):
        # Get last element of display list to get the content height
        _, y, _, _ = self.display_list[-1]

        # If the whole content fits onscreen
        if y < HEIGHT:
            return

        # Calculate the size of the scrollbar
        content_height = y
        viewport_height = HEIGHT
        scrollbar_height = SCROLL_HEIGHT
        thumb_size = max(((viewport_height / content_height) * scrollbar_height), 20)

        # Calculate the scrollbar position
        scroll_fraction = self.scroll / (content_height - viewport_height)
        thumb_position = scroll_fraction * (viewport_height - thumb_size)

        self.canvas.create_rectangle(WIDTH - 5, thumb_position, WIDTH, thumb_position + thumb_size, fill='blue')

    def draw(self):
        self.canvas.delete("all")
        self.draw_scrollbar()
        for x,y,c,f in self.display_list:
            if y > self.scroll + HEIGHT: continue   # skip items below the visible area
            if y + VSTEP < self.scroll: continue    # skip items above the visible area
            self.canvas.create_text(x, y-self.scroll, text=c, anchor='nw', font=f)
    
    def load(self, url):
        body = url.request()
        if body == "about:blank":
            self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT, bg="white")
            self.canvas.pack(fill=tkinter.BOTH, expand=True)
        self.nodes = HTMLParser(body).parse()
        self.display_list = Layout(self.nodes, WIDTH).display_list
        self.draw()

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

        i = 0
        while i < len(self.body):
            if self.body[i] == "<":
                in_tag = True
                if text: self.add_text(text)
                text = ""
                i += 1
            elif self.body[i] == ">":
                in_tag = False
                self.add_tag(text)
                text = ""
                i += 1
            elif self.body[i] == "&" and not in_tag:  # Check if the next sequence is an entity (&lt; or &gt;)
                if is_entity(self.body[i:i+4]):
                    if self.body[i+1] =="l":
                        text += "<"
                    else:
                        text += ">"
                    i += 4   # Skip entity by incrementing index
                else:
                    text += "&"
                    i += 1
            else:
                text += self.body[i]
                i += 1
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
                attributes[key.casefold()] = value
                if len(value) > 2 and value[0] in ["'", "\""]:
                    value = value[1:-1]   # remove quotes around attribute
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

class Layout:
    def __init__(self, nodes, canvas_width):
        self.display_list = []
        self.line = []
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.canvas_width = canvas_width
        self.weight = "normal"
        self.style = "roman"
        self.size = 12
        self.center_next_text = False # Flag for centering text
        self.superscript = False      # Flag for superscript
        self.small_caps = False       # Flag for small caps
        self.small_caps_size = 8

        self.recurse(nodes)
        
        self.flush()
    
    def open_tag(self, tag):
        if tag == "i":
            self.style = "italic"
        elif tag == "b":
            self.weight = "bold"
        elif tag == "small":
            self.size -= 2
        elif tag == "big":
            self.size += 4
        elif tag == "br":
            self.flush()
        elif tag == "h1 class=\"title\"":
            self.flush() # End the current line before centering
            self.center_next_text = True  # Set flag to center the next text tag
        elif tag == "sup":
            self.size = int(self.size / 2)
            self.superscript = True
        elif tag == "abbr":
            self.small_caps = True
    
    def close_tag(self, tag):
        if tag == "i":
            self.style = "roman"  
        elif tag == "b":
            self.weight = "normal"
        elif tag == "small":
            self.size += 2
        elif tag == "big":
            self.size -= 4
        elif tag == "p":
            self.flush()
            self.cursor_y += VSTEP
        elif tag == "h1":
            self.flush()
            self.cursor_x = HSTEP
        elif tag == "sup":
            self.size *= 2
            self.superscript = False
        elif tag == "abbr":
            self.small_caps = False
    
    def recurse(self, tree):
        if isinstance(tree, Text):
            if self.center_next_text:
                self.center_text(tree.text)     # Center this token's text
                self.center_next_text = False  # Reset the flag
            else:
                for word in tree.text.split():
                    self.word(word)
        else:
            self.open_tag(tree.tag)
            for child in tree.children:
                self.recurse(child)
            self.close_tag(tree.tag)
    
    def word(self, word):
        font = get_font(self.size, self.weight, self.style)
        w = font.measure(word)

        if self.small_caps: 
            word, font = self.apply_small_caps(word, font)

        if self.cursor_x + w > WIDTH - HSTEP:
            if check_hyphen(word):
                self.hyphen_word(word, font)
                return
            else:
                self.flush()
                
        # If the word contains hyphen encodings, remove them when hyphenation is not necessary
        if check_hyphen(word):
            word_hypen_slit = word.split("\N{SOFT HYPHEN}")
            word = "".join(word_hypen_slit)

        if  word == "\n":   # New line, move the cursor down
            self.cursor_x = HSTEP
            self.cursor_y += VSTEP + 2
        else:
            self.line.append((self.cursor_x, word, self.superscript, font))
            self.cursor_x += w + font.measure(" ")
    
    def flush(self):
        if not self.line: return
        metrics = [font.metrics() for _, _, _, font in self.line]
        max_ascent = max([metric["ascent"] for metric in metrics])

        baseline = self.cursor_y + 1.25 * max_ascent

        for x, word, superscript, font in self.line:
            if superscript:
                y = baseline - font.metrics("ascent") - SUPERSCRIPT_OFFSET
            else:
                y = baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font))
        
        max_descent = max([metric["descent"] for metric in metrics])
        self.cursor_y = baseline + 1.25 * max_descent

        self.cursor_x = HSTEP
        self.line = []

    def center_text(self, text):
        font = get_font(self.size, self.weight, self.style)
        text_width = font.measure(text)
        self.cursor_x = (self.canvas_width - text_width) // 2
        self.line.append((self.cursor_x, text, self.superscript, font))
        self.flush()  # Finish the centered text line
    
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
        
        self.flush()

        # Draw the second part on the new line
        self.line.append((self.cursor_x, second_part, self.superscript, font))

    def  apply_small_caps(self, word, font):
        if word.islower():
            small_caps_font = get_font(self.small_caps_size, "bold", self.style)
            word = word.upper()
            return word, small_caps_font
        else:
            return word, font


def get_font(size, weight, style):
    key = (size, weight, style)
    if key not in FONTS:
        font = tkinter.font.Font(size=size, weight=weight, slant=style)
        label = tkinter.Label(font=font)
        FONTS[key] = (font, label)
    return FONTS[key][0]

def print_tree(node, indent=0):
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent + 2)

def is_entity(text):
    return text == "&lt;" or text == "&gt;"

def check_hyphen(word):
    return "\N{SOFT HYPHEN}" in word

if __name__ == "__main__":
    import sys
    Browser().load(URL(sys.argv[1]))
    tkinter.mainloop()

# if __name__ == "__main__":
#     import sys
#     Browser().load(URL("file://D:/Martin/Projects/Browser/example.txt"))
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

