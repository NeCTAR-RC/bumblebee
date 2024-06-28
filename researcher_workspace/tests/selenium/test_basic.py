from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import tag
from selenium.webdriver.common.by import By
from selenium.webdriver import Firefox
from selenium.webdriver.firefox.service import Service
from webdriver_manager.firefox import GeckoDriverManager


@tag('selenium')
class BasicWorkspaceTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.driver = Firefox(
            service=Service(GeckoDriverManager().install()))
        cls.driver.implicitly_wait(10)

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()
        super().tearDownClass()

    def test_home(self):
        self.driver.get(f"{self.live_server_url}/")
        self.assertEqual(
            "Virtual Desktop Service - ARDC Nectar Research Cloud",
            self.driver.title)
        about = self.driver.find_element(By.XPATH, '//*[text()="About"]')
        self.assertTrue(about)
        self.assertEqual(f"{self.live_server_url}/about/",
                         about.get_attribute("href"))
        self.driver.get(f"{self.live_server_url}/about/")
