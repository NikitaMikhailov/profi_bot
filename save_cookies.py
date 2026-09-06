import time
import yaml
import pickle
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from config_logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

auth = config.get("auth", {})
chrome = config.get("chrome", {})

LOGIN = auth.get("login")
PASSWORD = auth.get("password")
COOKIE_FILE = chrome.get("cookies_file", "session")
HEADLESS = chrome.get("headless", True)

options = Options()

if HEADLESS:
    options.add_argument("--headless=new")
    logger.info("Headless mode enabled")
else:
    logger.info("Headless mode disabled")

options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

try:
    driver.get("https://profi.ru/backoffice/n.php")
    time.sleep(3)

    # Enter the login
    login_field = driver.find_element(By.CLASS_NAME, "ui-input")
    login_field.send_keys(LOGIN)
    # Enter the password
    password_field = driver.find_elements(By.CLASS_NAME, "ui-input")[1]
    password_field.send_keys(PASSWORD)

    # Click the login button
    driver.find_element(By.CLASS_NAME, "ui-button").click()
    time.sleep(10)

    # Save the cookies
    pickle.dump(driver.get_cookies(), open(COOKIE_FILE, "wb"))
    logger.info("✅ Session saved to %s", COOKIE_FILE)
except Exception as e:
    logger.exception("❌ Error during headless login: %s", e)
finally:
    driver.quit()
