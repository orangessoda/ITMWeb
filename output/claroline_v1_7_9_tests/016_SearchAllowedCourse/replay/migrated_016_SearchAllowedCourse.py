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
driver.find_element(By.LINK_TEXT, "Platform Administration").click()
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, "form[name='searchCourse'] > small > a").click()
time.sleep(1)
driver.find_element(By.ID, "intitule").clear()
driver.find_element(By.ID, "intitule").send_keys("Math")
time.sleep(1)
driver.find_element(By.ID, "subscription_allowed").click()
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, "input.claroButton").click()
time.sleep(1)
assert "Math" == driver.find_element(By.XPATH, "//*[@id='claroBody']/table[3]/tbody/tr/td[2]").text
time.sleep(1)
driver.quit()
time.sleep(1)
