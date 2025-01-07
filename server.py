import socket
import urllib.parse

def handle_connection(conx):
    req = conx.makefile("b")
    reqline = req.readline().decode("latin-1").strip()
    parts = reqline.split(" ", 2)
    if len(parts) != 3:
        raise ValueError(f"Invalid request line: {reqline}")
    method, url, version = parts
    assert method in ["GET", "POST"] 

    headers = {}
    while True:
        line = req.readline().decode("latin-1")
        if line == "\r\n": break
        header, value = line.split(":", 1)
        headers[header.casefold()] = value.strip()
    if 'content-length' in headers:
        length = int(headers['content-length'])
        body = req.read(length).decode("latin-1")
    else:
        body = None
    
    status, body = do_request(method, url, headers, body)
    response = f"HTTP/1.1 {status}\r\n"
    response += "Conent-Length: {}\r\n".format(len(body.encode("utf-8")))
    response += "\r\n" + body
    conx.send(response.encode("latin-1"))
    conx.close()

def do_request(method, url, headers, body):
    if method == "GET" and url == "/":
        return "200 OK", show_comments()
    elif method == "POST" and url == "/add":
        params = form_decode(body)
        return "200 OK", add_entry(params)
    else:
        return "404 Not Found", not_found(url, method)

def form_decode(body):
    params = {}
    for field in body.split("&"):
        name, value = field.split("=", 1)
        name = urllib.parse.unquote_plus(name)
        value = urllib.parse.unquote_plus(value)
        params[name] = value
    return params

ENTRIES = [ 'Martin was here' ]

def show_comments():
    out = "<!doctype html>"
    out += "<form action=add method=post>"
    out +=   "<p><input name=guest></p>"
    out +=   "<p><button>Sign the book!</button></p>"
    out += "</form>"
    for entry in ENTRIES:
        out += "<p>" + entry + "</p>"
    return out

def not_found(url, method):
    out = "<!doctype html>"
    out += "<h1>{} {} not found!</h1>".format(method, url)
    return out

def add_entry(params):
    if 'guest' in params:
        ENTRIES.append(params['guest'])
    return show_comments()

if __name__ == "__main__":
    s = socket.socket(
        family=socket.AF_INET, 
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    s.bind(('', 8000))
    s.listen()

    while True:
        conx, addr = s.accept()
        print("Received connection from", addr)
        handle_connection(conx)
