from selenium import webdriver
from selenium.webdriver.common.by import By
import time
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
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
driver.find_element(By.LINK_TEXT, 'John Doe').click()
driver.find_element(By.LINK_TEXT, 'Administration').click()
driver.find_element(By.LINK_TEXT, "Gestion des espaces d'activités").click()
element = driver.find_element(By.ID, 'search-items-txt')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('Math')
driver.find_element(By.ID, 'search-button').click()
driver.get('http://claroline-old.local:8088/claroline/exercice/admin.php?modifyExercise=yes')
time.sleep(1)
time.sleep(float('' or 1))
driver.find_element(By.ID, 'username').clear()
element = driver.find_element(By.ID, 'username')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('admin')
driver.find_element(By.ID, 'password').clear()
element = driver.find_element(By.ID, 'password')
element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None
element.send_keys('admin')
driver.find_element(By.XPATH, "//input[@type='submit' and @value='Ok']").click()
driver.get('http://claroline-old.local:8088/courses/1b2e/')
time.sleep(float('10' or 1))
driver.find_element(By.LINK_TEXT, 'Exercises').click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "New exercise").click()
time.sleep(1)
driver.find_element(By.ID, "exerciseTitle").clear()
driver.find_element(By.ID, "exerciseTitle").send_keys("Exercise 1")
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, "input[type='submit']").click()
time.sleep(1)
assert "There is no question for the moment" == driver.find_element(By.XPATH, "//*[@id='claroBody']/table[1]/tbody/tr/td").text
time.sleep(1)
driver.quit()
time.sleep(1)
