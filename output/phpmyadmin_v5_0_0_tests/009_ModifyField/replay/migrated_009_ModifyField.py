from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
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
driver.find_element(By.LINK_TEXT, "结构").click()
time.sleep(1)
driver.find_element(By.ID, 'pma_navigation_settings_icon').click()
time.sleep(1)
Select(driver.find_element(By.ID, "field_0_4")).select_by_visible_text("无")
time.sleep(1)
driver.find_element(By.NAME, "do_save_data").click()
time.sleep(1)
assert driver.find_element(By.CSS_SELECTOR, "tr:nth-child(2) em").text == "无"
time.sleep(1)
driver.quit()
time.sleep(1)
