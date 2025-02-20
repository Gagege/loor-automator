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
    def __init__(self, username, password, debug=False, dryrun=False):
        self.username = username
        self.password = password
        self.base_url = "https://www.loor.tv"
        self.logger = logging.getLogger(__name__)
        self.config = self.load_config()
        self.debug = debug
        self.dryrun = dryrun
        self._initialize_browser()

    def _initialize_browser(self):
        """Initialize browser resources"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=not self.debug)
        self.context = None
        self.page = None

    def cleanup(self):
        """Clean up browser resources in the correct order"""
        try:
            if hasattr(self, "page") and self.page:
                self.page = None

            if hasattr(self, "context") and self.context:
                try:
                    self.context.close()
                except Exception:
                    pass
                self.context = None

            if hasattr(self, "browser") and self.browser:
                try:
                    self.browser.close()
                except Exception:
                    pass
                self.browser = None

            if hasattr(self, "playwright") and self.playwright:
                try:
                    self.playwright.stop()
                except Exception:
                    pass
                self.playwright = None

        except Exception as e:
            logging.error(f"Error during cleanup: {str(e)}")

    def __del__(self):
        """Ensure resources are cleaned up"""
        self.cleanup()

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
            # Convert show name to URL slug format
            show_slug = show_name.lower().replace(" ", "-")
            project_url = f"{self.base_url}/project/{show_slug}"

            if self.debug:
                logging.info(f"Navigating to show URL: {project_url}")

            # Navigate to the project page
            response = self.page.goto(project_url)
            self.page.wait_for_load_state("networkidle", timeout=10000)

            if self.debug:
                self.take_debug_screenshot(f"show_page_{show_slug}")

            try:
                # Look for funding buttons (100, 400, 800)
                funding_buttons = self.page.query_selector_all(
                    'button:has-text("100"), button:has-text("400"), button:has-text("800")'
                )

                if not funding_buttons:
                    if self.debug:
                        logging.error(f"No funding buttons found for {show_name}")
                        self.take_debug_screenshot(f"no_funding_buttons_{show_slug}")
                    raise ValueError(
                        f'Show "{show_name}" not found or not available for funding'
                    )

                if self.debug:
                    logging.info(
                        f"Found {len(funding_buttons)} funding buttons for {show_name}"
                    )

                return show_slug

            except PlaywrightTimeoutError:
                if self.debug:
                    logging.error(f"Timeout waiting for funding buttons on {show_name}")
                raise ValueError(
                    f'Show "{show_name}" not found or not available for funding'
                )

        except Exception as e:
            logging.error(f"Failed to get show ID: {str(e)}")
            raise

    def fund_show(self, show_name, amounts):
        """Fund a show with specific amounts (100, 400, or 800)"""
        try:
            show_id = self.get_show_id(show_name)
            if not show_id:
                raise ValueError(f"Could not find show ID for {show_name}")

            # Validate amounts are in the allowed values
            valid_amounts = [100, 400, 800]
            invalid_amounts = [amt for amt in amounts if amt not in valid_amounts]
            if invalid_amounts:
                raise ValueError(
                    f"Invalid funding amounts {invalid_amounts}. Must be one or more of: {valid_amounts}"
                )

            success_count = 0
            for amount in amounts:
                try:
                    # Reload the show page for each funding attempt
                    project_url = f"{self.base_url}/project/{show_id}"
                    if self.debug:
                        logging.info(f"Loading show page: {project_url}")
                    self.page.goto(project_url)
                    self.page.wait_for_load_state("networkidle", timeout=10000)

                    # Take screenshot of show page if in debug mode
                    self.take_debug_screenshot(f"show_page_{show_name}_{amount}")

                    # Wait for and verify the funding button exists - look for button with both SVG and amount
                    button_selector = (
                        f'button:has(svg.fa-loor-money):has-text("{amount}")'
                    )
                    if self.debug:
                        logging.info(
                            f"Looking for funding button with selector: {button_selector}"
                        )

                    amount_button = self.page.wait_for_selector(
                        button_selector, timeout=5000
                    )
                    if not amount_button:
                        raise ValueError(
                            f"Could not find funding button for amount {amount}"
                        )

                    if self.dryrun:
                        logging.info(
                            f"DRYRUN: Would fund {show_name} with {amount} LOOT"
                        )
                        success_count += 1
                        continue

                    # Click the funding button and wait for confirmation dialog
                    logging.info(f"Clicking {amount} LOOT button for {show_name}")
                    amount_button.click()
                    self.page.wait_for_load_state("networkidle", timeout=5000)

                    # Take screenshot after initial button click
                    self.take_debug_screenshot(f"after_button_{show_name}_{amount}")

                    # Look for and click the confirm button
                    confirm_selectors = [
                        'button:has-text("Confirm")',
                        'button:has-text("Yes")',
                        'button[type="submit"]',
                        'button:has-text("Fund")',
                    ]

                    confirm_button = None
                    for selector in confirm_selectors:
                        try:
                            button = self.page.wait_for_selector(selector, timeout=2000)
                            if button and button.is_visible():
                                confirm_button = button
                                if self.debug:
                                    logging.info(
                                        f"Found confirm button with selector: {selector}"
                                    )
                                break
                        except PlaywrightTimeoutError:
                            continue

                    if not confirm_button:
                        raise ValueError("Could not find confirmation button")

                    # Take screenshot before confirming
                    self.take_debug_screenshot(f"before_confirm_{show_name}_{amount}")

                    # Click confirm and wait for completion
                    logging.info("Clicking confirm button")
                    confirm_button.click()
                    self.page.wait_for_load_state("networkidle", timeout=5000)

                    # Take screenshot after confirming
                    self.take_debug_screenshot(f"after_confirm_{show_name}_{amount}")

                    # Refresh page before checking balance to avoid cache
                    self.page.reload()
                    self.page.wait_for_load_state("networkidle", timeout=5000)

                    # Check if the balance decreased by the funded amount
                    new_balance = self.get_loot_balance()
                    if self.debug:
                        logging.info(f"Balance after funding attempt: {new_balance}")

                    success_count += 1
                    logging.info(f"Successfully funded {show_name} with {amount} LOOT")

                except PlaywrightTimeoutError as e:
                    self.take_debug_screenshot(f"funding_error_{show_name}_{amount}")
                    logging.error(f"Failed to fund {amount} LOOT: {str(e)}")

            return success_count > 0

        except Exception as e:
            logging.error(f"Funding failed for {show_name}: {str(e)}")
            raise

    def get_loot_balance(self):
        """Get the current LOOT balance from the header"""
        try:
            # Navigate to home page where balance is visible
            self.page.goto(self.base_url)
            self.page.wait_for_load_state("networkidle", timeout=10000)

            if self.debug:
                self.take_debug_screenshot("before_balance_check")

            # Look for the <a> tag containing the fa-loor-money icon and balance
            selectors = [
                "a:has(svg.fa-loor-money)",  # A tag containing the SVG icon
                'a:has([class*="fa-loor-money"])',  # Alternative class syntax
                'a:has([class*="loor-money"])',  # More general icon class
            ]

            balance_element = None
            balance_text = None

            for selector in selectors:
                try:
                    elements = self.page.query_selector_all(selector)
                    for element in elements:
                        text = element.text_content().strip()
                        # Make sure we have numbers in the text
                        if any(c.isdigit() for c in text):
                            balance_element = element
                            balance_text = text
                            logging.info(f"Found balance with selector: {selector}")
                            if self.debug:
                                logging.info(f"Raw balance text: {text}")
                            break
                    if balance_text:
                        break
                except Exception as e:
                    if self.debug:
                        logging.debug(f"Selector {selector} failed: {str(e)}")
                    continue

            if not balance_element or not balance_text:
                if self.debug:
                    self.take_debug_screenshot("balance_not_found")
                    # Get page content for debugging
                    with open(os.path.join("debug", "page_content.txt"), "w") as f:
                        f.write(self.page.content())
                raise ValueError("Could not find LOOT balance in header")

            # Extract just the number from the text, ignoring any commas or other text
            balance = int("".join(c for c in balance_text if c.isdigit()))

            if self.debug:
                # Take a screenshot of the balance element for debugging
                self.take_debug_screenshot("loot_balance")
                balance_element.screenshot(
                    path=os.path.join("debug", "screenshots", "balance_element.png")
                )
                logging.info(f"Extracted balance number: {balance}")

            logging.info(f"Current LOOT balance: {balance}")
            return balance

        except Exception as e:
            logging.error(f"Failed to get LOOT balance: {str(e)}")
            if self.debug:
                self.take_debug_screenshot("balance_error")
            raise

    def validate_funding_amounts(self):
        """Validate that we have enough LOOT for all planned funding"""
        try:
            # Calculate total LOOT needed
            total_needed = 0
            for item in self.config["media"]:
                total_needed += sum(item["amounts"])

            # Get current balance
            current_balance = self.get_loot_balance()

            if current_balance < total_needed:
                raise ValueError(
                    f"Insufficient LOOT balance. Have: {current_balance}, Need: {total_needed}"
                )

            if self.dryrun:
                logging.info(
                    f"DRYRUN: Would use {total_needed} of {current_balance} available LOOT"
                )
            else:
                logging.info(
                    f"LOOT balance sufficient. Have: {current_balance}, Need: {total_needed}"
                )
            return True

        except Exception as e:
            logging.error(f"Funding validation failed: {str(e)}")
            raise

    def fund_all_shows(self):
        """Fund all media specified in the config file."""
        try:
            # Validate we have enough LOOT before proceeding
            if not self.validate_funding_amounts():
                return False

            for item in self.config["media"]:
                try:
                    self.fund_show(item["name"], item["amounts"])
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
        """Claim daily LOOT if available."""
        # Ensure we're logged in
        if not self.context or not self.page:
            self.login()

        logging.info("Checking for claimable LOOT...")
        self.page.goto(f"{self.base_url}/quests")
        self.page.wait_for_load_state("networkidle", timeout=5000)

        # Take screenshot of quests page
        if self.debug:
            self.take_debug_screenshot("quests_page")

        # First check if already claimed
        try:
            claimed_text = self.page.wait_for_selector(
                'text="Already claimed"', timeout=2000
            )
            if claimed_text:
                logging.info("Already claimed today's LOOT")
                return
        except:
            pass  # Not already claimed, continue

        # Look for claim form
        form = self.page.query_selector('form:has(button:has-text("Claim"))')
        if form:
            logging.info("Found claimable LOOT quest")
            if self.debug:
                self.take_debug_screenshot("before_claim")

            # Click claim button
            claim_button = form.query_selector('button:has-text("Claim")')
            claim_button.click()

            # Wait for claim to process
            self.page.wait_for_load_state("networkidle", timeout=5000)

            if self.debug:
                self.take_debug_screenshot("after_claim")

            # Get new balance
            new_balance = self.get_loot_balance()
            logging.info(f"Successfully claimed LOOT. New balance: {new_balance}")
        else:
            logging.info("No quest available at this time")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Loor.tv Funding Automator")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (visible browser and screenshots)",
    )
    parser.add_argument(
        "--dryrun",
        action="store_true",
        help="Simulate the funding process without actually funding",
    )
    parser.add_argument(
        "--claim-only",
        action="store_true",
        help="Only claim LOOT without funding shows",
    )
    args = parser.parse_args()

    loor = None
    try:
        loor = LoorAPI(
            os.getenv("LOOR_EMAIL"),
            os.getenv("LOOR_PASSWORD"),
            debug=args.debug,
            dryrun=args.dryrun,
        )

        # Always try to claim LOOT first
        try:
            loor.claim_loot()  # This will handle login
        except Exception as e:
            logging.error(f"Failed to claim LOOT: {str(e)}")

        # If not claim-only mode, proceed with funding
        if not args.claim_only:
            if args.dryrun:
                logging.info("Starting dry run - no actual funding will occur")
            loor.fund_all_shows()  # Remove login call since we're already logged in
            if args.dryrun:
                logging.info("Dry run completed successfully")
            else:
                logging.info("Funding completed")
    except Exception as e:
        logging.error(f"Error during execution: {str(e)}")
    finally:
        if loor:
            loor.cleanup()


if __name__ == "__main__":
    main()
