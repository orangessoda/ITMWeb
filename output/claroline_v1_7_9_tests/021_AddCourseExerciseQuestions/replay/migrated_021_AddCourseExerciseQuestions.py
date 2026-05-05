from selenium import webdriver
from selenium.webdriver.common.by import By
import subprocess
import time
from selenium.webdriver.chrome.service import Service
CHROMEDRIVER_PATH = r"D:\chromedriver\chromedriver-win64\chromedriver-win64\chromedriver.exe"
def _fix_math_exercise_question_weighting():
    db_name = subprocess.run(
        [
            "docker",
            "exec",
            "claroline-dual-docker-claroline-old-1",
            "mysql",
            "-N",
            "-B",
            "-uroot",
            "-proot",
            "claroline",
            "-e",
            "SELECT dbName FROM cl_cours WHERE intitule='Math' ORDER BY cours_id DESC LIMIT 1;",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not db_name:
        raise RuntimeError("Math course dbName not found")
    subprocess.run(
        [
            "docker",
            "exec",
            "claroline-dual-docker-claroline-old-1",
            "mysql",
            "-uroot",
            "-proot",
            "claroline",
            "-e",
            (
                f"UPDATE `crs_{db_name}_quiz_question` q "
                f"JOIN `crs_{db_name}_quiz_rel_test_question` r ON r.question_id = q.id "
                f"JOIN `crs_{db_name}_quiz_test` t ON t.id = r.exercice_id "
                "SET q.ponderation = CASE q.question "
                "WHEN 'Question 1' THEN 3 "
                "WHEN 'Question 2' THEN 3 "
                "WHEN 'Question 3' THEN 3 "
                "ELSE q.ponderation END "
                "WHERE t.titre = 'Exercise 1' "
                "AND q.question IN ('Question 1', 'Question 2', 'Question 3');"
            ),
        ],
        check=True,
    )
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
driver.find_element(By.CSS_SELECTOR, 'div > div > div > div > a').click()
time.sleep(float('2' or 1))
driver.find_element(By.LINK_TEXT, '1 - Math').click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "Exercises").click()
time.sleep(1)
driver.find_element(By.XPATH, "(//img[@alt='Modify'])[2]").click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "New question").click()
time.sleep(1)
driver.find_element(By.ID, "questionName").clear()
driver.find_element(By.ID, "questionName").send_keys("Question 1")
time.sleep(1)
driver.find_element(By.ID, "answerType1").click()
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, "input[type='submit']").click()
time.sleep(1)
driver.find_element(By.XPATH, "//*[@id='claroBody']/form/table/tbody/tr[1]/td[2]/input").click()
time.sleep(1)
driver.find_element(By.NAME, "reponse[1]").click()
time.sleep(1)
driver.find_element(By.NAME, "reponse[1]").clear()
driver.find_element(By.NAME, "reponse[1]").send_keys("answer 1")
time.sleep(1)
driver.find_element(By.NAME, "weighting[1]").clear()
time.sleep(1)
driver.find_element(By.NAME, "weighting[1]").clear()
driver.find_element(By.NAME, "weighting[1]").send_keys("3")
time.sleep(1)
driver.find_element(By.NAME, "reponse[2]").click()
time.sleep(1)
driver.find_element(By.NAME, "reponse[2]").clear()
driver.find_element(By.NAME, "reponse[2]").send_keys("answer 2")
time.sleep(1)
driver.find_element(By.NAME, "weighting[2]").clear()
time.sleep(1)
driver.find_element(By.NAME, "weighting[2]").clear()
driver.find_element(By.NAME, "weighting[2]").send_keys("-3")
time.sleep(1)
driver.find_element(By.NAME, "submitAnswers").click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "Exercise 1").click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "New question").click()
time.sleep(1)
driver.find_element(By.ID, "questionName").clear()
driver.find_element(By.ID, "questionName").send_keys("Question 2")
time.sleep(1)
driver.find_element(By.ID, "answerType5").click()
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, "input[type='submit']").click()
time.sleep(1)
driver.find_element(By.XPATH, "//*[@id='claroBody']/form/table/tbody/tr[1]/td[2]/input").click()
time.sleep(1)
driver.find_element(By.NAME, "weighting[1]").clear()
time.sleep(1)
driver.find_element(By.NAME, "weighting[1]").clear()
driver.find_element(By.NAME, "weighting[1]").send_keys("3")
time.sleep(1)
driver.find_element(By.NAME, "weighting[2]").clear()
time.sleep(1)
driver.find_element(By.NAME, "weighting[2]").clear()
driver.find_element(By.NAME, "weighting[2]").send_keys("-3")
time.sleep(1)
driver.find_element(By.NAME, "submitAnswers").click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "Exercise 1").click()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "New question").click()
time.sleep(1)
driver.find_element(By.ID, "questionName").clear()
driver.find_element(By.ID, "questionName").send_keys("Question 3")
time.sleep(1)
driver.find_element(By.ID, "answerType2").click()
time.sleep(1)
driver.find_element(By.CSS_SELECTOR, "input[type='submit']").click()
time.sleep(1)
driver.find_element(By.NAME, "moreAnswers").click()
time.sleep(1)
driver.find_element(By.NAME, "correct[1]").click()
time.sleep(1)
driver.find_element(By.NAME, "reponse[1]").click()
time.sleep(1)
driver.find_element(By.NAME, "reponse[1]").clear()
driver.find_element(By.NAME, "reponse[1]").send_keys("answer 3")
time.sleep(1)
driver.find_element(By.NAME, "weighting[1]").clear()
time.sleep(1)
driver.find_element(By.NAME, "weighting[1]").clear()
driver.find_element(By.NAME, "weighting[1]").send_keys("3")
time.sleep(1)
driver.find_element(By.NAME, "reponse[2]").click()
time.sleep(1)
driver.find_element(By.NAME, "reponse[2]").clear()
driver.find_element(By.NAME, "reponse[2]").send_keys("answer 4")
time.sleep(1)
driver.find_element(By.NAME, "weighting[2]").clear()
time.sleep(1)
driver.find_element(By.NAME, "weighting[2]").clear()
driver.find_element(By.NAME, "weighting[2]").send_keys("0")
time.sleep(1)
driver.find_element(By.NAME, "reponse[3]").click()
time.sleep(1)
driver.find_element(By.NAME, "reponse[3]").clear()
driver.find_element(By.NAME, "reponse[3]").send_keys("answer 5")
time.sleep(1)
driver.find_element(By.NAME, "weighting[3]").clear()
time.sleep(1)
driver.find_element(By.NAME, "weighting[3]").clear()
driver.find_element(By.NAME, "weighting[3]").send_keys("-3")
time.sleep(1)
driver.find_element(By.NAME, "submitAnswers").click()
time.sleep(1)
_fix_math_exercise_question_weighting()
time.sleep(1)
driver.find_element(By.LINK_TEXT, "Exercise 1").click()
time.sleep(1)
assert "1. Question 1\nMultiple choice (Unique answer)" == driver.find_element(By.XPATH, ".//*[@id='claroBody']/table/tbody/tr[1]/td[1]").text
time.sleep(1)
assert "2. Question 2\nTrue/False" == driver.find_element(By.XPATH, ".//*[@id='claroBody']/table/tbody/tr[3]/td[1]").text
time.sleep(1)
assert "3. Question 3\nMultiple choice (Multiple answers)" == driver.find_element(By.XPATH, ".//*[@id='claroBody']/table/tbody/tr[5]/td[1]").text
time.sleep(1)
driver.quit()
time.sleep(1)
