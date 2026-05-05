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
driver.execute_script("window.location.href = '/workspaces/1b2e'")
time.sleep(1)
time.sleep(float('' or 1))
driver.find_element(By.XPATH, "//a[text()='Agenda']").click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "Add an event").click()
time.sleep(1)
driver.find_element(By.ID, "title").clear()
driver.find_element(By.ID, "title").send_keys("Exam 1")
time.sleep(1)
Select(driver.find_element(By.ID, "fday")).select_by_visible_text("31")
time.sleep(1)
Select(driver.find_element(By.ID, "fmonth")).select_by_visible_text("May")
time.sleep(1)
Select(driver.find_element(By.ID, "fyear")).select_by_visible_text("2021")
time.sleep(1)
driver.find_element(By.NAME, "submitEvent").click()
time.sleep(1)
assert "Event added to the agenda." == driver.find_element(By.XPATH, "//*[@id='claroBody']/table[1]/tbody/tr/td").text
time.sleep(1)
driver.quit()
time.sleep(1)
