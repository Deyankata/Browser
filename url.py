import socket
import ssl
import os
import time
import gzip
from urllib.parse import urljoin

class URL:
    cache = {}

    def __init__(self, url):
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

"""
parameters:

header_names - list of different header names
header_values - list of corresponding header values
"""
def add_headers(request, headers: dict):
    assert "Host" in request

    for header in headers.keys():
        request += f"{header}: {headers[header]}\r\n"

    return request

def show(body):
    in_tag = False

    i = 0
    skip_entity = 4
    while i < len(body):
        if body[i] == "<":
            in_tag = True
            i += 1
        elif body[i] == ">":
            in_tag = False
            i += 1
        elif body[i] == "&" and not in_tag:  # Check if the next sequence is an entity (&lt; or &gt;)
            if is_entity(body[i:i+4]):
                if body[i+1] =="l":
                    print("<", end="")
                else:
                    print(">", end="")
                i += skip_entity
            else:
                print("&", end="")
                i += 1
        elif not in_tag:
            print(body[i], end="")
            i += 1
        elif in_tag:
            i += 1
          
def is_entity(text):
    return text == "&lt;" or text == "&gt;"

def load(url):
    body = url.request()
    show(body)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        load(URL(sys.argv[1]))
    else:
        load(URL("file://D:/Martin/Projects/Browser/default.txt"))

# if __name__ == "__main__":
#     import sys
#     load(URL("http://example.org/"))


# Test URL's

# data:text/html,Hello world! &lt;div&gt;
# http://example.org/
# https://browser.engineering/examples/example1-simple.html
# file://D:/Martin/Projects/Browser/example.txt
# view-source:http://example.org/
# http://browser.engineering/redirect


