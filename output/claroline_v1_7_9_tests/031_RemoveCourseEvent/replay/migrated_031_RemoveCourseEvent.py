from selenium import webdriver
from selenium.webdriver.common.by import By
import time
from selenium.webdriver.chrome.service import Service
CHROMEDRIVER_PATH = r"D:\chromedriver\chromedriver-win64\chromedriver-win64\chromedriver.exe"
driver_options = webdriver.ChromeOptions()
driver_options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=driver_options)
driver.set_window_size(1920, 1080)
driver.get("http://claroline-new.local:8089/login")
time.sleep(1)
driver.find_element(By.ID, 'username').clear()
element = driver.find_element(By.ID, 'username')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('admin')
time.sleep(1)
driver.find_element(By.ID, "password").clear()
driver.find_element(By.ID, "password").send_keys("admin")
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, 'div > div > div > form > button').click()
time.sleep(1)
driver.get('http://claroline-new.local:8088/courses/1b2e/')
time.sleep(1)
time.sleep(float('' or 1))
time.sleep(float('10' or 1))
time.sleep(float('' or 1))
time.sleep(float('1' or 1))
time.sleep(1)
driver.execute_script('return true;')
driver.execute_script("window.confirm = function(){ return true; }; arguments[0].click();", confirm_target)
time.sleep(1)
assert "Event deleted from the agenda." == driver.find_element(By.XPATH, "//*[@id='claroBody']/table[1]/tbody/tr/td").text
time.sleep(1)
driver.quit()
time.sleep(1)
