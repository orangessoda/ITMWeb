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
driver.find_element(By.LINK_TEXT, "Create course").click()
time.sleep(1)
driver.find_element(By.ID, "title").clear()
driver.find_element(By.ID, "title").send_keys("Music")
time.sleep(1)
driver.find_element(By.ID, "officialCode").clear()
driver.find_element(By.ID, "officialCode").send_keys("3")
time.sleep(1)
Select(driver.find_element(By.ID, "category")).select_by_visible_text("(HUMA) Humanities")
time.sleep(1)
driver.find_element(By.ID, "courseEnrollAllowed_false").click()
time.sleep(1)
driver.find_element(By.NAME, "submitFromCoursProperties").click()
time.sleep(1)
assert "You have just created the course website : 3" == driver.find_element(By.XPATH, "//*[@id='claroBody']/table[1]/tbody/tr/td").text
time.sleep(1)
driver.find_element(By.LINK_TEXT, "Back to my course list").click()
time.sleep(1)
driver.quit()
time.sleep(1)
