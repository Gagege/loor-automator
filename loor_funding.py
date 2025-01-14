import os
import yaml
from dotenv import load_dotenv
import logging
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Set up basic logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Load environment variables from .secrets file
load_dotenv(".secrets")


class LoorAPI:
    def __init__(self, username, password, debug=False):
        self.username = username
        self.password = password
        self.base_url = "https://www.loor.tv"
        self.logger = logging.getLogger(__name__)
        self.config = self.load_config()
        self.debug = debug
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=not debug)
        self.context = None
        self.page = None

    def __del__(self):
        if self.page:
            self.page = None
        if self.context:
            self.context.close()
            self.context = None
        if self.browser:
            self.browser.close()
            self.browser = None
        if hasattr(self, "playwright") and self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.playwright = None

    @staticmethod
    def load_config():
        try:
            with open("config.yml", "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logging.error(f"Failed to load config: {str(e)}")
            raise

    def take_debug_screenshot(self, name):
        """Take a screenshot if debug mode is enabled"""
        if self.debug:
            # Create debug/screenshots directory if it doesn't exist
            screenshot_dir = os.path.join("debug", "screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)

            # Save screenshot in the debug/screenshots directory
            screenshot_path = os.path.join(screenshot_dir, f"{name}.png")
            self.page.screenshot(path=screenshot_path)

    def login(self):
        try:
            # Create a new context and page if not exists
            if not self.context:
                self.context = self.browser.new_context()
                self.page = self.context.new_page()

            # Navigate to login page and authenticate
            self.page.goto(f"{self.base_url}/login")
            self.page.fill('input[name="user[email]"]', self.username)
            self.page.fill('input[name="user[password]"]', self.password)

            self.take_debug_screenshot("before_login")
            self.page.click('button[type="submit"]')

            try:
                # Wait for page load after login
                self.page.wait_for_load_state("networkidle", timeout=10000)
                self.take_debug_screenshot("after_login")

                # Try to find any element that indicates we're logged in
                logged_in = self.page.wait_for_selector(
                    '.user-menu, .profile-menu, nav a[href*="user"]', timeout=10000
                )
                if logged_in:
                    logging.info("Successfully logged in to Loor.tv")
                    if self.debug:
                        logged_in_path = os.path.join(
                            "debug", "screenshots", "logged_in_element.png"
                        )
                        logged_in.screenshot(path=logged_in_path)
                else:
                    raise ValueError("Could not find logged-in user elements")

            except PlaywrightTimeoutError:
                self.take_debug_screenshot("login_failed")
                raise ValueError("Login failed - could not verify successful login")

        except Exception as e:
            logging.error(f"Login failed: {str(e)}")
            raise

    def get_show_id(self, show_name):
        try:
            show_slug = show_name.lower().replace(" ", "-")
            self.page.goto(f"{self.base_url}/project/{show_slug}")

            try:
                # Wait for funding button to verify show exists
                self.page.wait_for_selector(
                    'button[phx-click="fund_project"]', timeout=5000
                )
                return show_slug
            except PlaywrightTimeoutError:
                raise ValueError(
                    f'Show "{show_name}" not found or not available for funding'
                )

        except Exception as e:
            logging.error(f"Failed to get show ID: {str(e)}")
            raise

    def fund_show(self, show_name, amount):
        try:
            show_id = self.get_show_id(show_name)
            if not show_id:
                raise ValueError(f"Could not find show ID for {show_name}")

            try:
                # Wait for and click the fund button
                fund_button = self.page.wait_for_selector(
                    'button[phx-click="fund_project"]', timeout=5000
                )
                fund_button.click()

                # Wait for funding modal/form to appear and fill amount
                amount_input = self.page.wait_for_selector(
                    'input[type="number"]', timeout=5000
                )
                amount_input.fill(str(amount))

                # Click the confirm/submit button in the funding modal
                submit_button = self.page.wait_for_selector(
                    'button[type="submit"]', timeout=5000
                )
                submit_button.click()

                # Wait for success message or confirmation
                success = self.page.wait_for_selector('div[role="alert"]', timeout=5000)
                if success and "success" in success.text_content().lower():
                    logging.info(f"Successfully funded {show_name} with {amount} LOOT")
                    return True

            except PlaywrightTimeoutError as e:
                raise ValueError(f"Failed to complete funding process: {str(e)}")

            return False

        except Exception as e:
            logging.error(f"Funding failed for {show_name}: {str(e)}")
            raise

    def fund_all_shows(self):
        """Fund all media specified in the config file."""
        try:
            self.login()  # Ensure we're logged in before starting
            for item in self.config["media"]:
                try:
                    self.fund_show(item["name"], item["amount"])
                    logging.info(
                        f"Successfully processed {item['type']}: {item['name']}"
                    )
                except Exception as e:
                    logging.error(
                        f"Failed to fund {item['type']} '{item['name']}': {str(e)}"
                    )
                    continue
        finally:
            # Cleanup browser resources
            if self.context:
                self.context.close()
                self.context = None
            if self.page:
                self.page = None

    def claim_loot(self):
        try:
            if not self.context or not self.page:
                self.login()  # Ensure we're logged in

            # Navigate to quests page
            self.page.goto(f"{self.base_url}/user/quests")

            try:
                # Look for the claim form
                form = self.page.wait_for_selector("form", timeout=5000)
                if not form:
                    logging.info(
                        "No claim form found - might have already claimed today"
                    )
                    return True

                # Click the claim button/submit form
                submit_button = self.page.wait_for_selector(
                    'button[type="submit"]', timeout=5000
                )
                submit_button.click()

                # Wait for success message
                success = self.page.wait_for_selector('div[role="alert"]', timeout=5000)
                if success and "success" in success.text_content().lower():
                    logging.info("Successfully claimed LOOT")
                    return True

            except PlaywrightTimeoutError:
                logging.info("No claim form found - might have already claimed today")
                return True

        except Exception as e:
            logging.error(f"Failed to claim LOOT: {str(e)}")
            raise


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Loor.tv Funding Automator")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (visible browser and screenshots)",
    )
    args = parser.parse_args()

    loor = LoorAPI(
        os.getenv("LOOR_EMAIL"), os.getenv("LOOR_PASSWORD"), debug=args.debug
    )

    try:
        loor.login()
        # loor.fund_all_shows()  # Commented out for testing login only
        logging.info("Login test completed")
    except Exception as e:
        logging.error(f"Failed to login: {str(e)}")
    finally:
        # Ensure cleanup
        if loor.context:
            loor.context.close()
        if loor.browser:
            loor.browser.close()
        if loor.playwright:
            loor.playwright.stop()


if __name__ == "__main__":
    main()
