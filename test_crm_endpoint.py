import requests
import sys

# Simulation of a request to the local server
# Needs a valid session usually, but we can check if it returns 401 (which means route exists) or 404
try:
    # Login first? Or just check if endpoint exists.
    # Flask login usually requires session cookie.
    # We can try to cheat by looking at the code, but checking 401 is enough to prove route existence.
    resp = requests.get('http://127.0.0.1:5000/clientes/4281292/historial_json')
    print(f"Status: {resp.status_code}")
    # If 302 to login, that's expected.
    # If 404, that's bad.
    if resp.status_code == 404:
        print("Endpoint not found!")
    else:
        print("Endpoint seems to exist (even if 302/401)")
except Exception as e:
    print(f"Error: {e}")
