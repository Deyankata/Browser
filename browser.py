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
    def __init__(self, text):
        self.text = text

class Tag:
    def __init__(self, tag):
        self.tag = tag

WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
SCROLL_HEIGHT = 100

class Browser:
    
    def __init__(self):
        self.display_list = []
        self.tokens = []
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
        self.display_list = Layout(self.tokens).display_list
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
        self.tokens = lex(body)
        self.display_list = Layout(self.tokens, WIDTH).display_list
        self.draw()

FONTS = {}

class Layout:
    def __init__(self, tokens, canvas_width):
        self.display_list = []
        self.line = []
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.canvas_width = canvas_width
        self.weight = "normal"
        self.style = "roman"
        self.size = 12
        self.center_next_text = False # Flag for centering text

        for tok in tokens:
            self.token(tok)
        
        self.flush()
    
    def token(self, tok):
        if isinstance(tok, Text):
            if self.center_next_text:
                self.center_text(tok.text)     # Center this token's text
                self.center_next_text = False  # Reset the flag
            else:
                for word in tok.text.split():
                    self.word(word)
        elif tok.tag == "i":
            self.style = "italic"
        elif tok.tag == "/i":
            self.style = "roman"
        elif tok.tag == "b":
            self.weight = "bold"
        elif tok.tag == "/b":
            self.weight = "normal"
        elif tok.tag == "small":
            self.size -= 2
        elif tok.tag == "/small":
            self.size += 2
        elif tok.tag == "big":
            self.size += 4
        elif tok.tag == "/big":
            self.size -= 4
        elif tok.tag == "br":
            self.flush()
        elif tok.tag == "/p":
            self.flush()
            self.cursor_y += VSTEP
        elif tok.tag == "h1 class=\"title\"":
            self.flush() # End the current line before centering
            self.center_next_text = True  # Set flag to center the next text token
        elif tok.tag == "/h1":
            self.flush()
            self.cursor_x = HSTEP
    
    def word(self, word):
        font = get_font(self.size, self.weight, self.style)
        w = font.measure(word)

        if self.cursor_x + w > WIDTH - HSTEP:
            self.flush()

        if  word == "\n":   # New line, move the cursor down
            self.cursor_x = HSTEP
            self.cursor_y += VSTEP + 2
        else:
            self.line.append((self.cursor_x, word, font))
            self.cursor_x += w + font.measure(" ")
    
    def flush(self):
        if not self.line: return
        metrics = [font.metrics() for x, word, font in self.line]
        max_ascent = max([metric["ascent"] for metric in metrics])

        baseline = self.cursor_y + 1.25 * max_ascent

        for x, word, font in self.line:
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
        self.line.append((self.cursor_x, text, font))
        self.flush()  # Finish the centered text line

def get_font(size, weight, style):
    key = (size, weight, style)
    if key not in FONTS:
        font = tkinter.font.Font(size=size, weight=weight, slant=style)
        label = tkinter.Label(font=font)
        FONTS[key] = (font, label)
    return FONTS[key][0]

def lex(body):
    out = []
    buffer = ""
    in_tag = False

    i = 0
    while i < len(body):
        if body[i] == "<":
            in_tag = True
            if buffer: out.append(Text(buffer))
            buffer = ""
            i += 1
        elif body[i] == ">":
            in_tag = False
            out.append(Tag(buffer))
            buffer = ""
            i += 1
        elif body[i] == "&" and not in_tag:  # Check if the next sequence is an entity (&lt; or &gt;)
            if is_entity(body[i:i+4]):
                if body[i+1] =="l":
                    buffer += "<"
                else:
                    buffer += ">"
                i += 4   # Skip entity by incrementing index
            else:
                buffer += "&"
                i += 1
        else:
            buffer += body[i]
            i += 1
    if not in_tag and buffer:
        out.append(Text(buffer))
        i += 1
    
    return out

def is_entity(text):
    return text == "&lt;" or text == "&gt;"

# if __name__ == "__main__":
#     import sys
#     Browser().load(URL(sys.argv[1]))
#     tkinter.mainloop()

if __name__ == "__main__":
    import sys
    Browser().load(URL("https://browser.engineering/text.html"))
    tkinter.mainloop()

# Test URL's

# data:text/html,Hello world! &lt;div&gt;
# http://example.org/
# https://browser.engineering/examples/example1-simple.html
# file://D:/Martin/Projects/Browser/example.txt
# view-source:http://example.org/
# http://browser.engineering/redirect
# https://browser.engineering/examples/example3-sizes.html

# Journey to the West
# https://browser.engineering/examples/xiyouji.html

