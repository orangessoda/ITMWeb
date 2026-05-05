from selenium import webdriver
from selenium.webdriver.common.by import By
import subprocess
import time
from pathlib import Path
from selenium.webdriver.chrome.service import Service
CHROMEDRIVER_PATH = r"D:\chromedriver\chromedriver-win64\chromedriver-win64\chromedriver.exe"
subprocess.run(
    [
        "python",
        str(Path('C:/Users/DELL/Downloads/Graduation_project/ITMWeb/dockers') / "phpmyadmin-dual-docker" / "reset_phpmyadmin_non_user_data.py"),
        "--target",
        "new",
        "--execute",
    ],
    check=True,
)
print("[phpmyadmin-new] database reset succeeded")
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
driver.find_element(By.ID, 'pma_navigation_settings_icon').click()
time.sleep(1)
driver.quit()
time.sleep(1)

