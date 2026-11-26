name: Check Duplicate Orders

on:
  schedule:
    - cron: '0 * * * *'  # Every hour on the hour
  workflow_dispatch: {}   # Manual trigger for testing

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - run: pip install requests

      - run: python check_duplicates.py
        env:
          SHOPIFY_STORE: ${{ secrets.SHOPIFY_STORE }}
          SHOPIFY_TOKEN: ${{ secrets.SHOPIFY_TOKEN }}
          SLACK_WEBHOOK: ${{ secrets.SLACK_WEBHOOK }}
