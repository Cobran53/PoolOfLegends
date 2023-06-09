import time

from flask import Flask, render_template
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, \
    ElementNotVisibleException, ElementNotSelectableException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options as ChromeOptions

from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.edge.options import Options as EdgeOptions

from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.firefox.options import Options as FirefoxOptions

import werkzeug  # server
import os
import sys
import atexit  # do something at exit
import re  # regular expressions
import configparser

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/113.0"}

browsers = {
    "Firefox": {'name': 'Firefox', 'driver': webdriver.Firefox, 'service': FirefoxService,
                'manager': GeckoDriverManager, 'options': FirefoxOptions},
    "Chrome": {'name': 'Chrome', 'driver': webdriver.Chrome, 'service': ChromeService,
               'manager': ChromeDriverManager, 'options': ChromeOptions},
    "Edge": {'name': 'Edge', 'driver': webdriver.Edge, 'service': EdgeService,
             'manager': EdgeChromiumDriverManager, 'options': EdgeOptions},
}
driver = None

config = configparser.ConfigParser()
config.read("!config.ini")

browsers_in_order = [
    config["Preferred Browser"]["first_browser"],
    config["Preferred Browser"]["second_browser"],
    config["Preferred Browser"]["third_browser"],
    *[str(i) for i in browsers.keys()]
]
browsers_in_order_no_duplicates = []
[browsers_in_order_no_duplicates.append(x) for x in browsers_in_order if x not in browsers_in_order_no_duplicates and
 x in ["Firefox", "Edge", "Chrome"]]

# Iterate through each browser and try to initialize it
for key in browsers_in_order_no_duplicates:
    browser = browsers[key]
    try:
        options = browser['options']()
        print(config.getboolean("Browser Options", "show_images"))
        if not config.getboolean("Browser Options", "show_images"):
            # Add options to disable image loading
            options.add_argument('--blink-settings=imagesEnabled=false')
            if browser['name'] == "Firefox":
                options.set_preference('permissions.default.image', 2)
            if browser['name'] == 'Edge':
                options.use_chromium = True
        else:
            print("we keep the image")
        service = browser['service'](browser['manager']().install())
        driver = browser['driver'](service=service, options=options)
        print(f"Successfully initialized {browser['name']} browser.")
        break  # Exit the loop if browser initialization is successful
    except Exception as e:
        print(f"Failed to initialize {browser['name']} browser: {e}")

# Check if a browser was successfully initialized
if driver is None:
    print("No compatible browser found. Exiting...")
else:
    cookies_wait_time = config.getfloat("Wait Time", "cookies_wait_time")
    show_more_wait_time = config.getfloat("Wait Time", "show_more_wait_time")
    # Quit the browser at exit
    atexit.register(lambda: driver.quit())

if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    static_folder = os.path.join(sys._MEIPASS, 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
else:
    app = Flask(__name__)

cookies_enabled = False


def keep_only_numbers(string):
    """Removes all characters except numbers and the decimal point from a string before returning it."""
    return re.sub(r'[^0-9.]', '', string)


def get_champion_winrate(champion, role, patch=None, retry=0):
    """Returns a dict contening for each enemy champion, the winrate against it and the nuimber of match.

    patch should be written as "13_9" or "13_10". ("13.9" or "13_09" won't work.)
    retry is the number of time we retried due to a stale element.
    """
    global cookies_enabled
    champion = champion.lower()
    role = role.lower()
    try:
        assert role in ["top", "jungle", "middle", "adc", "support"]
    except AssertionError:
        print(role)
        raise

    if patch:  # 13_10, not 13.10
        url = f"https://u.gg/lol/champions/{champion}/counter?patch={patch}&role={role}"
    else:
        url = f"https://u.gg/lol/champions/{champion}/counter?role={role}"
    print("URL visited:", url)
    driver.get(url)

    if not cookies_enabled:
        try:
            if WebDriverWait(driver, show_more_wait_time).until(
                    EC.visibility_of_element_located((By.CLASS_NAME, "qc-cmp2-summary-buttons"))):
                buttons_cookies = driver.find_element(By.CLASS_NAME, "qc-cmp2-summary-buttons")
                buttons = buttons_cookies.find_elements(By.TAG_NAME, "button")
                cookies_enabled = True
                driver.execute_script("arguments[0].click();", buttons[2])
        except NoSuchElementException as excep:
            print("No cookies to accept. If it crashes, try making the wait time higher.")
            print("The exception is :", excep)
        except StaleElementReferenceException as excep:
            if retry < 5:
                print("The cookies element got stale. Retrying", retry + 1, "/5")
                return get_champion_winrate(champion, role, patch, retry + 1)
            else:
                print("Something has gone wrong. An element got stale. Here's the exception.", excep)
        except Exception as excep:
            print("An unknown exception happened. Here the message", excep, type(excep), sep="\n")

    ignore_list = [StaleElementReferenceException, ElementNotVisibleException,
                   ElementNotSelectableException, NoSuchElementException]
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    try:
        if WebDriverWait(driver, show_more_wait_time, ignored_exceptions=ignore_list).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "view-more-btn"))):
            button_show_more = driver.find_element(By.CLASS_NAME, "view-more-btn")
            button_show_more.click()
        else:
            print("This isn't supposed to happen. Please send a message to me about how you reached the else part of "
                  "the WebDriverWait.")
    except NoSuchElementException as excep:
        print("No more champions to show. This should only happen with extreme off meta picks. "
              "If some data isn't found, try making the wait time higher.")
        print("The exception is :", excep)
    except StaleElementReferenceException as excep:
        if retry < 5:
            print("The Show More element got stale. Retrying", retry + 1, "/5")
            return get_champion_winrate(champion, role, patch, retry + 1)
        else:
            print("Something has gone wrong. An element got stale. Here's the exception.", excep)
    except Exception as excep:
        print("An unexpected exception (type" + str(type(excep)) + ") happened. Here the message", excep, sep="\n")
    else:
        wait_until_not = WebDriverWait(driver, show_more_wait_time).until_not(
            EC.element_to_be_clickable((By.CLASS_NAME, "view-more-btn")))
        if not wait_until_not:
            print("DEBUG: Wait until not :", WebDriverWait(driver, show_more_wait_time).until_not(
                EC.element_to_be_clickable((By.CLASS_NAME, "view-more-btn"))))
            print("This isn't supposed to happen. Please send a message to me about how you reached the else part of "
                  "the wait_until_not.")

    soup = BeautifulSoup(driver.page_source, "lxml")
    try:
        counters_list = soup.find("div", class_="counters-list best-win-rate")
    except Exception:
        print(soup.prettify())
        raise

    dict_champions_winrate = {}  # format: champ_name -> [winrate, total_games]
    for a in counters_list.findAll("a"):
        champ_name = a.find("div", class_="champion-name").get_text()
        winrate = keep_only_numbers(a.find("div", class_="win-rate").get_text())
        total_games = keep_only_numbers(a.find("div", class_="total-games").get_text())
        dict_champions_winrate[champ_name] = [winrate, total_games]
    return dict_champions_winrate


def get_pool_counters(pool, role, patch=None):
    """
    Return a list containing the best counter among the pool for every champion, along with the WR and games of
    each pool champ.
    """
    dict_winrates = {champ: get_champion_winrate(champ, role, patch) for champ in pool}
    list_champions = [set(dict_winrates[key].keys()) for key in dict_winrates.keys()]
    set_champions = set()
    for new_set in list_champions:
        set_champions = set_champions | new_set  # add the new set of champions without duplicates
    all_champs = sorted(list(set_champions))  # to be sure there isn't any duplicates

    table = []  # format: champ -> best_champ, best_winrate, best_number_of_games
    for champ in all_champs:
        best_champ = "None"
        best_winrate = 0
        best_number_of_games = 0
        infos_by_champ = {}
        for pool_champ in pool:
            infos = dict_winrates[pool_champ].get(champ)
            if infos:
                winrate, number_of_games = 100 - float(infos[0]), int(infos[1])
                infos_by_champ[pool_champ] = f"{winrate:2.2f}%", f"{number_of_games:,}".replace(",", " ")
                if winrate and winrate > best_winrate:
                    best_winrate = winrate
                    best_champ = pool_champ
                    best_number_of_games = number_of_games
            else:
                infos_by_champ[pool_champ] = "0%", 0

        table.append(
            [champ, best_champ, f"{best_winrate:2.2f}%", f"{best_number_of_games:,}".replace(",", " "), infos_by_champ])
    return table


@app.route('/results/<pool>/<string:role>')
@app.route('/results/<pool>/<string:role>/<patch>')
def results(pool, role, patch=None):
    pool = pool.split(",")
    return render_template("results.html", pool_evaluation=get_pool_counters(pool, role, patch=patch), pool=pool,
                           role=role, patch=patch)


@app.route("/credits")
def page_credits():
    return render_template("credits.html")


@app.route("/")
@app.route("/home")
def home():
    with open("static/data/champs.csv", "r") as file:
        champs = file.read().split("\n")
    return render_template("home.html", champs=champs)


@app.route("/error", defaults={'exception': None})
@app.errorhandler(werkzeug.exceptions.InternalServerError)
def handle_internal_server_error(exception):
    return render_template("error.html", exception=str(exception))
