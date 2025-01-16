# Loor.tv Funding Automator

A Python script to automate the process of funding shows on Loor.tv. The script can:

- Automatically claim daily LOOT rewards
- Fund multiple shows with specified LOOT amounts
- Validate LOOT balance before funding
- Take debug screenshots for troubleshooting

## Requirements

- Python 3.7+
- Playwright for Python
- PyYAML
- python-dotenv

## Setup

1. Install dependencies:

```bash
pip install playwright python-dotenv pyyaml
playwright install chromium
```

2. Create a `.secrets` file with your Loor.tv credentials:

```env
LOOR_EMAIL=your.email@example.com
LOOR_PASSWORD=your_password
```

3. Create your `config.yml` by copying the example:

```bash
cp .example.config.yml config.yml
```

4. Edit `config.yml` to configure your shows:

```yaml
media:
  - name: "Show Name"
    type: "show"
    amounts: [100, 400] # Valid amounts: 100, 400, 800
```

Note: Both `.secrets` and `config.yml` are git-ignored for security.

## Usage

Basic usage:

```bash
python3 loor_funding.py
```

Available options:

- `--debug`: Enable debug mode (visible browser and screenshots)
- `--dryrun`: Simulate funding without actually spending LOOT
- `--claim-only`: Only claim daily LOOT without funding shows

Examples:

```bash
# Just claim daily LOOT
python3 loor_funding.py --claim-only

# Test funding with debug screenshots
python3 loor_funding.py --debug

# Simulate funding without spending LOOT
python3 loor_funding.py --dryrun
```

## Debug Mode

When running with `--debug`:

- Browser window will be visible
- Screenshots are saved in `debug/screenshots/` directory
- Detailed logging is enabled

## Configuration

The `config.yml` file supports:

- Multiple shows
- Different funding amounts per show (100, 400, or 800 LOOT)
- Show types (currently supports "show")

Example config:

```yaml
media:
  - name: "Show One"
    type: "show"
    amounts: [100, 400]

  - name: "Show Two"
    type: "show"
    amounts: [800]
```

## Error Handling

The script includes:

- LOOT balance validation
- Automatic login retry
- Detailed error logging
- Debug screenshots for troubleshooting
- Graceful cleanup of browser resources
