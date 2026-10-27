import aiohttp, asyncio
from aiohttp import web
from random import choices
from collections import deque
from os import environ

BUFFER_WRITE_SIZE = int(environ.get("BUFFER_WRITE_SIZE", default=64 * 1024))
MAX_BUFFER_SIZE = int(environ.get("MAX_BUFFER_SIZE", default=BUFFER_WRITE_SIZE * 8))
DICTIONARY_FILE = environ.get("DICTIONARY_FILE", default="dictionary.txt")

HOST = environ.get("HOST", default="127.0.0.1")
PORT = int(environ.get("PORT", default=6340))
SCHEME = "http"
BASE_URL = environ.get("BASE_URL", default=f"{SCHEME}://{HOST}:{PORT}")

DICTIONARY = [str(i) for i in range(10,100) if i % 10 != 0]
try:
    with open("dictionary.txt", "r") as f:
        DICTIONARY = [x for w in f.readlines() if len(x := w.strip().lower()) > 0]
except FileNotFoundError as e:
    print("Failed to find dictionary file, continuing with fallback")

class Session:
    def __init__(self, name, max_buffer_size=MAX_BUFFER_SIZE):
        self.name = name
        self.buffer: deque[bytes] = deque()
        self.buffer_size = 0
        self.max_buffer_size = max_buffer_size
        self.lock = asyncio.Condition()
        self.sender_finished = False
        self.sender_error = None
        self.receiver_finished = False
        self.receiver_error = None
    
    async def close_sender(self, error=None):
        self.sender_finished = True
        self.sender_error = error
    
    async def close_receiver(self, error=None):
        self.receiver_finished = True
        self.receiver_error = error

    async def write(self, data: bytes):
        async with self.lock:
            self.buffer.append(data)
            self.buffer_size += len(data)
            self.lock.notify()
            if self.buffer_size > self.max_buffer_size:
                raise RuntimeError(f"Buffer overflow in session {self.name}")

    async def read(self) -> bytes | None:
        async with self.lock:
            while not self.buffer and not self.sender_finished:
                await self.lock.wait()
            if self.buffer: # FIXME: is this if statement necessary?
                chunk = self.buffer.popleft()
                self.buffer_size -= len(chunk)
                return chunk
            if not self.buffer and self.sender_finished:
                return None
            raise RuntimeError("How did we get here?")

class Molniya:
    def __init__(self, base_url = None):
        self.base_url = base_url
        self.sessions = {}

        self.app = web.Application()
        self.app.router.add_get("/", self.handler_root)
        self.app.router.add_get("/receive/{session_name}", self.handler_receive)
        self.app.router.add_put("/send/{session_name}", self.handler_send)

    def run(self, host="0.0.0.0", port=8000):
        web.run_app(self.app, host=host, port=port)
    
    async def create_session(self, name) -> Session | None:
        if name not in self.sessions:
            session = Session(name)
            self.sessions[name] = session
            return session
        else:
            return None
    
    async def get_session(self, name) -> Session | None:
        return self.sessions.get(name)

    async def cleanup_session(self, name):
        if name in self.sessions:
            del self.sessions[name]
        else:
            raise RuntimeError(f"Tried to cleanup session {name} but it does not exists")

    async def handler_root(self, request: web.Request) -> web.Response:
        recommended_id = None
        while recommended_id is None or recommended_id in self.sessions:
            recommended_id = '-'.join(choices(DICTIONARY, k=3))
        
        send_url    = f"{self.base_url or ""}/send/{recommended_id}"
        receive_url = f"{self.base_url or ""}/receive/{recommended_id}"

        user_agent = request.headers.get("User-Agent")
        if user_agent is not None and "curl" in user_agent:
            response_text = f"Send to: {send_url}\n" \
                            f"Receive at: {receive_url}\n\n" \
                            f"curl command:\n  curl {send_url} --upload-file FILENAME"
            content_type = "text/plain"
        else:
            response_text = f"""<!DOCTYPE html>""" \
            f"""<html lang="en"><head><title>Molniya</title><script>""" \
            f"""async function automagic() {{ try {{""" \
            f"""  await navigator.clipboard.writeText("{send_url}");""" \
            f"""  alert("The send URL was copied to your clipboard");""" \
            f"""  window.location.href="{receive_url}";""" \
            f"""}} catch (e) {{ console.error("Failed: ", e) }} }}""" \
            f"""</script><body>""" \
            f"""Send to: <a href="{send_url}">{send_url}</a><br>""" \
            f"""Receive at: <a href="{receive_url}">{receive_url}</a><br>""" \
            f"""<button onclick="automagic()">Download from the browser</button>""" \
            f"""</body></html>"""
            content_type = "text/html"
        
        return web.Response(body=response_text, content_type=content_type)

    async def handler_receive(self, request: web.Request) -> web.Response:
        session_name = request.match_info["session_name"]
        session = await self.create_session(session_name)
        if session is None:
            return web.Response(body="A receiver with this name is busy listening", status=423)
        
        response = web.StreamResponse(headers={"Content-Type":"application/octet-stream"})
        response.enable_chunked_encoding()
        await response.prepare(request)

        try:
            while True:
                chunk = await session.read()
                if chunk is None:
                    break # Sender is done and buffer empty
                await response.write(chunk)
            await session.close_receiver()
        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError) as e:
            await session.close_receiver(e)
        finally:
            await self.cleanup_session(session_name)

        return response

    async def handler_send(self, request: web.Request) -> web.Response:
        session_name = request.match_info["session_name"]
        session = await self.get_session(session_name)
        if session is None:
            return web.Response(body="This session does not exist. Is the receiver ready and listening?", status=404)
        
        try:
            async for chunk in request.content.iter_chunked(64 * 1024):
                if session.receiver_finished:
                    raise RuntimeError("The remote receiver disconnected")
                if not chunk:
                    break
                await session.write(chunk)
            await session.close_sender()
        except Exception as e:
            await session.close_sender(e)
        
        return web.Response()

if __name__ == "__main__":
    molniya = Molniya(BASE_URL)
    molniya.run(host=HOST, port=PORT)