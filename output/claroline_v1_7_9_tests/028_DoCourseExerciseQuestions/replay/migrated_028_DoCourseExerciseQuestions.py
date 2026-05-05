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
driver.find_element(By.ID, "password").send_keys("passwordU")
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, 'div > div > div > form > button').click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, 'Connexion').click()
element = driver.find_element(By.ID, 'username')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('UserU')
element = driver.find_element(By.ID, 'password')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('passwordU')
driver.find_element(By.LINK_TEXT, 'Connexion').click()
element = driver.find_element(By.ID, 'username')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('UserU')
element = driver.find_element(By.ID, 'password')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('passwordU')
driver.find_element(By.CSS_SELECTOR, 'div > div > div > form > button').click()
time.sleep(float('2' or 1))
element = driver.find_element(By.ID, 'username')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('UserU')
element = driver.find_element(By.ID, 'password')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('passwordU')
driver.find_element(By.CSS_SELECTOR, 'div > div > div > form > button').click()
element = driver.find_element(By.ID, 'username')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('UserU')
element = driver.find_element(By.ID, 'password')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('passwordU')
driver.find_element(By.LINK_TEXT, 'Connexion').click()
driver.find_element(By.ID, 'username').clear()
element = driver.find_element(By.ID, 'username')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('UserU')
driver.find_element(By.ID, 'password').clear()
element = driver.find_element(By.ID, 'password')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('passwordU')
driver.find_element(By.CSS_SELECTOR, 'div > div > div > form > button').click()
driver.get('http://claroline-old.local:8088/courses/1b2e/')
time.sleep(1)
time.sleep(float('10' or 1))
time.sleep(float('10' or 1))
time.sleep(float('10' or 1))
driver.find_element(By.LINK_TEXT, 'Exercises').click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "Exercise 1").click()
time.sleep(1)
driver.find_element(By.XPATH, "/html/body/div[3]/table/tbody/tr[1]/td/table[1]/tfoot/tr[3]/td[1]/input").click()
time.sleep(1)
driver.find_element(By.XPATH, "/html/body/div[3]/table/tbody/tr[1]/td/table[3]/tfoot/tr[3]/td[1]/input").click()
time.sleep(1)
driver.find_element(By.XPATH, "/html/body/div[3]/table/tbody/tr[1]/td/table[2]/tfoot/tr[3]/td[1]/input").click()
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, "input[type=submit]").click()
time.sleep(1)
assert "Your total score is 9/9" == driver.find_element(By.XPATH, "/html/body/div[3]/form/table[4]/tbody/tr[2]").text
time.sleep(1)
driver.quit()
time.sleep(1)
