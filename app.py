import time

from flask import Flask, render_template, request
from bs4 import BeautifulSoup


from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, \
    ElementNotVisibleException, ElementNotSelectableException, ElementClickInterceptedException
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
        if browser['name'] == 'Edge':
            driver.maximize_window()  # Edge has a lot of trouble clicking on stuff, for some reason. This might help.
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


def get_champion_winrate(champion, role, patch="latest", retry=0):
    """Returns a dict contening for each enemy champion, the winrate against it and the number of match.

    patch should be written as "13_9" or "13_10". ("13.9" or "13_09" won't work.)
    retry is the number of time we retried due to a stale element.

    return dict = format: champ_name -> [winrate, total_games]
    """
    global cookies_enabled
    champion = champion.lower()
    role = role.lower()
    try:
        assert role in ["top", "jungle", "middle", "adc", "support"]
    except AssertionError:
        print(role)
        raise

    url = f"https://u.gg/lol/champions/{champion}/matchups?role={role}"
    if patch != "latest":  # 13_10, not 13.10
        url += f"&patch={patch}"
    print("URL visited:", url)
    driver.get(url)

    input()

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

    soup = BeautifulSoup(driver.page_source, "lxml")
    try:
        counters_list = soup.find("div", class_="matchups-table").find("div", class_="rt-tbody")
    except Exception:
        print(soup.prettify())
        raise

    dict_champions_winrate = {}  # format: champ_name -> [winrate, total_games]
    for div in counters_list.findAll("div", class_="rt-tr-group"):
        row = div.find("div", class_="rt-tr")
        champ_name = row.find("div", class_="champion").find("a").find("div", class_="champion-name").get_text()
        winrate = keep_only_numbers(row.find("div", class_="win_rate").find("div").get_text())
        total_games = row.find("div", class_="matches").find("span").get_text()
        dict_champions_winrate[champ_name] = [winrate, total_games]
    return dict_champions_winrate


def get_pool_counters(pool, role, patch=None, delta=False):
    """
    Return a list containing the best counter among the pool for every champion, along with the WR and games of
    each pool champ.
    """
    dict_winrates = {champ: get_champion_winrate(champ, role, patch) for champ in pool}

    if delta:
        dict_total_winrates = {}
        pool_totals = []
        for pool_champ in pool:
            numerator_weighted_average = 0  # It should become the sum of winrate% * number_of_games
            denominator_weighted_average = 0  # It should become the total number of games on the champ.
            for winrate, number_of_games in dict_winrates[pool_champ].values():
                winrate = float(winrate) / 100
                number_of_games = int(number_of_games.replace(",", ""))
                numerator_weighted_average += winrate * number_of_games
                denominator_weighted_average += number_of_games
            average_winrate = numerator_weighted_average / denominator_weighted_average * 100
            dict_total_winrates[pool_champ] = average_winrate
            pool_totals.append([pool_champ, f"{average_winrate:2.2f}%",
                                f"{denominator_weighted_average:,}".replace(",", " ")])

    list_champions = [set(dict_winrates[counter_champ].keys()) for counter_champ in dict_winrates.keys()]
    set_champions = set()
    for new_set in list_champions:
        set_champions = set_champions | new_set  # add the new set of champions without duplicates
    all_champs = sorted(list(set_champions))  # to be sure there isn't any duplicates

    if delta:
        table = []  # format: counter_champ, best_champ, best_delta, best_number_of_games
        for counter_champ in all_champs:
            best_champ = "None"
            best_delta = -100
            best_number_of_games = 0
            infos_by_champ = {}
            for pool_champ in pool:
                infos = dict_winrates[pool_champ].get(counter_champ)
                if infos:
                    winrate, number_of_games = float(infos[0]), int(infos[1].replace(",", ""))
                    delta = winrate - dict_total_winrates[pool_champ]
                    infos_by_champ[pool_champ] = f"{delta:+2.2f}%", f"{number_of_games:,}".replace(",", " ")
                    if delta and delta > best_delta:
                        best_delta = delta
                        best_champ = pool_champ
                        best_number_of_games = number_of_games
                else:
                    infos_by_champ[pool_champ] = "-99.99%", 0
            table.append([counter_champ, best_champ, f"{best_delta:+2.2f}%",
                          f"{best_number_of_games:,}".replace(",", " "), infos_by_champ])

        return table, pool_totals

    else:
        table = []  # format: counter_champ, best_champ, best_winrate, best_number_of_games
        for counter_champ in all_champs:
            best_champ = "None"
            best_winrate = 0
            best_number_of_games = 0
            infos_by_champ = {}
            for pool_champ in pool:
                infos = dict_winrates[pool_champ].get(counter_champ)
                if infos:
                    winrate, number_of_games = float(infos[0]), int(infos[1].replace(",", ""))
                    infos_by_champ[pool_champ] = f"{winrate:2.2f}%", f"{number_of_games:,}".replace(",", " ")
                    if winrate and winrate > best_winrate:
                        best_winrate = winrate
                        best_champ = pool_champ
                        best_number_of_games = number_of_games
                else:
                    infos_by_champ[pool_champ] = "0%", 0

            table.append([counter_champ, best_champ, f"{best_winrate:2.2f}%",
                          f"{best_number_of_games:,}".replace(",", " "), infos_by_champ])
        return table, None


@app.route("/results", methods=['GET'])
def results():
    pool = [champ.replace("'", "").replace(" ", "").replace(".", "") for champ in request.args.getlist('pool[]')]
    role = request.args.get("role")
    patch = request.args.get("patch")
    delta = request.args.get("delta") == "on"
    pool_evaluation, pool_totals = get_pool_counters(pool, role, patch=patch, delta=delta)
    return render_template("results.html", pool_evaluation=pool_evaluation, pool=pool, role=role, patch=patch,
                           delta=delta, pool_totals=pool_totals)


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
