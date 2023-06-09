from werkzeug.serving import run_simple
from app import app
from webbrowser import open
import configparser


if __name__ == '__main__':
    config = configparser.ConfigParser()
    config.read("!config.ini")
    if config.getboolean("Browser Options", "open_browser_on_start"):
        open("http://localhost:5000", new=1, autoraise=True)
    else:
        print("No broswer at starting chosen. Open http://localhost:5000 to see the home page!")
    run_simple('localhost', 5000, app)

