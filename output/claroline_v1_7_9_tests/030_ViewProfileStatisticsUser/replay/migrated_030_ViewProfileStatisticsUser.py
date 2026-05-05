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
driver.find_element(By.CSS_SELECTOR, 'div > div > ul > li > a').click()
driver.find_element(By.CSS_SELECTOR, 'div > div > ul > li > a').click()
driver.find_element(By.CSS_SELECTOR, '.dropdown-toggle').click()
driver.find_element(By.CSS_SELECTOR, 'div > div > ul > li > a').click()
driver.find_element(By.ID, 'username').clear()
element = driver.find_element(By.ID, 'username')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('UserU')
driver.find_element(By.ID, 'password').clear()
element = driver.find_element(By.ID, 'password')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('passwordU')
driver.find_element(By.CSS_SELECTOR, 'div > div > div > form > button').click()
driver.find_element(By.CSS_SELECTOR, 'div > div > ul > li > a').click()
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
driver.get('http://claroline-old.local:8088/claroline/auth/profile.php')
time.sleep(1)
driver.find_element(By.XPATH, "//*[@id='claroBody']/p/a").click()
time.sleep(1)
driver.find_element(By.XPATH, "//*[@id='claroBody']/ul/li/a").click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "Show all").click()
time.sleep(1)
assert "Exercise 1" == driver.find_element(By.XPATH, "//*[@id='claroBody']/table[2]/tbody[2]/tr/td[1]/a").text
time.sleep(1)
assert "9" == driver.find_element(By.XPATH, "//*[@id='claroBody']/table[2]/tbody[2]/tr/td[3]").text
time.sleep(1)
driver.quit()
time.sleep(1)
