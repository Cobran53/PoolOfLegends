from werkzeug.serving import run_simple
from app import app
from webbrowser import open

if __name__ == '__main__':
    open("http://localhost:5000", new=1, autoraise=True)
    run_simple('localhost', 5000, app)

