# Molniya

Simple file transfer without storage.

---

This is a simple HTTP server which proxies chunked transfer of a file between a sender and a receiver. 

## Usage

### Command-line:
```sh
# On the receiver side
curl http://localhost:6340/receive/cat-pictures

# On the sender side
curl http://localhost:6340/receive/cat-pictures --upload-file cats.tar.gz

# Or, if you want random IDs to copy:
curl http://localhost:6340/
```

## Browser
- Visit `http://localhost:6340/`
- Press `Download from the browser`
- The link for the sending side is in your clipboard

Alternatively, you can still visit `http://localhost:6340/receive/your-chosen-id` and it will work the same.

## Setup
Simply run `main.py` with Python 3.

Note that it's best to run this behind a reverse proxy, both for HTTPS and for authentication.

### Environment Variables
```
BUFFER_WRITE_SIZE=65536
MAX_BUFFER_SIZE=524288 # BUFFER_WRITE_SIZE * 8
HOST=127.0.0.1
PORT=6340
BASE_URL=http://127.0.0.1:6340 # http://{HOST}:{PORT}
DICTIONARY_FILE=dictionary.txt # For generating random IDs
```

## TODO
- [ ] File integrity mechanism..?
- [ ] Support HTTPS by default
- [ ] Support authentication