from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
from selenium.webdriver.chrome.service import Service
CHROMEDRIVER_PATH = r"D:\chromedriver\chromedriver-win64\chromedriver-win64\chromedriver.exe"
driver_options = webdriver.ChromeOptions()
driver_options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=driver_options)
driver.set_window_size(1920, 1080)
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
driver.find_element(By.LINK_TEXT, "账户").click()
time.sleep(1)
driver.find_element(By.ID, 'pma_navigation_settings_icon').click()
time.sleep(1)
driver.find_element(By.ID, "checkall_数据_priv").click()
time.sleep(1)
driver.find_element(By.ID, "checkbox_Select_priv").click()
time.sleep(1)
driver.find_element(By.TAG_NAME, "html").send_keys(Keys.END)
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, "#fieldset_user_privtable_footer > .btn").click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "账户").click()
time.sleep(1)
assert driver.find_element(By.CSS_SELECTOR, "tr:nth-child(3) > td:nth-child(5)").text == "SELECT, SHOW VIEW"
time.sleep(1)
driver.quit()
time.sleep(1)
