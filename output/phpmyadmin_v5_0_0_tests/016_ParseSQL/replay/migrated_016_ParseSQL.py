from selenium import webdriver
from selenium.webdriver.common.by import By
import time
from selenium.webdriver.chrome.service import Service
CHROMEDRIVER_PATH = r"D:\chromedriver\chromedriver-win64\chromedriver-win64\chromedriver.exe"
driver_options = webdriver.ChromeOptions()
driver_options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=driver_options)
driver.set_window_size(1920, 1080)
js = driver
driver.execute_script("document.body.style.zoom='80%'")
driver.get("http://phpmyadmin-new.local:8093/")
time.sleep(1)
driver.find_element(By.ID, "input_username").clear()
driver.find_element(By.ID, "input_username").send_keys("admin")
time.sleep(1)
driver.find_element(By.ID, "input_password").clear()
driver.find_element(By.ID, "input_password").send_keys("admin")
time.sleep(1)
driver.find_element(By.ID, "input_go").click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "test").click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "testtable").click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "解析 SQL").click()
time.sleep(1)
assert driver.find_element(By.CSS_SELECTOR, ".data:nth-child(1) > span").text == "1"
time.sleep(1)
assert driver.find_element(By.CSS_SELECTOR, ".data:nth-child(2) > span").text == "SIMPLE"
time.sleep(1)
assert driver.find_element(By.CSS_SELECTOR, ".data:nth-child(3) > span").text == "testtable"
time.sleep(1)
driver.find_element(By.ID, 'pma_navigation_settings_icon').click()
time.sleep(1)
driver.quit()
time.sleep(1)
